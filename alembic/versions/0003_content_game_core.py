"""Add stage 2 content and scenario progress."""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_content_game_core"
down_revision: str | None = "0002_users"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "career_directions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "direction_id",
            sa.Integer(),
            sa.ForeignKey("career_directions.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("direction_id", "slug"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id"), nullable=False
        ),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("validation_config", sa.JSON(), nullable=False),
        sa.Column("correct_explanation", sa.String(length=2000), nullable=False),
        sa.Column("incorrect_explanation", sa.String(length=2000), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id"), nullable=False
        ),
        sa.Column(
            "state",
            sa.Enum(
                "LOCKED",
                "AVAILABLE",
                "ACTIVE",
                "COMPLETED",
                "SKIPPED",
                name="scenario_state",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "scenario_id"),
    )


def downgrade() -> None:
    op.drop_table("progress")
    op.drop_table("tasks")
    op.drop_table("scenarios")
    op.drop_table("career_directions")
