"""add_cv_text_pdf_field

Revision ID: b7738458d5b8
Revises: 119428e424c7
Create Date: 2026-02-13 11:49:32.588910+00:00

Adds fields to store PDF-extracted text separately from Airtable text:
- cv_text_pdf: Text extracted from PDF attachment
- cv_extraction_pages: Number of pages in the PDF

This enables dual-source CV processing where both Airtable text and
PDF-extracted text are merged during normalization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7738458d5b8"
down_revision: str | None = "119428e424c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add cv_text_pdf and cv_extraction_pages to raw_candidates."""
    op.add_column("raw_candidates", sa.Column("cv_text_pdf", sa.Text(), nullable=True))
    op.add_column("raw_candidates", sa.Column("cv_extraction_pages", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove cv_text_pdf and cv_extraction_pages from raw_candidates."""
    op.drop_column("raw_candidates", "cv_extraction_pages")
    op.drop_column("raw_candidates", "cv_text_pdf")
