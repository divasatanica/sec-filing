"""Ports that isolate HTTP code from your SEC and RAG implementations.

Implement these protocols with your preferred SEC client, parser, database, embedding
provider, and vector store. API routers should depend only on these interfaces.
"""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from sec_filing_agent.domain.filings import FilingForm, FilingReference
from sec_filing_agent.domain.research import Citation, ResearchQuery


class SecFilingsGateway(Protocol):
    async def discover_filings(
        self,
        *,
        instrument: str,
        forms: Sequence[FilingForm],
        from_date: date | None,
        to_date: date | None,
    ) -> Sequence[FilingReference]:
        """Get filing metadata from SEC EDGAR or another authoritative source."""

    async def download_filing(self, *, accession_number: str) -> str:
        """Return the raw filing document for the given accession number."""


class FilingRepository(Protocol):
    async def list_filings(
        self,
        *,
        instrument: str,
        forms: Sequence[FilingForm],
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[FilingReference], str | None]:
        """List locally known filing records."""

    async def get_filing(self, *, accession_number: str) -> FilingReference:
        """Return one locally known filing record."""

    async def upsert_filings(self, filings: Sequence[FilingReference]) -> None:
        """Persist discovered filing metadata idempotently."""


class RagEngine(Protocol):
    async def index_filing(self, *, filing: FilingReference, raw_document: str) -> None:
        """Parse, chunk, embed and persist a filing for retrieval."""

    async def query(self, request: ResearchQuery) -> Sequence[Citation]:
        """Retrieve grounded passages from indexed filing chunks."""
