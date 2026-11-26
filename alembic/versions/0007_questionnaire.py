"""Persist versioned questionnaire attempts and idempotent operations."""

import sqlalchemy as sa

from alembic import op

revision = "0007_questionnaire"
down_revision = "0006_story_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "questionnaire_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("interpretation_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_question_id", sa.String(8), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "number"),
    )
    op.create_table(
        "questionnaire_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("questionnaire_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String(8), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.UniqueConstraint("attempt_id", "question_id"),
    )
    op.create_table(
        "questionnaire_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "request_id"),
    )


def downgrade():
    op.drop_table("questionnaire_operations")
    op.drop_table("questionnaire_answers")
    op.drop_table("questionnaire_attempts")
