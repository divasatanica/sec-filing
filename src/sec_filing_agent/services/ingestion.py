"""Orchestration flow for future filing ingestion implementation."""

from collections.abc import Sequence
from dataclasses import dataclass

from sec_filing_agent.domain.filings import FilingReference, FilingSyncRequest
from sec_filing_agent.services.contracts import FilingRepository, RagEngine, SecFilingsGateway


@dataclass(slots=True)
class IngestionService:
    """Coordinates discovery, persistence, download, and RAG indexing.

    It deliberately has no SEC parsing or vector-store logic. Keep those details in
    concrete adapters, which makes each layer independently testable and replaceable.
    """

    gateway: SecFilingsGateway
    repository: FilingRepository
    rag_engine: RagEngine

    async def sync(self, request: FilingSyncRequest) -> int:
        discovered: list[FilingReference] = []
        for instrument in request.instruments:
            filings: Sequence[FilingReference] = await self.gateway.discover_filings(
                instrument=instrument.upper(),
                forms=request.forms,
                from_date=request.from_date,
                to_date=request.to_date,
            )
            discovered.extend(filings)

        await self.repository.upsert_filings(discovered)

        # Your adapter can make `force_reprocess` meaningful (for example by checking
        # a content hash before re-chunking). The orchestration boundary stays stable.
        for filing in discovered:
            raw_document = await self.gateway.download_filing(
                accession_number=filing.accession_number
            )
            await self.rag_engine.index_filing(filing=filing, raw_document=raw_document)

        return len(discovered)
