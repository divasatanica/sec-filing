"""Add persisted filing cleanings and chunks.

Revision ID: c3d6e8f1a2b4
Revises: f4b7a3c9d214
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3d6e8f1a2b4"
down_revision: str | Sequence[str] | None = "f4b7a3c9d214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "filing_section_cleanings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("content_clean", sa.Text(), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_indexable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exclusion_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "cleaning_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["section_id"], ["filing_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section_id", name="uq_filing_section_cleanings_section"),
    )
    op.create_index(
        op.f("ix_filing_section_cleanings_content_hash"),
        "filing_section_cleanings",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_filing_section_cleanings_is_indexable"),
        "filing_section_cleanings",
        ["is_indexable"],
        unique=False,
    )
    op.create_index(
        op.f("ix_filing_section_cleanings_section_id"),
        "filing_section_cleanings",
        ["section_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_filing_section_cleanings_source_content_hash"),
        "filing_section_cleanings",
        ["source_content_hash"],
        unique=False,
    )

    op.create_table(
        "filing_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cleaning_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["cleaning_id"], ["filing_section_cleanings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cleaning_id", "chunk_index", name="uq_filing_chunks_cleaning_index"),
    )
    op.create_index(op.f("ix_filing_chunks_cleaning_id"), "filing_chunks", ["cleaning_id"], unique=False)
    op.create_index(op.f("ix_filing_chunks_content_hash"), "filing_chunks", ["content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_filing_chunks_content_hash"), table_name="filing_chunks")
    op.drop_index(op.f("ix_filing_chunks_cleaning_id"), table_name="filing_chunks")
    op.drop_table("filing_chunks")
    op.drop_index(
        op.f("ix_filing_section_cleanings_source_content_hash"),
        table_name="filing_section_cleanings",
    )
    op.drop_index(
        op.f("ix_filing_section_cleanings_section_id"), table_name="filing_section_cleanings"
    )
    op.drop_index(
        op.f("ix_filing_section_cleanings_is_indexable"), table_name="filing_section_cleanings"
    )
    op.drop_index(
        op.f("ix_filing_section_cleanings_content_hash"), table_name="filing_section_cleanings"
    )
    op.drop_table("filing_section_cleanings")
