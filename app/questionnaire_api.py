from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth_api import current_user
from app.database import get_session
from app.models import User
from app.questionnaire_catalog import CATALOG_VERSION
from app.questionnaire_service import (
    CATALOGS,
    LATEST_CATALOG_VERSION,
    QuestionnaireService,
    public_catalog,
)

router = APIRouter(prefix="/questionnaire", tags=["questionnaire"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class Start(Input):
    retake: bool = False
    catalog_version: int = 1


class AnswerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    answer: dict[str, Any]


class Progress(Input):
    expected_revision: int = Field(ge=0)
    current_question_id: str
    answer: AnswerUpdate | None = None


class Complete(Input):
    expected_revision: int = Field(ge=0)


@router.get("/catalog")
def catalog(user: UserDep, version: int = CATALOG_VERSION):
    if version not in CATALOGS:
        raise HTTPException(404, "Каталог не найден")
    return {
        "version": version,
        "questions": public_catalog(version) if version != 1 else CATALOGS[1],
    }


@router.get("/capabilities")
def capabilities(user: UserDep):
    return {"latest_catalog_version": LATEST_CATALOG_VERSION}


@router.get("/state")
def state(session: SessionDep, user: UserDep, version: int = 1, history: bool = False):
    if version not in CATALOGS:
        raise HTTPException(404, "Каталог не найден")
    result = QuestionnaireService(session, user.id).state(history)
    if result["current"] and result["current"]["catalog_version"] > version:
        raise HTTPException(409, "Обновите приложение, чтобы продолжить опрос")
    return result


def execute(service, data, operation, payload, callback, response):
    result, code = service.execute(str(data.request_id), operation, payload, callback)
    response.status_code = code
    return result


@router.post("/attempts")
def start(data: Start, response: Response, session: SessionDep, user: UserDep):
    service = QuestionnaireService(session, user.id)
    payload = {"retake": data.retake}
    if data.catalog_version != 1:
        payload["catalog_version"] = data.catalog_version
    return execute(
        service,
        data,
        "start",
        payload,
        lambda: service.start(data.retake, data.catalog_version),
        response,
    )


@router.put("/attempts/{attempt_id}/progress")
def progress(
    attempt_id: int,
    data: Progress,
    response: Response,
    session: SessionDep,
    user: UserDep,
):
    service = QuestionnaireService(session, user.id)
    update = data.answer.model_dump(mode="json") if data.answer else None
    if update is not None:
        answer = update["answer"]
        # Preserve the canonical representation of already stored v1 operations.
        if (
            answer.get("status") in ("skipped", "unsure")
            and answer.get("value") is None
        ):
            answer["value"] = None
        if isinstance(answer.get("value"), list) and all(
            isinstance(v, str) for v in answer["value"]
        ):
            answer["value"] = sorted(answer["value"])
    payload = {
        "attempt_id": attempt_id,
        "expected_revision": data.expected_revision,
        "current_question_id": data.current_question_id,
        "answer": update,
    }
    return execute(
        service,
        data,
        "progress",
        payload,
        lambda: service.progress(
            attempt_id, data.expected_revision, data.current_question_id, update
        ),
        response,
    )


@router.post("/attempts/{attempt_id}/complete")
def complete(
    attempt_id: int,
    data: Complete,
    response: Response,
    session: SessionDep,
    user: UserDep,
):
    service = QuestionnaireService(session, user.id)
    payload = {"attempt_id": attempt_id, "expected_revision": data.expected_revision}
    return execute(
        service,
        data,
        "complete",
        payload,
        lambda: service.complete(attempt_id, data.expected_revision),
        response,
    )


@router.get("/attempts/{attempt_id}/results")
def results(attempt_id: int, session: SessionDep, user: UserDep):
    return QuestionnaireService(session, user.id).results(attempt_id)
