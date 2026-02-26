"""Add min_level to job_required_skills.

Revision ID: 20260226_min_level
Revises: 20260221_staff
Create Date: 2026-02-26

- job_required_skills.min_level (INTEGER, nullable): minimum proficiency level
  (1-10 scale) expected for this skill, inferred from job description.
- CHECK constraint: min_level IS NULL OR (min_level >= 1 AND min_level <= 10)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260226_min_level"
down_revision: str | None = "20260221_staff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_required_skills",
        sa.Column("min_level", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_min_level_range",
        "job_required_skills",
        "min_level IS NULL OR (min_level >= 1 AND min_level <= 10)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_min_level_range", "job_required_skills", type_="check")
    op.drop_column("job_required_skills", "min_level")
