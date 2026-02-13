"""add_cv_extraction_fields

Revision ID: 119428e424c7
Revises: e14af2d1360d
Create Date: 2026-02-13 11:45:44.780058+00:00

Adds fields to track how CV text was extracted:
- cv_extraction_method: 'airtable', 'pdf_text', 'mistral_ocr', 'native', 'failed'
- cv_extraction_cost_usd: Cost of extraction (for PDF processing)
- cv_extraction_model: Model used (e.g., 'openai/gpt-4o-mini')
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "119428e424c7"
down_revision: str | None = "e14af2d1360d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add CV extraction tracking fields to raw_candidates."""
    # Create the enum type first
    cv_extraction_method_enum = sa.Enum(
        "AIRTABLE", "PDF_TEXT", "MISTRAL_OCR", "NATIVE", "FAILED", name="cv_extraction_method_enum"
    )
    cv_extraction_method_enum.create(op.get_bind(), checkfirst=True)

    # Add new columns
    op.add_column(
        "raw_candidates",
        sa.Column("cv_extraction_method", cv_extraction_method_enum, nullable=True),
    )
    op.add_column("raw_candidates", sa.Column("cv_extraction_cost_usd", sa.Float(), nullable=True))
    op.add_column(
        "raw_candidates", sa.Column("cv_extraction_model", sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    """Remove CV extraction tracking fields from raw_candidates."""
    op.drop_column("raw_candidates", "cv_extraction_model")
    op.drop_column("raw_candidates", "cv_extraction_cost_usd")
    op.drop_column("raw_candidates", "cv_extraction_method")

    # Drop the enum type
    sa.Enum(name="cv_extraction_method_enum").drop(op.get_bind(), checkfirst=True)
