import os
from datetime import datetime
from typing import List, Dict, Any
from opensearchpy import OpenSearch

class OpenSearchClient:
    def __init__(self):
        self.client = OpenSearch(
            hosts=[os.getenv('OPENSEARCH_URL', 'http://opensearch:9200')],
            http_auth=None,
            use_ssl=False,
            verify_certs=False,
            ssl_show_warn=False
        )
        self.index_name = 'pdf_documents'
        self.ensure_index()

    def ensure_index(self):
        index_body = {
            'mappings': {
                'properties': {
                    'content': {'type': 'text'},
                    'chunk_index': {'type': 'integer'},
                    'embedding': {
                        'type': 'knn_vector',
                        'dimension': 1536,
                        'method': {
                            'name': 'hnsw',
                            'space_type': 'cosinesimil',
                            'engine': 'nmslib'
                        }
                    },
                    'created_at': {'type': 'date'},
                    # Add additional metadata fields if needed
                    'metadata': {
                        'type': 'object',
                        'enabled': True
                    }
                }
            },
            'settings': {
                'index': {
                    'knn': True,
                    'knn.algo_param.ef_search': 100,
                    'number_of_shards': 1,  # Recommended for k-NN
                    'number_of_replicas': 0  # Can be adjusted based on your needs
                }
            }
        }

        if not self.client.indices.exists(self.index_name):
            self.client.indices.create(
                index=self.index_name,
                body=index_body
            )

    async def index_document(self, doc_id: str, content: str, metadata: Dict[str, Any], embeddings: List[List[float]]):
        try:
            # Split content into chunks to match embeddings
            chunks = content.split('\n\n')  # Simple splitting, matches the text splitter in AIUtils

            # Index each chunk with its embedding
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                document = {
                    'content': chunk,
                    'chunk_index': i,
                    'embedding': embedding,
                    'metadata': metadata,
                    'created_at': datetime.utcnow().isoformat()
                }

                # Index the document
                response = self.client.index(
                    index=self.index_name,
                    id=f"{doc_id}_{i}",  # Unique ID for each chunk
                    body=document,
                    refresh=True  # Ensure the document is immediately searchable
                )

            return True

        except Exception as e:
            print(f"Error indexing document {doc_id}: {str(e)}")
            raise

    async def search_documents(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            # Using k-NN search query
            knn_query = {
                "knn": {
                    "embedding": {
                        "vector": query_embedding,
                        "k": top_k * 2  # Fetch more results initially to account for deduplication
                    }
                }
            }

            response = self.client.search(
                index=self.index_name,
                body={
                    "query": knn_query,
                    "_source": ["content", "chunk_index", "metadata"],
                    "size": top_k * 2
                }
            )

            # Group by original document ID and take the highest scoring chunk
            results_by_doc = {}
            for hit in response["hits"]["hits"]:
                doc_id = hit["_id"].split("_")[0]  # Get original document ID
                if doc_id not in results_by_doc or hit["_score"] > results_by_doc[doc_id]["score"]:
                    results_by_doc[doc_id] = {
                        "id": doc_id,
                        "content": hit["_source"]["content"],
                        "score": hit["_score"],
                        "metadata": hit["_source"].get("metadata", {})
                    }

            # Return only the top k results after deduplication
            return list(results_by_doc.values())[:top_k]

        except Exception as e:
            print(f"Error searching documents: {str(e)}")
            raise

    async def delete_document(self, doc_id: str) -> bool:
        """Delete all chunks of a document by its ID prefix"""
        try:
            response = self.client.delete_by_query(
                index=self.index_name,
                body={
                    "query": {
                        "prefix": {
                            "_id": doc_id
                        }
                    }
                },
                refresh=True
            )
            return response["deleted"] > 0
        except Exception as e:
            print(f"Error deleting document {doc_id}: {str(e)}")
            return False

    async def get_document(self, doc_id: str) -> Dict[str, Any]:
        """Retrieve all chunks of a document by its ID prefix"""
        try:
            response = self.client.search(
                index=self.index_name,
                body={
                    "query": {
                        "prefix": {
                            "_id": doc_id
                        }
                    },
                    "sort": [
                        {"chunk_index": "asc"}
                    ]
                }
            )

            chunks = []
            metadata = {}
            for hit in response["hits"]["hits"]:
                chunks.append(hit["_source"]["content"])
                if not metadata and "metadata" in hit["_source"]:
                    metadata = hit["_source"]["metadata"]

            return {
                "id": doc_id,
                "content": "\n\n".join(chunks),
                "metadata": metadata
            }
        except Exception as e:
            print(f"Error retrieving document {doc_id}: {str(e)}")
            return None