"""Add expected_capability to job_required_skills.

Revision ID: 20260220_exp_cap
Revises: 20260219_comp_k
Create Date: 2026-02-20

- job_required_skills.expected_capability (TEXT, nullable): what the ideal
  candidate should be capable of with this skill, inferred from job description.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260220_exp_cap"
down_revision: str | None = "20260219_comp_k"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_required_skills",
        sa.Column("expected_capability", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_required_skills", "expected_capability")
