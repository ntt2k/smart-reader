from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document as LangchainDocument
from typing import List, Dict, Any
import os
from pypdf import PdfReader
import io

class AIUtils:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.llm = ChatOpenAI(temperature=0)
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
            prompt = f"""Please provide a concise summary of the following text. Focus on the main points and key takeaways:

            {chunk.page_content}

            Summary:"""

            messages = [{"role": "user", "content": prompt}]
            response = await self.llm.agenerate([messages])
            chunk_summaries.append(response.generations[0][0].text)

        # If we have multiple chunks, create a final summary
        if len(chunk_summaries) > 1:
            combined_summary = "\n\n".join(chunk_summaries)
            final_prompt = f"""Please provide a coherent summary combining these section summaries:

            {combined_summary}

            Final Summary:"""

            messages = [{"role": "user", "content": final_prompt}]
            response = await self.llm.agenerate([messages])
            return response.generations[0][0].text

        return chunk_summaries[0] if chunk_summaries else ""

    async def split_text(self, text: str) -> List[LangchainDocument]:
        return self.text_splitter.create_documents([text])
    