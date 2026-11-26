from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy.orm import Session

from app.auth_api import current_user
from app.database import get_session
from app.models import User
from app.quest_service import QuestService

router = APIRouter(tags=["quests"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]


class ObjectiveOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    objective_type: str
    required_count: int
    current_count: int
    completed: bool
    is_required: bool


class QuestOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    description: str
    category: str
    location_slug: str
    giver_npc_id: str
    status: Literal["locked", "available", "active", "abandoned", "completed"]
    accepted_at: datetime | None
    completed_at: datetime | None
    tracked: bool
    objectives: list[ObjectiveOutput]
    gameplay: "GameplayOutput | None" = None


class GameplayOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    state: dict[str, Any]


class ObjectiveChange(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quest_id: int
    objective_id: int
    objective_completed: bool
    quest_completed: bool


class InteractionOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    accepted: bool
    changes: list[ObjectiveChange]


class TerminalOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log: str
    port: int


class OfferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    npc_id: str = Field(min_length=1, max_length=80)


class TerminalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class TrackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quest_id: int | None


class InteractionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    event_type: str = Field(min_length=1, max_length=80)
    target_key: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/quests", response_model=list[QuestOutput])
def quests(session: SessionDep, user: UserDep):
    service = QuestService(session, user.id)
    return [service.view(item) for item in service.repo.definitions()]


@router.put("/quests/tracked")
def track(data: TrackInput, session: SessionDep, user: UserDep):
    service = QuestService(session, user.id)
    service.track(data.quest_id)
    return {"quest_id": data.quest_id}


@router.get("/quests/{quest_id}", response_model=QuestOutput)
def quest(quest_id: int, session: SessionDep, user: UserDep):
    service = QuestService(session, user.id)
    return service.view(service.definition(quest_id))


@router.post("/quests/{quest_id}/offer", response_model=QuestOutput)
def offer(quest_id: int, data: OfferInput, session: SessionDep, user: UserDep):
    return QuestService(session, user.id).offer(quest_id, data.npc_id)


@router.post("/quests/{quest_id}/accept", response_model=QuestOutput)
def accept(quest_id: int, session: SessionDep, user: UserDep):
    return QuestService(session, user.id).accept(quest_id)


@router.post("/quests/{quest_id}/abandon", response_model=QuestOutput)
def abandon(quest_id: int, session: SessionDep, user: UserDep):
    return QuestService(session, user.id).abandon(quest_id)


@router.post("/game/interactions", response_model=InteractionOutput)
def interact(data: InteractionInput, session: SessionDep, user: UserDep):
    return QuestService(session, user.id).interact(
        str(data.request_id), data.event_type, data.target_key, data.payload
    )


@router.post("/game/backend-terminal", response_model=TerminalOutput)
def terminal(data: TerminalInput, session: SessionDep, user: UserDep):
    return QuestService(session, user.id).terminal(str(data.request_id))


class GamePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None = Field(default=None, max_length=4000)
    key: str | None = Field(default=None, max_length=40)


class GameActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    action: str = Field(min_length=1, max_length=40)
    payload: GamePayload = Field(default_factory=GamePayload)


class AwardOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    description: str


class GameActionOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: dict[str, Any]
    awards: list[AwardOutput]


@router.post("/quests/{quest_id}/actions", response_model=GameActionOutput)
def game_action(
    quest_id: int, data: GameActionInput, session: SessionDep, user: UserDep
):
    from app.quest_gameplay import act

    return act(
        QuestService(session, user.id),
        quest_id,
        str(data.request_id),
        data.action,
        data.payload.model_dump(exclude_none=True),
    )


class ReflectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    response: Literal["repeat", "unsure", "not_mine"]
    activity_code: str | None = Field(default=None, max_length=40)
    barrier: Literal["difficulty", "interface", "activity"] | None = None


class ReflectionOutput(BaseModel):
    response: Literal["repeat", "unsure", "not_mine"]
    activity_code: str | None
    barrier: Literal["difficulty", "interface", "activity"] | None
    evidence_event_id: int


@router.post("/quests/{quest_id}/reflection", response_model=ReflectionOutput)
def reflection(
    quest_id: int, data: ReflectionInput, session: SessionDep, user: UserDep
):
    from app.activity_profile import save_reflection

    return save_reflection(
        QuestService(session, user.id),
        quest_id,
        str(data.request_id),
        data.response,
        data.activity_code,
        data.barrier,
    )


class ReflectionV2Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    rating: StrictInt | Literal["unable"] | None
    reason: (
        Literal["difficulty", "knowledge", "interface", "activity", "other"] | None
    ) = None

    @model_validator(mode="after")
    def validate_rating(self):
        if isinstance(self.rating, int) and not 1 <= self.rating <= 5:
            raise ValueError("Rating must be between 1 and 5")
        if self.reason and (not isinstance(self.rating, int) or self.rating > 2):
            raise ValueError("Reason is only available for ratings 1–2")
        return self


class ReflectionV2Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    changes: list[ReflectionV2Change] = Field(max_length=20)
    repeat: bool | None = None
    clear_repeat: bool = False

    @model_validator(mode="after")
    def unique_codes(self):
        if self.clear_repeat and self.repeat is not None:
            raise ValueError("Cannot set and clear repeat together")
        if len({item.code for item in self.changes}) != len(self.changes):
            raise ValueError("Duplicate activity code")
        return self


@router.put("/quests/{quest_id}/reflection-v2")
def reflection_v2(
    quest_id: int, data: ReflectionV2Input, session: SessionDep, user: UserDep
):
    from app.activity_profile import save_reflection_v2

    return save_reflection_v2(
        QuestService(session, user.id),
        quest_id,
        str(data.request_id),
        [item.model_dump() for item in data.changes],
        data.repeat,
        data.clear_repeat,
    )
