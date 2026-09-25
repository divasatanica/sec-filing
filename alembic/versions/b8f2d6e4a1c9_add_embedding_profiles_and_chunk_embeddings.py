"""Add embedding profiles, persisted embeddings, and direct company scopes.

Revision ID: b8f2d6e4a1c9
Revises: a7e9c2d4f6b8
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

from alembic import op

revision: str = "b8f2d6e4a1c9"
down_revision: str | Sequence[str] | None = "a7e9c2d4f6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _add_and_backfill_company_scopes()

    op.create_table(
        "embedding_model_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("revision", sa.String(length=200), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_name",
            "revision",
            "dimensions",
            name="uq_embedding_model_profiles_identity",
        ),
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), nullable=False),
        sa.Column("model_profile_id", sa.Integer(), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        # An unconstrained vector column permits model profiles with different
        # dimensions. Queries/indexes must be scoped to one profile.
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["filing_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cik"], ["companies.cik"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["model_profile_id"],
            ["embedding_model_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id",
            "model_profile_id",
            name="uq_chunk_embeddings_chunk_profile",
        ),
    )
    op.create_index(
        op.f("ix_chunk_embeddings_chunk_id"),
        "chunk_embeddings",
        ["chunk_id"],
    )
    op.create_index(
        "ix_chunk_embeddings_model_profile_cik",
        "chunk_embeddings",
        ["model_profile_id", "cik"],
    )
    _create_company_scope_triggers()


def downgrade() -> None:
    _drop_company_scope_triggers()
    op.drop_index("ix_chunk_embeddings_model_profile_cik", table_name="chunk_embeddings")
    op.drop_index(op.f("ix_chunk_embeddings_chunk_id"), table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
    op.drop_table("embedding_model_profiles")
    op.drop_index(op.f("ix_financial_facts_cik"), table_name="financial_facts")
    op.drop_constraint("fk_financial_facts_cik_companies", "financial_facts", type_="foreignkey")
    op.drop_column("financial_facts", "cik")
    op.drop_index(op.f("ix_filing_chunks_cik"), table_name="filing_chunks")
    op.drop_constraint("fk_filing_chunks_cik_companies", "filing_chunks", type_="foreignkey")
    op.drop_column("filing_chunks", "cik")


def _add_and_backfill_company_scopes() -> None:
    """Materialize the owning filing's CIK on hot fact tables."""

    op.add_column("filing_chunks", sa.Column("cik", sa.String(length=10), nullable=True))
    op.execute(
        """
        UPDATE filing_chunks AS chunk
        SET cik = filing.cik
        FROM filing_section_cleanings AS cleaning
        JOIN filing_sections AS section ON section.id = cleaning.section_id
        JOIN filings AS filing ON filing.accession_number = section.accession_number
        WHERE cleaning.id = chunk.cleaning_id
        """
    )
    op.alter_column("filing_chunks", "cik", nullable=False)
    op.create_foreign_key(
        "fk_filing_chunks_cik_companies",
        "filing_chunks",
        "companies",
        ["cik"],
        ["cik"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_filing_chunks_cik"), "filing_chunks", ["cik"])

    op.add_column("financial_facts", sa.Column("cik", sa.String(length=10), nullable=True))
    op.execute(
        """
        UPDATE financial_facts AS fact
        SET cik = filing.cik
        FROM filings AS filing
        WHERE filing.accession_number = fact.accession_number
        """
    )
    op.alter_column("financial_facts", "cik", nullable=False)
    op.create_foreign_key(
        "fk_financial_facts_cik_companies",
        "financial_facts",
        "companies",
        ["cik"],
        ["cik"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_financial_facts_cik"), "financial_facts", ["cik"])


def _create_company_scope_triggers() -> None:
    """Derive and verify the redundant CIK scopes on every write."""

    op.execute(
        """
        CREATE FUNCTION enforce_filing_chunk_cik()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_cik varchar(10);
        BEGIN
            SELECT filing.cik
            INTO expected_cik
            FROM filing_section_cleanings AS cleaning
            JOIN filing_sections AS section ON section.id = cleaning.section_id
            JOIN filings AS filing ON filing.accession_number = section.accession_number
            WHERE cleaning.id = NEW.cleaning_id;

            IF expected_cik IS NULL THEN
                RAISE EXCEPTION 'No filing CIK found for filing_chunks.cleaning_id=%', NEW.cleaning_id;
            END IF;
            IF NEW.cik IS NOT NULL AND NEW.cik <> expected_cik THEN
                RAISE EXCEPTION 'filing_chunks.cik must match its owning filing';
            END IF;

            NEW.cik := expected_cik;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER enforce_filing_chunk_cik_trigger
        BEFORE INSERT OR UPDATE OF cleaning_id, cik ON filing_chunks
        FOR EACH ROW EXECUTE FUNCTION enforce_filing_chunk_cik();
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_financial_fact_cik()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_cik varchar(10);
        BEGIN
            SELECT cik INTO expected_cik
            FROM filings
            WHERE accession_number = NEW.accession_number;

            IF expected_cik IS NULL THEN
                RAISE EXCEPTION 'No filing CIK found for financial_facts.accession_number=%', NEW.accession_number;
            END IF;
            IF NEW.cik IS NOT NULL AND NEW.cik <> expected_cik THEN
                RAISE EXCEPTION 'financial_facts.cik must match its owning filing';
            END IF;

            NEW.cik := expected_cik;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER enforce_financial_fact_cik_trigger
        BEFORE INSERT OR UPDATE OF accession_number, cik ON financial_facts
        FOR EACH ROW EXECUTE FUNCTION enforce_financial_fact_cik();
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_chunk_embedding_cik()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_cik varchar(10);
        BEGIN
            SELECT cik INTO expected_cik
            FROM filing_chunks
            WHERE id = NEW.chunk_id;

            IF expected_cik IS NULL THEN
                RAISE EXCEPTION 'No CIK found for chunk_embeddings.chunk_id=%', NEW.chunk_id;
            END IF;
            IF NEW.cik IS NOT NULL AND NEW.cik <> expected_cik THEN
                RAISE EXCEPTION 'chunk_embeddings.cik must match its owning chunk';
            END IF;

            NEW.cik := expected_cik;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER enforce_chunk_embedding_cik_trigger
        BEFORE INSERT OR UPDATE OF chunk_id, cik ON chunk_embeddings
        FOR EACH ROW EXECUTE FUNCTION enforce_chunk_embedding_cik();
        """
    )


def _drop_company_scope_triggers() -> None:
    op.execute("DROP TRIGGER enforce_chunk_embedding_cik_trigger ON chunk_embeddings")
    op.execute("DROP FUNCTION enforce_chunk_embedding_cik()")
    op.execute("DROP TRIGGER enforce_financial_fact_cik_trigger ON financial_facts")
    op.execute("DROP FUNCTION enforce_financial_fact_cik()")
    op.execute("DROP TRIGGER enforce_filing_chunk_cik_trigger ON filing_chunks")
    op.execute("DROP FUNCTION enforce_filing_chunk_cik()")
