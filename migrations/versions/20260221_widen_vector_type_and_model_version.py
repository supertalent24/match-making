"""Widen vector_type and model_version columns on vector tables.

Revision ID: 20260221_vec_cols
Revises: 20260220_exp_cap
Create Date: 2026-02-21

- candidate_vectors.vector_type: VARCHAR(50) -> VARCHAR(150)
- candidate_vectors.model_version: VARCHAR(50) -> VARCHAR(100)
- job_vectors.vector_type: VARCHAR(50) -> VARCHAR(150)
- job_vectors.model_version: VARCHAR(50) -> VARCHAR(100)

Skill-derived vector_type keys (e.g. "skill_business_development_strategy_&_sales_enablement")
can exceed 50 chars.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260221_vec_cols"
down_revision: str | None = "20260220_exp_cap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "candidate_vectors",
        "vector_type",
        type_=sa.String(150),
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    op.alter_column(
        "candidate_vectors",
        "model_version",
        type_=sa.String(100),
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    op.alter_column(
        "job_vectors",
        "vector_type",
        type_=sa.String(150),
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    op.alter_column(
        "job_vectors",
        "model_version",
        type_=sa.String(100),
        existing_type=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "job_vectors",
        "model_version",
        type_=sa.String(50),
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "job_vectors",
        "vector_type",
        type_=sa.String(50),
        existing_type=sa.String(150),
        existing_nullable=False,
    )
    op.alter_column(
        "candidate_vectors",
        "model_version",
        type_=sa.String(50),
        existing_type=sa.String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "candidate_vectors",
        "vector_type",
        type_=sa.String(50),
        existing_type=sa.String(150),
        existing_nullable=False,
    )
