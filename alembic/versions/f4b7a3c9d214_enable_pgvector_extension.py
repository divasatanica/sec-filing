"""Enable the PostgreSQL pgvector extension.

Revision ID: f4b7a3c9d214
Revises: e0692c2ea6dc
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b7a3c9d214"
down_revision: str | Sequence[str] | None = "e0692c2ea6dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable vector operations in this PostgreSQL database once."""

    # IF NOT EXISTS makes this safe when pgvector was enabled manually in pgAdmin.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Keep this database-level extension when rolling back application tables."""

    # Do not drop the extension: it may predate this migration or be used outside
    # this application's tables.
    return None
