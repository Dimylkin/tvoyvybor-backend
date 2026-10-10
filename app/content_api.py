from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth_api import current_user, require_admin
from app.content_repository import ContentRepository
from app.content_service import (
    ContentConflictError,
    ContentNotFoundError,
    ContentService,
)
from app.database import get_session
from app.models import CareerDirection, Scenario, ScenarioState, Task, User

router = APIRouter(tags=["content"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]
AdminDep = Annotated[User, Depends(require_admin)]


class DirectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=1000)


class DirectionOutput(BaseModel):
    id: int
    slug: str
    title: str
    description: str


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction_id: int = Field(gt=0)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=1000)


class ScenarioAdminOutput(BaseModel):
    id: int
    direction_id: int
    slug: str
    title: str
    description: str
    is_published: bool


class TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    content: dict
    validation_config: dict
    correct_explanation: str = Field(min_length=1, max_length=2000)
    incorrect_explanation: str = Field(min_length=1, max_length=2000)


class TaskAdminOutput(BaseModel):
    id: int
    scenario_id: int
    kind: str
    title: str
    content: dict
    validation_config: dict
    correct_explanation: str
    incorrect_explanation: str
    is_published: bool


class TaskOutput(BaseModel):
    id: int
    kind: str
    title: str
    content: dict


class ScenarioOutput(BaseModel):
    id: int
    direction_id: int
    slug: str
    title: str
    description: str
    state: ScenarioState


class ScenarioDetail(ScenarioOutput):
    tasks: list[TaskOutput]
    completed_task_ids: list[int]


class ProgressOutput(BaseModel):
    scenario_id: int
    state: ScenarioState


def service(session: Session) -> ContentService:
    return ContentService(ContentRepository(session))


def missing() -> HTTPException:
    return HTTPException(status_code=404, detail="Content not found")


def scenario_output(scenario: Scenario, state: ScenarioState) -> ScenarioOutput:
    return ScenarioOutput(
        id=scenario.id,
        direction_id=scenario.direction_id,
        slug=scenario.slug,
        title=scenario.title,
        description=scenario.description,
        state=state,
    )


@router.post("/admin/directions", response_model=DirectionOutput, status_code=201)
def create_direction(
    data: DirectionInput, session: SessionDep, _admin: AdminDep
) -> CareerDirection:
    try:
        return service(session).create_direction(**data.model_dump())
    except ContentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/admin/scenarios", response_model=ScenarioAdminOutput, status_code=201)
def create_scenario(
    data: ScenarioInput, session: SessionDep, _admin: AdminDep
) -> Scenario:
    try:
        return service(session).create_scenario(**data.model_dump())
    except ContentNotFoundError as exc:
        raise missing() from exc
    except ContentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/admin/scenarios/{scenario_id}/tasks",
    response_model=TaskAdminOutput,
    status_code=201,
)
def create_task(
    scenario_id: int, data: TaskInput, session: SessionDep, _admin: AdminDep
) -> Task:
    try:
        return service(session).create_task(scenario_id, **data.model_dump())
    except ContentNotFoundError as exc:
        raise missing() from exc


@router.put("/admin/tasks/{task_id}/publish", response_model=TaskAdminOutput)
def publish_task(task_id: int, session: SessionDep, _admin: AdminDep) -> Task:
    try:
        return service(session).publish_task(task_id)
    except ContentNotFoundError as exc:
        raise missing() from exc
    except ContentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put(
    "/admin/scenarios/{scenario_id}/publish", response_model=ScenarioAdminOutput
)
def publish_scenario(
    scenario_id: int, session: SessionDep, _admin: AdminDep
) -> Scenario:
    try:
        return service(session).publish_scenario(scenario_id)
    except ContentNotFoundError as exc:
        raise missing() from exc
    except ContentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/directions", response_model=list[DirectionOutput])
def directions(session: SessionDep, _user: UserDep) -> list[CareerDirection]:
    return ContentRepository(session).directions()


@router.get("/scenarios", response_model=list[ScenarioOutput])
def scenarios(
    session: SessionDep, user: UserDep, direction_id: int | None = None
) -> list[ScenarioOutput]:
    repository = ContentRepository(session)
    return [
        scenario_output(
            item,
            (
                progress.state
                if (progress := repository.progress(user.id, item.id))
                else ScenarioState.AVAILABLE
            ),
        )
        for item in repository.published_scenarios(direction_id)
    ]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetail)
def scenario_detail(
    scenario_id: int, session: SessionDep, user: UserDep
) -> ScenarioDetail:
    content = service(session)
    try:
        scenario = content.published_scenario(scenario_id)
    except ContentNotFoundError as exc:
        raise missing() from exc
    data = scenario_output(scenario, content.scenario_state(user.id, scenario_id))
    tasks = ContentRepository(session).tasks(scenario_id, published_only=True)
    return ScenarioDetail(
        **data.model_dump(),
        tasks=[TaskOutput.model_validate(task, from_attributes=True) for task in tasks],
        completed_task_ids=ContentRepository(session).completed_task_ids(
            user.id, scenario_id
        ),
    )


@router.put("/scenarios/{scenario_id}/start", response_model=ProgressOutput)
def start_scenario(
    scenario_id: int, session: SessionDep, user: UserDep
) -> ProgressOutput:
    try:
        state = service(session).start_scenario(user.id, scenario_id)
    except ContentNotFoundError as exc:
        raise missing() from exc
    except ContentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProgressOutput(scenario_id=scenario_id, state=state)


@router.get("/progress", response_model=list[ProgressOutput])
def progress(session: SessionDep, user: UserDep) -> list[ProgressOutput]:
    repository = ContentRepository(session)
    return [
        ProgressOutput(scenario_id=item.scenario_id, state=item.state)
        for item in repository.user_progress(user.id)
        if (scenario := repository.scenario(item.scenario_id)) is not None
        and scenario.is_published
    ]
