"""Add 'staff' value to seniority_enum.

Revision ID: 20260221_staff
Revises: 20260221_vec_cols
Create Date: 2026-02-21

Staff is a legitimate IC-track seniority level (distinct from Lead which is
management-track). The LLM naturally extracts it from CVs with titles like
"Staff Engineer".
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260221_staff"
down_revision: str | None = "20260221_vec_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE seniority_enum ADD VALUE IF NOT EXISTS 'staff' AFTER 'senior'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type.
    pass
