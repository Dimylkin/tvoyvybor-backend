"""Persist CampusOS introduction and story completion."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006_story_progress"
down_revision: Union[str, None] = "1f142b2e194b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "intro_completed", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "main_story_completed", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.execute("UPDATE users SET intro_completed = onboarding_completed")


def downgrade() -> None:
    op.drop_column("users", "main_story_completed")
    op.drop_column("users", "intro_completed")
