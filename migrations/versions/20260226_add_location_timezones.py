"""Add location_timezones lookup table.

Revision ID: 20260226_location_tz
Revises: 20260226_min_level
Create Date: 2026-02-26

Caches (city, country) -> IANA timezone mappings resolved by LLM.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260226_location_tz"
down_revision: str | None = "20260226_min_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_timezones",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("utc_offset", sa.String(10), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="high"),
        sa.Column("resolved_by", sa.String(20), nullable=False, server_default="llm"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("city", "country", name="uq_location_timezones_city_country"),
    )
    op.create_index("idx_location_tz_country", "location_timezones", ["country"])


def downgrade() -> None:
    op.drop_index("idx_location_tz_country", table_name="location_timezones")
    op.drop_table("location_timezones")
