"""Fix compensation stored as bare thousands (e.g. 60 instead of 60000).

Revision ID: 20260219_comp_k
Revises: 20260218_match_sim
Create Date: 2026-02-19

One-time data fix: normalized_candidates with compensation_min or compensation_max
below 1000 were parsed from strings like "60-70k" where the first number had no
"k" suffix. Multiply those values by 1000 so they represent yearly amounts.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260219_comp_k"
down_revision: str | None = "20260218_match_sim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE normalized_candidates
        SET
            compensation_min = compensation_min * 1000
        WHERE compensation_min IS NOT NULL AND compensation_min < 1000
    """)
    op.execute("""
        UPDATE normalized_candidates
        SET
            compensation_max = compensation_max * 1000
        WHERE compensation_max IS NOT NULL AND compensation_max < 1000
    """)


def downgrade() -> None:
    # Cannot reliably reverse: we don't know which rows were scaled
    pass
