"""Embedding Service"""

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from sec_filing_agent.db.session import SessionLocal
from sec_filing_agent.db.tables import ChunkEmbedding, FilingChunk
from sec_filing_agent.services.embedding.embedding_provider import UniversalEmbeddingProvider


class ChunkNotFoundError(LookupError):
    """Chunk should exist before embedding"""


DEFAULT_MODEL_PROFILE_ID = 1


class EmbeddingService:
    def __init__(self) -> None:
        self.embedding_provider = UniversalEmbeddingProvider()

    async def build_embedding_index(self, cik: str, force: bool = False) -> int:
        """Create or refresh embeddings whose source chunk content has changed."""

        async with SessionLocal() as session:
            statement = select(FilingChunk).where(FilingChunk.cik == cik)
            chunks = (await session.scalars(statement)).all()

            if not chunks:
                raise ChunkNotFoundError(cik)

            existing_hashes: dict[int, str] = {}
            if not force:
                existing_hash_rows = (
                    (
                        await session.execute(
                            select(
                                ChunkEmbedding.chunk_id,
                                ChunkEmbedding.source_content_hash,
                            ).where(
                                ChunkEmbedding.model_profile_id == DEFAULT_MODEL_PROFILE_ID,
                                ChunkEmbedding.chunk_id.in_([chunk.id for chunk in chunks]),
                            )
                        )
                    )
                    .tuples()
                    .all()
                )
                existing_hashes: dict[int, str] = dict(existing_hash_rows)

        chunks_to_embed = [
            chunk
            for chunk in chunks
            if force or existing_hashes.get(chunk.id) != chunk.content_hash
        ]
        if not chunks_to_embed:
            return 0

        embedding_vectors = self.embedding_provider.embed_documents(
            [chunk.content for chunk in chunks_to_embed]
        )
        rows = [
            {
                "chunk_id": chunk.id,
                "source_content_hash": chunk.content_hash,
                "embedding": embedding_vector,
                "model_profile_id": DEFAULT_MODEL_PROFILE_ID,
                "cik": chunk.cik,
            }
            for chunk, embedding_vector in zip(chunks_to_embed, embedding_vectors, strict=True)
        ]
        insert_statement = insert(ChunkEmbedding).values(rows)
        excluded = insert_statement.excluded
        set_values = {
            "embedding": excluded["embedding"],
            "source_content_hash": excluded["source_content_hash"],
        }
        if force:
            upsert_statement = insert_statement.on_conflict_do_update(
                constraint="uq_chunk_embeddings_chunk_profile",
                set_=set_values,
            )
        else:
            upsert_statement = insert_statement.on_conflict_do_update(
                constraint="uq_chunk_embeddings_chunk_profile",
                set_=set_values,
                where=ChunkEmbedding.source_content_hash.is_distinct_from(
                    excluded["source_content_hash"]
                ),
            )

        async with SessionLocal.begin() as session:
            await session.execute(upsert_statement)

        return len(chunks_to_embed)

    async def search(self, query: str):
        query_vectors = (
            await run_in_threadpool(
                self.embedding_provider.embed_queries,
                [query],
            )
        )[0]

        return query_vectors
