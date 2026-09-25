"""Universal embedding provider exposing API to external caller"""

from sec_filing_agent.services.embedding.base import BaseEmbeddingImplementation
from sec_filing_agent.services.embedding.profiles.qwen_4b import Qwen3Embedding4B

embedding_impl = Qwen3Embedding4B()


class UniversalEmbeddingProvider:
    embedding_impl: BaseEmbeddingImplementation

    def __init__(self):
        self.embedding_impl = embedding_impl

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embedding_impl.embed_documents(texts)

    def embed_queries(self, queries: list[str]) -> list[list[str]]:
        return self.embed_queries(queries)
