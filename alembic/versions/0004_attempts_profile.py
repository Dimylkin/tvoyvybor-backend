"""Persist attempts, interest evidence, profile, recommendation and awards."""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_attempts_profile"
down_revision: str | None = "0003_content_game_core"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.String(length=2000), nullable=False),
        sa.Column(
            "scenario_state",
            sa.Enum(
                "LOCKED",
                "AVAILABLE",
                "ACTIVE",
                "COMPLETED",
                "SKIPPED",
                name="attempt_scenario_state",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "request_id"),
    )
    op.create_table(
        "interest_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "attempt_id", sa.Integer(), sa.ForeignKey("task_attempts.id"), nullable=True
        ),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("trait", sa.String(length=80), nullable=True),
        sa.Column(
            "direction_id",
            sa.Integer(),
            sa.ForeignKey("career_directions.id"),
            nullable=False,
        ),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.String(length=2000), nullable=False),
        sa.UniqueConstraint("attempt_id"),
    )
    op.create_table(
        "interest_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("trait_scores", sa.JSON(), nullable=False),
        sa.Column("direction_scores", sa.JSON(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "direction_id",
            sa.Integer(),
            sa.ForeignKey("career_directions.id"),
            nullable=True,
        ),
        sa.Column("explanation", sa.String(length=2000), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "achievements",
            sa.column("slug", sa.String()),
            sa.column("title", sa.String()),
            sa.column("description", sa.String()),
        ),
        [
            {
                "slug": "first-task",
                "title": "Первое задание",
                "description": "Верно выполнено первое задание",
            }
        ],
    )
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "achievement_id",
            sa.Integer(),
            sa.ForeignKey("achievements.id"),
            nullable=False,
        ),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "achievement_id"),
    )


def downgrade() -> None:
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("recommendations")
    op.drop_table("interest_profiles")
    op.drop_table("interest_events")
    op.drop_table("task_attempts")
