import io
import os
from typing import List

from langchain.schema import Document as LangchainDocument
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from openai import AsyncOpenAI
from pypdf import PdfReader


class AIUtils:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100
        )

    async def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        pdf_file = io.BytesIO(pdf_content)
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text

    async def create_embeddings(self, text: str) -> List[List[float]]:
        # Split text into chunks
        chunks = await self.split_text(text)

        # Create embeddings for each chunk
        embeddings = []
        for chunk in chunks:
            chunk_embedding = await self.embeddings.aembed_query(chunk.page_content)
            embeddings.append(chunk_embedding)

        return embeddings

    async def create_summary(self, text: str) -> str:
        # Split into chunks if text is too long
        chunks = await self.split_text(text)

        # Summarize each chunk
        chunk_summaries = []
        for chunk in chunks:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                    {"role": "user", "content": f"Please summarize the following text, focusing on the main points and key takeaways:\n\n{chunk.page_content}"}
                ],
                temperature=0
            )
            chunk_summaries.append(response.choices[0].message.content)

        # If we have multiple chunks, create a final summary
        if len(chunk_summaries) > 1:
            combined_summary = "\n\n".join(chunk_summaries)

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates coherent summaries."},
                    {"role": "user", "content": f"Please provide a coherent summary with bullet points combining these section summaries:\n\n{combined_summary}"}
                ],
                temperature=0
            )
            return response.choices[0].message.content

        return chunk_summaries[0] if chunk_summaries else ""

    async def split_text(self, text: str) -> List[LangchainDocument]:
        return self.text_splitter.create_documents([text])