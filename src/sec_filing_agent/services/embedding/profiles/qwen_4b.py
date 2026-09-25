"""Qwen3 4b Embedding"""

import torch
from sentence_transformers import SentenceTransformer

from sec_filing_agent.services.embedding.base import BaseEmbeddingImplementation

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

model = SentenceTransformer(
    "Qwen/Qwen3-Embedding-4B",
    local_files_only=True,
    device=DEVICE,
)

QUERY_PROMPT = (
    "Instruct: Given an investor question, retrieve the most relevant passages "
    "from SEC filings. Match the company, fiscal period, financial metric, "
    "and requested disclosure.\nQuery:"
)


class Qwen3Embedding4B(BaseEmbeddingImplementation):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = model.encode(
            texts,
            batch_size=8,
            normalize_embeddings=True,
            truncate_dim=1024,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_queries(self, queries: list[str]) -> list[list[float]]:
        vectors = model.encode(
            queries,
            prompt=QUERY_PROMPT,
            batch_size=8,
            normalize_embeddings=True,
            truncate_dim=1024,
            show_progress_bar=False,
        )
        return vectors.tolist()
