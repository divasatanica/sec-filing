"""Normalization of annual SEC companyfacts into audit-friendly fiscal metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sec_filing_agent.models import FilingMetadata, FiscalMetrics, MetricValue

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"}
CURRENCY_UNITS = ("USD", "EUR", "CAD", "GBP", "JPY", "CHF", "AUD", "CNY")

CONCEPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "revenue": {"us-gaap": ("Revenues",), "ifrs-full": ("Revenue",)},
    "revenueFromContract": {
        "us-gaap": ("RevenueFromContractWithCustomerExcludingAssessedTax",),
        "ifrs-full": (),
    },
    "costOfRevenue": {"us-gaap": ("CostOfRevenue",), "ifrs-full": ("CostOfSales",)},
    "costOfGoodsAndServices": {"us-gaap": ("CostOfGoodsAndServicesSold",), "ifrs-full": ()},
    "grossProfit": {"us-gaap": ("GrossProfit",), "ifrs-full": ("GrossProfit",)},
    "operatingIncome": {"us-gaap": ("OperatingIncomeLoss",), "ifrs-full": ("OperatingProfitLoss",)},
    "netIncome": {"us-gaap": ("NetIncomeLoss",), "ifrs-full": ("ProfitLoss",)},
    "epsBasic": {
        "us-gaap": ("EarningsPerShareBasic",),
        "ifrs-full": ("BasicEarningsLossPerShare",),
    },
    "epsDiluted": {
        "us-gaap": ("EarningsPerShareDiluted",),
        "ifrs-full": ("DilutedEarningsLossPerShare",),
    },
    "totalAssets": {"us-gaap": ("Assets",), "ifrs-full": ("Assets",)},
    "totalLiabilities": {"us-gaap": ("Liabilities",), "ifrs-full": ("Liabilities",)},
    "currentAssets": {"us-gaap": ("AssetsCurrent",), "ifrs-full": ("CurrentAssets",)},
    "currentLiabilities": {
        "us-gaap": ("LiabilitiesCurrent",),
        "ifrs-full": ("LiabilitiesCurrent",),
    },
    "stockholdersEquity": {"us-gaap": ("StockholdersEquity",), "ifrs-full": ("Equity",)},
    "operatingCashFlow": {
        "us-gaap": ("NetCashProvidedByUsedInOperatingActivities",),
        "ifrs-full": ("CashFlowsFromUsedInOperatingActivities",),
    },
    "capex": {
        "us-gaap": ("PaymentsToAcquirePropertyPlantAndEquipment",),
        "ifrs-full": ("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",),
    },
    "longTermDebt": {"us-gaap": ("LongTermDebtNoncurrent",), "ifrs-full": ()},
    "rAndD": {
        "us-gaap": ("ResearchAndDevelopmentExpense",),
        "ifrs-full": ("ResearchAndDevelopmentExpense",),
    },
    "sGAndA": {
        "us-gaap": ("SellingGeneralAndAdministrativeExpense",),
        "ifrs-full": ("SellingGeneralAndAdministrativeExpense",),
    },
    "revenueBySegment": {
        "us-gaap": ("RevenueFromExternalCustomersAttributedToReportableSegmentsByGeographicAreas",),
        "ifrs-full": (),
    },
}


@dataclass
class XbrlExtractionResult:
    fiscal_metrics: list[FiscalMetrics]
    warnings: list[str]


def extract_annual_metrics(
    company_facts: dict[str, Any],
    *,
    ticker: str,
    selected_filings: list[FilingMetadata],
    max_years: int = 3,
) -> XbrlExtractionResult:
    """Return up to ``max_years`` of FY facts, preferring selected filings when possible."""

    all_facts = company_facts.get("facts")
    if not isinstance(all_facts, dict):
        return XbrlExtractionResult([], ["companyfacts_missing_facts"])

    namespace = _choose_namespace(all_facts, selected_filings)
    if namespace is None:
        return XbrlExtractionResult([], ["companyfacts_no_supported_annual_facts"])

    namespace_facts = all_facts.get(namespace)
    if not isinstance(namespace_facts, dict):  # Defensive after _choose_namespace.
        return XbrlExtractionResult([], [f"companyfacts_invalid_namespace:{namespace}"])

    preferred_accessions = {filing.accession_number for filing in selected_filings}
    by_year: dict[int, dict[str, MetricValue]] = {}
    for metric_key, namespace_concepts in CONCEPTS.items():
        for concept in _concepts_for_namespace(namespace_concepts, namespace):
            selected = _select_concept_values(
                namespace_facts.get(concept),
                namespace=namespace,
                concept=concept,
                preferred_accessions=preferred_accessions,
            )
            if selected:
                for fiscal_year, value in selected.items():
                    by_year.setdefault(fiscal_year, {})[metric_key] = value
                break

    if not by_year:
        return XbrlExtractionResult([], [f"companyfacts_no_mapped_metrics:{namespace}"])

    metrics = []
    for fiscal_year in sorted(by_year, reverse=True)[:max_years]:
        facts = by_year[fiscal_year]
        _add_derived_facts(facts)
        metrics.append(FiscalMetrics(ticker=ticker, fiscal_year=fiscal_year, facts=facts))
    return XbrlExtractionResult(metrics, [])


def _choose_namespace(
    all_facts: dict[str, Any], selected_filings: list[FilingMetadata]
) -> str | None:
    candidates = [namespace for namespace in ("us-gaap", "ifrs-full") if namespace in all_facts]
    candidates.extend(
        namespace
        for namespace in all_facts
        if namespace not in {"us-gaap", "ifrs-full", "dei"}
        and isinstance(all_facts[namespace], dict)
    )
    preferred_accessions = {filing.accession_number for filing in selected_filings}
    best_namespace: str | None = None
    best_score = 0
    for namespace in candidates:
        namespace_facts = all_facts.get(namespace)
        if not isinstance(namespace_facts, dict):
            continue
        score = 0
        for metric_concepts in CONCEPTS.values():
            for concept in _concepts_for_namespace(metric_concepts, namespace):
                score += len(
                    _select_concept_values(
                        namespace_facts.get(concept),
                        namespace=namespace,
                        concept=concept,
                        preferred_accessions=preferred_accessions,
                    )
                )
        if score > best_score:
            best_namespace = namespace
            best_score = score
    return best_namespace


def _concepts_for_namespace(
    concepts_by_namespace: dict[str, tuple[str, ...]], namespace: str
) -> tuple[str, ...]:
    configured = concepts_by_namespace.get(namespace)
    if configured is not None:
        return configured
    # Custom namespaces occasionally reuse a standard concept name. Try both mappings,
    # but never pretend that an absent custom concept is a standard fact.
    return tuple(
        dict.fromkeys(
            (
                *concepts_by_namespace.get("us-gaap", ()),
                *concepts_by_namespace.get("ifrs-full", ()),
            )
        )
    )


def _select_concept_values(
    concept_payload: Any,
    *,
    namespace: str,
    concept: str,
    preferred_accessions: set[str],
) -> dict[int, MetricValue]:
    if not isinstance(concept_payload, dict):
        return {}
    units = concept_payload.get("units")
    if not isinstance(units, dict):
        return {}

    # Prefer a currency unit for monetary concepts, but retain non-currency units such
    # as USD/shares for EPS instead of dropping the metric entirely.
    unit_names = [unit for unit in CURRENCY_UNITS if unit in units]
    unit_names.extend(unit for unit in units if unit not in unit_names)
    for unit in unit_names:
        facts = units.get(unit)
        if not isinstance(facts, list):
            continue
        by_year: dict[int, list[dict[str, Any]]] = {}
        for fact in facts:
            if not _is_annual_fact(fact):
                continue
            try:
                fiscal_year = int(fact["fy"])
                float(fact["val"])
            except (KeyError, TypeError, ValueError):
                continue
            by_year.setdefault(fiscal_year, []).append(fact)
        if by_year:
            return {
                fiscal_year: _metric_value(
                    _preferred_fact(candidates, preferred_accessions),
                    unit=unit,
                    namespace=namespace,
                    concept=concept,
                )
                for fiscal_year, candidates in by_year.items()
            }
    return {}


def _is_annual_fact(fact: Any) -> bool:
    return (
        isinstance(fact, dict)
        and str(fact.get("fp", "")).upper() == "FY"
        and str(fact.get("form", "")).upper() in ANNUAL_FORMS
    )


def _preferred_fact(
    candidates: list[dict[str, Any]], preferred_accessions: set[str]
) -> dict[str, Any]:
    # FY alone is not unique: amended filings and restatements can overlap. A fact from
    # a selected filing wins first; frame and filing date then provide deterministic ties.
    return max(
        candidates,
        key=lambda fact: (
            str(fact.get("accn", "")) in preferred_accessions,
            bool(fact.get("frame")),
            str(fact.get("filed", "")),
            str(fact.get("end", "")),
            str(fact.get("start", "")),
        ),
    )


def _metric_value(fact: dict[str, Any], *, unit: str, namespace: str, concept: str) -> MetricValue:
    return MetricValue(
        value=float(fact["val"]),
        unit=unit,
        end_date=_parse_date(fact.get("end")),
        filed=_parse_date(fact.get("filed")),
        accession_number=_string_or_none(fact.get("accn")),
        namespace=namespace,
        concept=concept,
        form=_string_or_none(fact.get("form")),
        fiscal_period=_string_or_none(fact.get("fp")),
        frame=_string_or_none(fact.get("frame")),
        start_date=_parse_date(fact.get("start")),
    )


def _add_derived_facts(facts: dict[str, MetricValue]) -> None:
    if "revenue" not in facts and "revenueFromContract" in facts:
        facts["revenue"] = facts["revenueFromContract"].model_copy()
    if "costOfRevenue" not in facts and "costOfGoodsAndServices" in facts:
        facts["costOfRevenue"] = facts["costOfGoodsAndServices"].model_copy()

    operating_cash_flow = facts.get("operatingCashFlow")
    capex = facts.get("capex")
    # Mixing USD operating cash flow with (for example) EUR capex would create a
    # plausible-looking but invalid free-cash-flow value, so refuse to derive it.
    if operating_cash_flow is None or capex is None or operating_cash_flow.unit != capex.unit:
        return
    facts["freeCashFlow"] = MetricValue(
        value=operating_cash_flow.value - abs(capex.value),
        unit=operating_cash_flow.unit,
        end_date=operating_cash_flow.end_date,
        filed=operating_cash_flow.filed,
        accession_number=operating_cash_flow.accession_number,
        derived=True,
        namespace=operating_cash_flow.namespace,
        concept="derived:operatingCashFlow-capex",
        form=operating_cash_flow.form,
        fiscal_period=operating_cash_flow.fiscal_period,
        frame=operating_cash_flow.frame,
        start_date=operating_cash_flow.start_date,
    )


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
