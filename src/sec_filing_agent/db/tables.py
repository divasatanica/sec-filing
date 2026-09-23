from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Company(Base):
    """SEC 公司主体；CIK 是稳定主键，ticker 不是。"""

    __tablename__ = "companies"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class CompanyTicker(Base):
    """ticker 与 CIK 的关联，支持未来保留 ticker 历史。"""

    __tablename__ = "company_tickers"
    __table_args__ = (UniqueConstraint("ticker", "cik", name="uq_company_tickers_ticker_cik"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cik: Mapped[str] = mapped_column(
        ForeignKey("companies.cik", ondelete="RESTRICT"),
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    exchange: Mapped[str | None] = mapped_column(String(50))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class Filing(Base):
    """每一份 SEC 申报的元数据；accession number 全局唯一。"""

    __tablename__ = "filings"

    accession_number: Mapped[str] = mapped_column(String(30), primary_key=True)
    cik: Mapped[str] = mapped_column(
        ForeignKey("companies.cik", ondelete="RESTRICT"),
        index=True,
    )
    form_type: Mapped[str] = mapped_column(String(20), index=True)
    filing_date: Mapped[date | None] = mapped_column(Date, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, index=True)

    primary_document: Mapped[str | None] = mapped_column(String(500))
    html_url: Mapped[str] = mapped_column(Text)
    archive_directory_url: Mapped[str] = mapped_column(Text)

    selection_reason: Mapped[str] = mapped_column(String(32), default="requested")
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class FilingSection(Base):
    """Filing 中解析出的原始 Item section。"""

    __tablename__ = "filing_sections"
    __table_args__ = (
        UniqueConstraint(
            "accession_number",
            "item_code",
            "parser_version",
            name="uq_filing_sections_accession_item_parser",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accession_number: Mapped[str] = mapped_column(
        ForeignKey("filings.accession_number", ondelete="CASCADE"),
        index=True,
    )
    item_code: Mapped[str] = mapped_column(String(30), index=True)
    item_label: Mapped[str] = mapped_column(String(500))

    # 永远保存解析得到的完整原文；RAG 清洗文本以后另存。
    content_raw: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    document_kind: Mapped[str] = mapped_column(String(30))

    source_start: Mapped[int | None] = mapped_column(Integer)
    source_end: Mapped[int | None] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)

    parser_version: Mapped[str] = mapped_column(String(50), default="v1")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class FinancialFact(Base):
    """一条可审计的 XBRL 财务事实。"""

    __tablename__ = "financial_facts"
    __table_args__ = (
        UniqueConstraint(
            "accession_number",
            "metric_key",
            "unit",
            "start_date",
            "end_date",
            "concept",
            name="uq_financial_facts_natural_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 用字段组合计算出的 SHA-256；处理 PostgreSQL 中 NULL 不参与唯一约束的问题。
    fact_key: Mapped[str] = mapped_column(String(64), unique=True)

    accession_number: Mapped[str] = mapped_column(
        ForeignKey("filings.accession_number", ondelete="CASCADE"),
        index=True,
    )
    metric_key: Mapped[str] = mapped_column(String(100), index=True)
    namespace: Mapped[str | None] = mapped_column(String(100))
    concept: Mapped[str | None] = mapped_column(String(200))

    # 财务数值不要使用 float；入库时用 Decimal(str(value)) 转换。
    value_numeric: Mapped[Decimal] = mapped_column(Numeric(36, 10))
    unit: Mapped[str] = mapped_column(String(30))

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(10))
    form_type: Mapped[str | None] = mapped_column(String(20))
    filed_date: Mapped[date | None] = mapped_column(Date)
    frame: Mapped[str | None] = mapped_column(String(100))
    is_instant: Mapped[bool] = mapped_column(Boolean, default=False)
    derived: Mapped[bool] = mapped_column(Boolean, default=False)

    source_url: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class IngestionRun(Base):
    """一次抓取、解析与入库任务的审计记录。"""

    __tablename__ = "ingestion_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    filings_discovered: Mapped[int] = mapped_column(Integer, default=0)
    filings_saved: Mapped[int] = mapped_column(Integer, default=0)
    sections_saved: Mapped[int] = mapped_column(Integer, default=0)
    facts_saved: Mapped[int] = mapped_column(Integer, default=0)

    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
