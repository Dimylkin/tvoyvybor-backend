"""Initialize migration history without application tables."""

from typing import Sequence

revision: str = "0001_stage_0"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
