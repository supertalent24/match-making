"""add normalized_job narratives and normalized_json

Revision ID: a1b2c3d4e5f6
Revises: 8ad874f86ef5
Create Date: 2026-02-18

Adds to normalized_jobs:
- normalized_json (JSONB) for full LLM output
- narrative_experience, narrative_domain, narrative_personality,
  narrative_impact, narrative_technical, narrative_role (TEXT) for vector matching
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "8ad874f86ef5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("normalized_jobs", sa.Column("normalized_json", JSONB, nullable=True))
    op.add_column("normalized_jobs", sa.Column("narrative_experience", sa.Text(), nullable=True))
    op.add_column("normalized_jobs", sa.Column("narrative_domain", sa.Text(), nullable=True))
    op.add_column("normalized_jobs", sa.Column("narrative_personality", sa.Text(), nullable=True))
    op.add_column("normalized_jobs", sa.Column("narrative_impact", sa.Text(), nullable=True))
    op.add_column("normalized_jobs", sa.Column("narrative_technical", sa.Text(), nullable=True))
    op.add_column("normalized_jobs", sa.Column("narrative_role", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("normalized_jobs", "narrative_role")
    op.drop_column("normalized_jobs", "narrative_technical")
    op.drop_column("normalized_jobs", "narrative_impact")
    op.drop_column("normalized_jobs", "narrative_personality")
    op.drop_column("normalized_jobs", "narrative_domain")
    op.drop_column("normalized_jobs", "narrative_experience")
    op.drop_column("normalized_jobs", "normalized_json")
