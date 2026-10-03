from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.USER,
    )


class ScenarioState(StrEnum):
    LOCKED = "locked"
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class CareerDirection(Base):
    __tablename__ = "career_directions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (UniqueConstraint("direction_id", "slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction_id: Mapped[int] = mapped_column(
        ForeignKey("career_directions.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    correct_explanation: Mapped[str] = mapped_column(String(2000), nullable=False)
    incorrect_explanation: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "scenario_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), nullable=False)
    state: Mapped[ScenarioState] = mapped_column(
        Enum(ScenarioState, name="scenario_state", native_enum=False),
        nullable=False,
    )
