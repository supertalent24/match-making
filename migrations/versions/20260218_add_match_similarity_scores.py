"""Add role/domain/culture_similarity_score to matches.

Revision ID: 20260218_match_sim
Revises: 20260218_employment_skills
Create Date: 2026-02-18

- matches.role_similarity_score, domain_similarity_score, culture_similarity_score (Float 0-1)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260218_match_sim"
down_revision: str | None = "20260218_employment_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("role_similarity_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("domain_similarity_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("culture_similarity_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("matches", "culture_similarity_score")
    op.drop_column("matches", "domain_similarity_score")
    op.drop_column("matches", "role_similarity_score")
