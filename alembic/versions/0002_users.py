"""Create users for stage 1 authentication."""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_users"
down_revision: str | None = "0001_stage_0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "ADMIN", name="user_role", native_enum=False),
            nullable=False,
        ),
        sa.UniqueConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("users")
