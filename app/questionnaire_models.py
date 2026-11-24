from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now():
    return datetime.now(UTC)


class QuestionnaireAttempt(Base):
    __tablename__ = "questionnaire_attempts"
    __table_args__ = (UniqueConstraint("user_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    interpretation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_question_id: Mapped[str] = mapped_column(String(8), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("questionnaire_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String(8), nullable=False)
    answer: Mapped[dict] = mapped_column(JSON, nullable=False)


class QuestionnaireOperation(Base):
    __tablename__ = "questionnaire_operations"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
