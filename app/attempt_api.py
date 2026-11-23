from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.activity_profile import activity_profile
from app.attempt_repository import AttemptRepository
from app.attempt_service import (
    AttemptConflictError,
    AttemptNotFoundError,
    AttemptService,
    final_report,
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


class FinalReportDirectionOutput(BaseModel):
    direction_id: int
    title: str
    score: int
    reason: str


class FinalReportOutput(BaseModel):
    event_count: int
    completed_task_count: int
    directions: list[FinalReportDirectionOutput]
    observations: list[str]
    next_steps: list[str]


class ActivityOptionOutput(BaseModel):
    code: str
    label: str


class ReflectionOutput(BaseModel):
    response: Literal["repeat", "unsure", "not_mine"]
    activity_code: str | None
    barrier: Literal["difficulty", "interface", "activity"] | None
    evidence_event_id: int | None = None


class ActivityHistoryOutput(BaseModel):
    quest_id: int
    title: str
    status: str
    published: bool
    activities: list[ActivityOptionOutput]
    reflection: ReflectionOutput | None
    legacy_reaction: str | None


class ActivityEvidenceOutput(BaseModel):
    quest_id: int
    title: str
    description: str


class ActivityInsightOutput(BaseModel):
    activity_code: str
    label: str
    status: Literal["hypothesis", "repeated", "mixed"]
    evidence: list[ActivityEvidenceOutput]


class ActivityStepOutput(BaseModel):
    quest_id: int | None
    title: str
    explanation: str


class MainObservationOutput(BaseModel):
    activity_code: str
    status: Literal["hypothesis", "repeated", "mixed"]
    headline: str
    interest: str
    direction: str
    example: str


class ActivityGroupOutput(BaseModel):
    code: str
    name: str
    description: str
    score: int
    evidence_count: int
    evidence: list[str]


class ActivityCareerOutput(BaseModel):
    name: str
    explanation: str


class ActivityLearningOutput(BaseModel):
    title: str
    action: str
    group: str


class ActivityProfileOutput(BaseModel):
    event_count: int
    performance_score: int
    preliminary: bool
    groups: list[ActivityGroupOutput]
    careers: list[ActivityCareerOutput]
    learning: list[ActivityLearningOutput]
    additional: tuple[str, str] | None
    observations: int
    history: list[ActivityHistoryOutput]
    insights: list[ActivityInsightOutput]
    next_step: ActivityStepOutput | None
    main_observation: MainObservationOutput | None


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


@router.get("/final-report", response_model=FinalReportOutput)
def get_final_report(session: SessionDep, user: UserDep) -> FinalReportOutput:
    report = final_report(AttemptRepository(session).events_with_directions(user.id))
    return FinalReportOutput(
        event_count=report.event_count,
        completed_task_count=report.completed_task_count,
        directions=[
            FinalReportDirectionOutput(
                direction_id=item.direction_id,
                title=item.title,
                score=item.score,
                reason=item.reason,
            )
            for item in report.directions
        ],
        observations=report.observations,
        next_steps=report.next_steps,
    )


@router.get("/activity-profile", response_model=ActivityProfileOutput)
def get_activity_profile(session: SessionDep, user: UserDep) -> dict:
    """Return explainable activity interests from both new and legacy gameplay."""
    return activity_profile(session, user.id)
