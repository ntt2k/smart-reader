import io
import os
from typing import List
import tiktoken

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
            chunk_size=8000,
            chunk_overlap=200
        )
        # Initialize tokenizer for GPT-4
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        self.max_tokens = 8000  # Conservative limit for GPT-4 input

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
        # Check text length in tokens
        num_tokens = len(self.tokenizer.encode(text))

        if num_tokens <= self.max_tokens:
            # If text is within token limit, summarize directly
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates comprehensive yet concise summaries. Organize the summary with bullet points for key topics and insights."},
                    {"role": "user", "content": f"Please provide a comprehensive summary of the following text, focusing on the main points and key takeaways:\n\n{text}"}
                ],
                temperature=0
            )
            return response.choices[0].message.content

        # If text is too long, fall back to chunked summarization
        chunks = await self.split_text(text)

        # Summarize each chunk
        chunk_summaries = []
        for chunk in chunks:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates concise summaries of text segments."},
                    {"role": "user", "content": f"Please summarize this text segment, focusing on the main points:\n\n{chunk.page_content}"}
                ],
                temperature=0
            )
            chunk_summaries.append(response.choices[0].message.content)

        # Create final summary from chunk summaries
        combined_summary = "\n\n".join(chunk_summaries)

        final_response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that creates coherent summaries. Organize the final summary with bullet points for key topics and insights."},
                {"role": "user", "content": f"Please provide a coherent, comprehensive summary combining these section summaries, maintaining a clear flow between topics:\n\n{combined_summary}"}
            ],
            temperature=0
        )

        return final_response.choices[0].message.content

    async def split_text(self, text: str) -> List[LangchainDocument]:
        return self.text_splitter.create_documents([text])