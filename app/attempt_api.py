from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.attempt_repository import AttemptRepository
from app.attempt_service import (
    AttemptConflictError,
    AttemptNotFoundError,
    AttemptService,
)
from app.auth_api import current_user
from app.database import get_session
from app.models import ScenarioState, User
from app.task_strategy import InvalidTaskConfigError, UnsupportedTaskKindError

router = APIRouter(tags=["attempts"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]


class AttemptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    answer: str = Field(min_length=1, max_length=2000)


class AttemptOutput(BaseModel):
    id: int
    task_id: int
    is_correct: bool
    reaction: str
    explanation: str
    scenario_state: ScenarioState


class InterestProfileOutput(BaseModel):
    direction_scores: dict[str, int]
    event_count: int


class InterestEventOutput(BaseModel):
    task_id: int | None
    direction_id: int
    source: str
    weight: int
    explanation: str


class RecommendationOutput(BaseModel):
    direction_id: int
    explanation: str


class AchievementOutput(BaseModel):
    slug: str
    title: str
    description: str


@router.post("/tasks/{task_id}/attempts", response_model=AttemptOutput, status_code=201)
def submit_attempt(
    task_id: int, data: AttemptInput, session: SessionDep, user: UserDep
) -> AttemptOutput:
    try:
        result = AttemptService(session).submit(
            user.id, task_id, str(data.request_id), data.answer
        )
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except AttemptConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidTaskConfigError, UnsupportedTaskKindError) as exc:
        raise HTTPException(status_code=409, detail="Task is not playable") from exc
    return AttemptOutput(
        id=result.id,
        task_id=result.task_id,
        is_correct=result.is_correct,
        reaction="completed" if result.is_correct else "retry",
        explanation=result.explanation,
        scenario_state=result.scenario_state,
    )


@router.get("/interest-profile", response_model=InterestProfileOutput)
def interest_profile(session: SessionDep, user: UserDep) -> InterestProfileOutput:
    profile = AttemptRepository(session).profile(user.id)
    if profile is None:
        return InterestProfileOutput(direction_scores={}, event_count=0)
    return InterestProfileOutput(
        direction_scores=profile.direction_scores, event_count=profile.event_count
    )


@router.get("/interest-events", response_model=list[InterestEventOutput])
def interest_events(session: SessionDep, user: UserDep) -> list[InterestEventOutput]:
    return [
        InterestEventOutput.model_validate(event, from_attributes=True)
        for event in AttemptRepository(session).events(user.id)
    ]


@router.get("/recommendation", response_model=RecommendationOutput | None)
def recommendation(session: SessionDep, user: UserDep) -> RecommendationOutput | None:
    item = AttemptRepository(session).recommendation(user.id)
    if item is None or item.direction_id is None:
        return None
    return RecommendationOutput.model_validate(item, from_attributes=True)


@router.get("/achievements", response_model=list[AchievementOutput])
def achievements(session: SessionDep, user: UserDep) -> list[AchievementOutput]:
    return [
        AchievementOutput.model_validate(item, from_attributes=True)
        for _, item in AttemptRepository(session).user_achievements(user.id)
    ]
