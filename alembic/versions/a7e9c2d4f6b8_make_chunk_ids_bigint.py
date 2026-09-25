"""Make filing chunk IDs bigint.

Revision ID: a7e9c2d4f6b8
Revises: c3d6e8f1a2b4
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7e9c2d4f6b8"
down_revision: str | Sequence[str] | None = "c3d6e8f1a2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "filing_chunks",
        "id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.execute("ALTER SEQUENCE filing_chunks_id_seq AS BIGINT")


def downgrade() -> None:
    op.alter_column(
        "filing_chunks",
        "id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.execute("ALTER SEQUENCE filing_chunks_id_seq AS INTEGER")
