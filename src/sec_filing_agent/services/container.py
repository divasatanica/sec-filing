"""Application composition root.

Replace only this module's placeholder adapters when wiring real infrastructure.
"""

from dataclasses import dataclass

from sec_filing_agent.core.config import Settings
from sec_filing_agent.services.contracts import FilingRepository, RagEngine, SecFilingsGateway
from sec_filing_agent.services.ingestion import IngestionService
from sec_filing_agent.services.placeholders import (
    PlaceholderFilingRepository,
    PlaceholderRagEngine,
    PlaceholderSecFilingsGateway,
)


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    gateway: SecFilingsGateway
    repository: FilingRepository
    rag_engine: RagEngine
    ingestion: IngestionService


def build_container(settings: Settings) -> ServiceContainer:
    """Construct service dependencies for one process.

    TODO: instantiate your real adapters here, then pass the same adapters to
    `IngestionService`. Keep routers unaware of vendor SDKs or database clients.
    """

    gateway = PlaceholderSecFilingsGateway()
    repository = PlaceholderFilingRepository()
    rag_engine = PlaceholderRagEngine()
    ingestion = IngestionService(gateway=gateway, repository=repository, rag_engine=rag_engine)
    return ServiceContainer(
        settings=settings,
        gateway=gateway,
        repository=repository,
        rag_engine=rag_engine,
        ingestion=ingestion,
    )
