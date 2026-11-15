"""Persistent quest definitions and per-player state.

These tables intentionally coexist with the historical scenario tables.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now() -> datetime:
    return datetime.now(UTC)


class QuestDefinition(Base):
    __tablename__ = "quest_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("career_directions.id"))
    giver_npc_id: Mapped[str] = mapped_column(String(80), nullable=False)
    location_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    availability_config: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now, onupdate=now
    )


class QuestObjective(Base):
    __tablename__ = "quest_objectives"
    __table_args__ = (UniqueConstraint("quest_id", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quest_id: Mapped[int] = mapped_column(
        ForeignKey("quest_definitions.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    objective_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_key: Mapped[str] = mapped_column(String(80), nullable=False)
    required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validation_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PlayerQuest(Base):
    __tablename__ = "player_quests"
    __table_args__ = (UniqueConstraint("user_id", "quest_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    quest_id: Mapped[int] = mapped_column(
        ForeignKey("quest_definitions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now, onupdate=now
    )


class PlayerQuestObjective(Base):
    __tablename__ = "player_quest_objectives"
    __table_args__ = (UniqueConstraint("player_quest_id", "objective_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_quest_id: Mapped[int] = mapped_column(
        ForeignKey("player_quests.id"), nullable=False
    )
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("quest_objectives.id"), nullable=False
    )
    current_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestEvent(Base):
    __tablename__ = "quest_events"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_key: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now
    )


class TrackedQuest(Base):
    __tablename__ = "tracked_quests"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    player_quest_id: Mapped[int] = mapped_column(
        ForeignKey("player_quests.id"), nullable=False
    )
