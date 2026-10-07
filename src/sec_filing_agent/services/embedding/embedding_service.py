"""Embedding Service"""

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from sec_filing_agent.db.session import SessionLocal
from sec_filing_agent.db.tables import (
    ChunkEmbedding,
    FilingChunk,
    Filing,
    FilingSection,
    FilingSectionCleaning,
)
from sec_filing_agent.services.embedding.embedding_provider import UniversalEmbeddingProvider
from sec_filing_agent.models import SearchResult, RetrievalFilters


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

    async def search(self, query: str, top_k: int, filters: RetrievalFilters):
        query_vectors = (
            await run_in_threadpool(
                self.embedding_provider.embed_queries,
                [query],
            )
        )[0]

        result_after = await self._structured_filter(query_vectors, top_k, filters)

        return result_after

    async def _structured_filter(
        self, query_vector: list[float], top_k: int, filters: RetrievalFilters
    ):
        distance = ChunkEmbedding.embedding.cosine_distance(query_vector).label("distance")

        statement = (
            select(
                FilingChunk.id.label("chunk_id"),
                distance,
                Filing.accession_number,
                Filing.form_type,
                Filing.report_date,
                FilingSection.item_code,
                FilingChunk.content,
                FilingSection.source_url,
                Filing.cik,
            )
            .select_from(ChunkEmbedding)
            .join(FilingChunk, FilingChunk.id == ChunkEmbedding.chunk_id)
            .join(FilingSectionCleaning, FilingSectionCleaning.id == FilingChunk.cleaning_id)
            .join(FilingSection, FilingSection.id == FilingSectionCleaning.section_id)
            .join(Filing, Filing.accession_number == FilingSection.accession_number)
            .where(ChunkEmbedding.model_profile_id == DEFAULT_MODEL_PROFILE_ID)
        )

        if filters.ciks is not None:
            statement = statement.where(ChunkEmbedding.cik.in_(filters.ciks))

        if filters.form_types is not None:
            statement = statement.where(Filing.form_type.in_(filters.form_types))

        if filters.report_date_from is not None:
            statement = statement.where(Filing.report_date >= filters.report_date_from)

        if filters.report_date_to is not None:
            statement = statement.where(Filing.report_date <= filters.report_date_to)

        if filters.item_codes is not None:
            statement = statement.where(FilingSection.item_code.in_(filters.item_codes))

        statement = statement.order_by(distance).limit(top_k)

        # retrieval first round with cosine distance
        async with SessionLocal() as session:
            result = await session.execute(statement)

        return [
            SearchResult(
                chunk_id=chunk_id,
                score=1 - distance,
                cik=cik,
                accession_number=accession_number,
                form_type=form_type,
                report_date=report_date,
                item_code=item_code,
                content=content,
                source_url=source_url,
            )
            for (
                chunk_id,
                distance,
                accession_number,
                form_type,
                report_date,
                item_code,
                content,
                source_url,
                cik,
            ) in result.tuples()
        ]
