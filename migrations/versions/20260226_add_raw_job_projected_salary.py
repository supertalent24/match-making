"""Add projected_salary column to raw_jobs.

Revision ID: 20260226_proj_sal
Revises: 20260226_location_tz
Create Date: 2026-02-26

Stores the recruiter-provided projected salary range from Airtable ATS.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260226_proj_sal"
down_revision: str | None = "20260226_location_tz"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_jobs", sa.Column("projected_salary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_jobs", "projected_salary")
