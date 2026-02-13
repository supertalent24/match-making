"""update_skill_rating_to_1_10_scale

Revision ID: 8ad874f86ef5
Revises: b7738458d5b8
Create Date: 2026-02-13 12:02:33.015955+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ad874f86ef5"
down_revision: str | None = "b7738458d5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Update skill rating constraint from 1-5 to 1-10 scale."""
    # Drop old constraint (1-5 range)
    op.drop_constraint("ck_rating_range", "candidate_skills", type_="check")

    # Add new constraint (1-10 range)
    op.create_check_constraint(
        "ck_rating_range_10", "candidate_skills", "rating >= 1 AND rating <= 10"
    )


def downgrade() -> None:
    """Revert skill rating constraint back to 1-5 scale."""
    # Drop new constraint
    op.drop_constraint("ck_rating_range_10", "candidate_skills", type_="check")

    # Restore old constraint
    op.create_check_constraint("ck_rating_range", "candidate_skills", "rating >= 1 AND rating <= 5")
