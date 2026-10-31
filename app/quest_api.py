from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth_api import current_user
from app.database import get_session
from app.models import User
from app.quest_service import QuestService

router = APIRouter(tags=["quests"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]


class ObjectiveOutput(BaseModel):
    id: int
    title: str
    description: str
    objective_type: str
    required_count: int
    current_count: int
    completed: bool
    is_required: bool


class QuestOutput(BaseModel):
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


class ObjectiveChange(BaseModel):
    quest_id: int
    objective_id: int
    objective_completed: bool
    quest_completed: bool


class InteractionOutput(BaseModel):
    accepted: bool
    changes: list[ObjectiveChange]


class TerminalOutput(BaseModel):
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
