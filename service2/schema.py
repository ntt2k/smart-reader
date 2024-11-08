import strawberry
from typing import List
import httpx
import os
import boto3
from botocore.client import Config

from opensearch_utils import OpenSearchClient
from ai_utils import AIUtils


@strawberry.type
class SearchResult:
    id: str
    content: str
    page_number: int
    score: float


@strawberry.type
class Query:
    @strawberry.field
    async def search_pdfs(self, query: str, top_k: int = 5) -> List[SearchResult]:
        ai_utils = AIUtils()
        opensearch_client = OpenSearchClient()

        # Create embedding for the query - get single embedding vector
        embeddings, _ = await ai_utils.create_embeddings(query)
        # Take first embedding and convert to list of floats
        query_embedding = [float(x) for x in embeddings[0]]

        # Search documents
        results = await opensearch_client.search_documents(query_embedding, top_k)

        return [
            SearchResult(
                id=result["id"],
                content=result["content"],
                page_number=result["page_number"],
                score=result["score"],
            )
            for result in results
        ]


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def index_pdf(self, pdf_id: int) -> bool:
        try:
            ai_utils = AIUtils()
            opensearch_client = OpenSearchClient()

            # 1. Get PDF metadata from Service 1
            async with httpx.AsyncClient() as client:
                query = """
                    query($pdfId: Int!) {
                        pdf(pdfId: $pdfId) {
                            id
                            filename
                            s3Url
                        }
                    }
                """
                variables = {"pdfId": pdf_id}
                response = await client.post(
                    "http://service1:8081/graphql",
                    json={"query": query, "variables": variables},
                )

                if response.status_code != 200:
                    print(f"Error fetching PDF metadata: {response.text}")
                    return False

                data = response.json()
                if not data.get("data", {}).get("pdf"):
                    print(f"PDF with id {pdf_id} not found")
                    return False

                pdf_data = data["data"]["pdf"]
                s3_url = pdf_data["s3Url"]

            # 2. Download PDF from S3
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(signature_version="s3v4"),
            )

            bucket_name = os.getenv("BUCKET_NAME")
            file_key = pdf_data["filename"]

            # 3. Download PDF content to memory
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            pdf_content = response["Body"].read()

            # 4. Extract text from PDF with page numbers
            page_chunks = await ai_utils.extract_text_from_pdf(pdf_content)

            # 5. Create embeddings
            embeddings, chunks = await ai_utils.create_embeddings(page_chunks)

            # 6. Index document in OpenSearch with page numbers
            await opensearch_client.index_document(str(pdf_id), chunks, {}, embeddings)

            return True

        except Exception as e:
            print(f"Error indexing PDF: {e}")
            return False

    @strawberry.mutation
    async def generate_summary(self, pdf_id: int) -> str:
        try:
            ai_utils = AIUtils()

            # 1. Get PDF metadata from Service 1
            async with httpx.AsyncClient() as client:
                query = """
                    query($pdfId: Int!) {
                        pdf(pdfId: $pdfId) {
                            id
                            filename
                            s3Url
                        }
                    }
                """
                variables = {"pdfId": pdf_id}
                response = await client.post(
                    "http://service1:8081/graphql",
                    json={"query": query, "variables": variables},
                )

                if response.status_code != 200:
                    raise Exception(f"Error fetching PDF metadata: {response.text}")

                data = response.json()
                if not data.get("data", {}).get("pdf"):
                    raise Exception(f"PDF with id {pdf_id} not found")

                pdf_data = data["data"]["pdf"]

            # 2a. Download PDF from S3
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(signature_version="s3v4"),
            )

            bucket_name = os.getenv("BUCKET_NAME")
            file_key = pdf_data["filename"]

            # 2b. Download PDF content to memory
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            pdf_content = response["Body"].read()

            # 3. Extract text from PDF with page numbers
            page_chunks = await ai_utils.extract_text_from_pdf(pdf_content)

            # 4. Generate and return summary
            summary = await ai_utils.create_summary(page_chunks)
            return summary

        except Exception as e:
            print(f"Error generating summary: {e}")
            raise


schema = strawberry.federation.Schema(query=Query, mutation=Mutation)
