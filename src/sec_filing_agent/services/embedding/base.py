"""Base class of Embedding implementation"""

from abc import ABC, abstractmethod


class BaseEmbeddingImplementation(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_queries(self, queries: list[str]) -> list[list[float]]: ...
