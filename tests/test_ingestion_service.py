import asyncio
from datetime import date

from sec_filing_agent.db.tables import FinancialFact
from sec_filing_agent.models import FilingMetadata, FiscalMetrics, MetricValue
from sec_filing_agent.services.ingestion_service import (
    CollectedFinancialFact,
    IngestionService,
    _financial_fact_key,
    _group_facts_by_accession,
)


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add_all(self, values: object) -> None:
        self.added.extend(values)  # type: ignore[arg-type]

    async def commit(self) -> None:
        self.commit_count += 1


class _ScalarResult:
    def scalar_one_or_none(self) -> None:
        return None


class FactRecordingSession:
    def __init__(self) -> None:
        self.added: list[FinancialFact] = []

    async def execute(self, statement: object) -> _ScalarResult:
        del statement
        return _ScalarResult()

    def add(self, value: FinancialFact) -> None:
        self.added.append(value)


def test_groups_facts_by_accession_and_warns_for_missing_provenance() -> None:
    revenue = MetricValue(
        value=100.0,
        unit="USD",
        accession_number="0000000001-25-000001",
        namespace="us-gaap",
        concept="Revenues",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    missing_accession = MetricValue(value=10.0, unit="USD")
    fiscal_metrics = [
        FiscalMetrics(
            ticker="TEST",
            fiscal_year=2024,
            facts={"revenue": revenue, "rAndD": missing_accession},
        )
    ]

    grouped, warnings = _group_facts_by_accession(fiscal_metrics)

    assert list(grouped) == ["0000000001-25-000001"]
    assert grouped["0000000001-25-000001"][0].metric_key == "revenue"
    assert warnings == ["financial_fact_missing_accession:rAndD:FY2024"]


def test_financial_fact_key_uses_fact_identity_not_value() -> None:
    metric = MetricValue(
        value=100.0,
        unit="USD",
        concept="Revenues",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    restated_metric = metric.model_copy(update={"value": 200.0})
    other_period = metric.model_copy(update={"end_date": date(2025, 1, 1)})

    key = _financial_fact_key("0000000001-25-000001", "revenue", metric)

    assert key == _financial_fact_key("0000000001-25-000001", "revenue", restated_metric)
    assert key != _financial_fact_key("0000000001-25-000001", "revenue", other_period)


def test_ingestion_run_records_start_and_completion() -> None:
    async def scenario() -> None:
        session = RecordingSession()
        service = IngestionService(session=session, collector=object())  # type: ignore[arg-type]

        runs = await service._start_runs(["TEST"])
        run = runs["TEST"]
        assert run.status == "running"
        assert session.added == [run]
        assert session.commit_count == 1

        await service._finish_run(
            run,
            status="completed",
            filings_discovered=1,
            filings_saved=1,
            sections_saved=5,
            facts_saved=3,
            warnings=[],
        )

        assert run.finished_at is not None
        assert run.status == "completed"
        assert run.filings_discovered == 1
        assert run.sections_saved == 5
        assert run.facts_saved == 3
        assert session.commit_count == 2

    asyncio.run(scenario())


def test_financial_fact_upsert_persists_the_filing_cik() -> None:
    async def scenario() -> None:
        filing = FilingMetadata(
            ticker="TEST",
            cik="0000123456",
            title="Test Company",
            form_type="10-K",
            accession_number="0000000001-25-000001",
            html_url="https://www.sec.gov/example",
            archive_directory_url="https://www.sec.gov/archive",
        )
        metric = MetricValue(
            value=100.0,
            unit="USD",
            accession_number=filing.accession_number,
            concept="Revenues",
            end_date=date(2024, 12, 31),
        )
        session = FactRecordingSession()
        service = IngestionService(session=session, collector=object())  # type: ignore[arg-type]

        await service._upsert_financial_fact(
            filing,
            CollectedFinancialFact(
                fiscal_year=2024,
                fiscal_period="FY",
                metric_key="revenue",
                metric=metric,
            ),
        )

        assert len(session.added) == 1
        assert session.added[0].cik == filing.cik

    asyncio.run(scenario())
