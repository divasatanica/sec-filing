"""Embedding Service"""

import re

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import aliased
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

        return await self._complete_chunk_context(result_after)

    async def _complete_chunk_context(self, results: list[SearchResult]) -> list[SearchResult]:
        """Repair overlapping chunk boundaries without changing ranks or stored text.

        Fetch both neighbors in one query, scoped to the same cleaning version/section.
        Only the returned content is expanded; its score still belongs to the hit.
        """
        if not results:
            return results

        previous = aliased(FilingChunk)
        following = aliased(FilingChunk)
        statement = (
            select(FilingChunk.id, previous.content, following.content)
            .outerjoin(
                previous,
                (previous.cleaning_id == FilingChunk.cleaning_id)
                & (previous.chunk_index == FilingChunk.chunk_index - 1),
            )
            .outerjoin(
                following,
                (following.cleaning_id == FilingChunk.cleaning_id)
                & (following.chunk_index == FilingChunk.chunk_index + 1),
            )
            .where(FilingChunk.id.in_([result.chunk_id for result in results]))
        )
        async with SessionLocal() as session:
            neighbors = {
                chunk_id: (before, after)
                for chunk_id, before, after in (await session.execute(statement)).tuples().all()
            }

        completed = []
        for result in results:
            before, after = neighbors.get(result.chunk_id, (None, None))
            content = result.content
            if before is not None:
                content = self._restore_chunk_prefix(before, content)
            if after is not None:
                content = self._restore_chunk_suffix(after, content)
            completed.append(result.model_copy(update={"content": content}))
        return completed

    @staticmethod
    def _restore_chunk_prefix(previous: str, content: str) -> str:
        """Use exact overlap to restore a partial opening sentence or line.

        Bounds are in characters, independent of the embedding tokenizer. If there
        is no reliable overlap/boundary, leave the hit unchanged instead of guessing.
        """
        previous = previous.rstrip()
        current = content.lstrip()
        # A minimum match avoids treating coincidental punctuation as overlap.
        overlap = next(
            (
                size
                for size in range(min(len(previous), len(current), 2000), 15, -1)
                if previous.endswith(current[:size])
            ),
            0,
        )
        if not overlap:
            return content

        start = len(previous) - overlap
        # Decimal points are not sentence boundaries; preserve line/table boundaries.
        boundaries = [0] + [
            match.end() for match in re.finditer(r"\n\s*|[.!?]\s+", previous[:start])
        ]
        boundary = boundaries[-1]
        prefix = previous[boundary:start]
        if not prefix.strip() or len(prefix) > 800:
            return content

        # Prefix ends exactly where the overlapping text begins: no inserted space
        # that could turn "$141" + ".3 million" into a broken numeric literal.
        return prefix.lstrip() + current

    @staticmethod
    def _restore_chunk_suffix(following: str, content: str) -> str:
        """Restore a partial closing sentence/line using the next chunk's overlap."""
        current = content.rstrip()
        following = following.lstrip()
        overlap = next(
            (
                size
                for size in range(min(len(current), len(following), 2000), 15, -1)
                if current.endswith(following[:size])
            ),
            0,
        )
        if not overlap:
            return content

        remainder = following[overlap:]
        # Already at a sentence/line boundary: do not append the next sentence/row.
        if not remainder or remainder.startswith("\n"):
            return content
        if current.endswith((".", "!", "?")) and remainder[0].isspace():
            return content

        boundary = re.search(r"\n|[.!?](?=\s|$)", remainder)
        if boundary is None:
            return content
        end = boundary.start() if boundary.group() == "\n" else boundary.end()
        suffix = remainder[:end]
        if not suffix.strip() or len(suffix) > 800:
            return content
        return current + suffix

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
