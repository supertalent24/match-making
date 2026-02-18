"""employment_type as array, skills.is_requirement

Revision ID: 20260218_employment_skills
Revises: a1b2c3d4e5f6
Create Date: 2026-02-18

- normalized_jobs.employment_type: single enum -> ARRAY(employment_type_enum)
- skills.is_requirement: new boolean, default false (backfill false for existing rows)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260218_employment_skills"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) employment_type: single enum -> array of enum
    op.execute(
        """
        ALTER TABLE normalized_jobs
        ALTER COLUMN employment_type TYPE employment_type_enum[]
        USING CASE
            WHEN employment_type IS NOT NULL THEN ARRAY[employment_type]
            ELSE NULL
        END
        """
    )

    # 2) skills.is_requirement
    op.add_column(
        "skills",
        sa.Column("is_requirement", sa.Boolean(), nullable=True),
    )
    op.execute("UPDATE skills SET is_requirement = false WHERE is_requirement IS NULL")
    op.alter_column(
        "skills",
        "is_requirement",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )


def downgrade() -> None:
    # employment_type: array -> single (take first element)
    op.execute(
        """
        ALTER TABLE normalized_jobs
        ALTER COLUMN employment_type TYPE employment_type_enum
        USING employment_type[1]
        """
    )

    op.drop_column("skills", "is_requirement")
