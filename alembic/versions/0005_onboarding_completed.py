"""Persist whether an account has completed the campus introduction."""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_onboarding_completed"
down_revision: str | None = "0004_attempts_profile"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed")
