"""Safe defaults which document the adapters that must be supplied before use."""

from collections.abc import Sequence
from datetime import date

from sec_filing_agent.core.errors import CoreNotConfiguredError
from sec_filing_agent.domain.filings import FilingForm, FilingReference
from sec_filing_agent.domain.research import Citation, ResearchQuery


class PlaceholderSecFilingsGateway:
    async def discover_filings(
        self,
        *,
        instrument: str,
        forms: Sequence[FilingForm],
        from_date: date | None,
        to_date: date | None,
    ) -> Sequence[FilingReference]:
        raise CoreNotConfiguredError(
            "SEC gateway is not configured. Implement SecFilingsGateway first."
        )

    async def download_filing(self, *, accession_number: str) -> str:
        raise CoreNotConfiguredError(
            "SEC gateway is not configured. Implement SecFilingsGateway first."
        )


class PlaceholderFilingRepository:
    async def list_filings(
        self,
        *,
        instrument: str,
        forms: Sequence[FilingForm],
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[FilingReference], str | None]:
        raise CoreNotConfiguredError(
            "Filing repository is not configured. Implement FilingRepository first."
        )

    async def get_filing(self, *, accession_number: str) -> FilingReference:
        raise CoreNotConfiguredError(
            "Filing repository is not configured. Implement FilingRepository first."
        )

    async def upsert_filings(self, filings: Sequence[FilingReference]) -> None:
        raise CoreNotConfiguredError(
            "Filing repository is not configured. Implement FilingRepository first."
        )


class PlaceholderRagEngine:
    async def index_filing(self, *, filing: FilingReference, raw_document: str) -> None:
        raise CoreNotConfiguredError("RAG engine is not configured. Implement RagEngine first.")

    async def query(self, request: ResearchQuery) -> Sequence[Citation]:
        raise CoreNotConfiguredError("RAG engine is not configured. Implement RagEngine first.")
