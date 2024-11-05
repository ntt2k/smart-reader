import io
import os
from dataclasses import dataclass
from typing import List, Tuple, Union
import tiktoken

from langchain.schema import Document as LangchainDocument
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from openai import AsyncOpenAI
from pypdf import PdfReader


TOKEN_SIZE = 4000
TOKEN_OVERLAP = 200


@dataclass
class PageChunk:
    content: str
    page_num: int


class AIUtils:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=TOKEN_SIZE, chunk_overlap=TOKEN_OVERLAP
        )
        # Initialize tokenizer for GPT-4
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        self.max_tokens = TOKEN_SIZE  # Conservative limit for GPT-4 input

    async def extract_text_from_pdf(self, pdf_content: bytes) -> List[PageChunk]:
        pdf_file = io.BytesIO(pdf_content)
        pdf_reader = PdfReader(pdf_file)
        page_chunks = []

        for page_num, page in enumerate(pdf_reader.pages, 1):  # Start page numbers at 1
            text = page.extract_text()
            if text.strip():  # Only add non-empty pages
                page_chunks.append(PageChunk(content=text, page_num=page_num))

        return page_chunks


    async def create_embeddings(self, text_or_chunks: Union[str, List[PageChunk]]) -> Tuple[List[List[float]], List[PageChunk]]:
        if isinstance(text_or_chunks, str):
            # For search queries, return single embedding with dummy page chunk
            if len(self.tokenizer.encode(text_or_chunks)) < TOKEN_SIZE:
                embedding = await self.embeddings.aembed_query(text_or_chunks)
                return [embedding], [PageChunk(content=text_or_chunks, page_num=0)]

        # For PDF content, we have a list of PageChunks
        all_chunks = []
        all_embeddings = []

        # Process each page's content
        page_chunks = text_or_chunks if isinstance(text_or_chunks, list) else [PageChunk(text_or_chunks, 0)]

        for page_chunk in page_chunks:
            # Split the page content into smaller chunks
            chunks = self.text_splitter.create_documents([page_chunk.content])

            # Create embeddings for each chunk while maintaining page number
            for chunk in chunks:
                chunk_embedding = await self.embeddings.aembed_query(chunk.page_content)
                all_embeddings.append(chunk_embedding)
                all_chunks.append(PageChunk(
                    content=chunk.page_content,
                    page_num=page_chunk.page_num
                ))

        return all_embeddings, all_chunks


    async def create_summary(self, page_chunks: List[PageChunk]) -> str:
        # Combine all page contents with page numbers
        formatted_text = "\n\n".join(
            f"[Page {chunk.page_num}]\n{chunk.content}"
            for chunk in page_chunks
        )

        # Check text length in tokens
        num_tokens = len(self.tokenizer.encode(formatted_text))

        if num_tokens <= self.max_tokens:
            # If text is within token limit, summarize directly
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates comprehensive yet concise summaries. Organize the summary with bullet points for key topics and insights. When referencing content, include the page number in brackets [Page X].",
                    },
                    {
                        "role": "user",
                        "content": f"Please provide a comprehensive summary of the following text, focusing on the main points and key takeaways. Include page references when noting key points:\n\n{formatted_text}",
                    },
                ],
                temperature=0,
            )
            return response.choices[0].message.content

        # If text is too long, fall back to chunked summarization
        chunks = await self.split_text(formatted_text)

        # Summarize each chunk
        chunk_summaries = []
        for chunk in chunks:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates concise summaries of text segments. Include page references [Page X] when noting key points.",
                    },
                    {
                        "role": "user",
                        "content": f"Please summarize this text segment, focusing on the main points:\n\n{chunk.page_content}",
                    },
                ],
                temperature=0,
            )
            chunk_summaries.append(response.choices[0].message.content)

        # Create final summary from chunk summaries
        combined_summary = "\n\n".join(chunk_summaries)

        final_response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that creates coherent summaries. Organize the final summary with bullet points for key topics and insights. Maintain page references [Page X] for key points.",
                },
                {
                    "role": "user",
                    "content": f"Please provide a coherent, comprehensive summary combining these section summaries, maintaining a clear flow between topics and preserving page references:\n\n{combined_summary}",
                },
            ],
            temperature=0,
        )

        return final_response.choices[0].message.content

    async def split_text(self, text: str) -> List[LangchainDocument]:
        return self.text_splitter.create_documents([text])
