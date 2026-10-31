import importlib.util
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.security import create_access_token


def seed(session):
    path = Path(__file__).parents[1] / "scripts" / "seed_quests.py"
    spec = importlib.util.spec_from_file_location("seed_quests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        seed(session)

    def get_test_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        for email in ("one@example.com", "two@example.com"):
            assert (
                test_client.post(
                    "/auth/register", json={"email": email, "password": "password123"}
                ).status_code
                == 201
            )
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def headers(user=1):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_quest_full_flow_and_idempotency(client):
    h = headers()
    assert client.post("/quests/1/accept", headers=h).status_code == 409
    assert (
        client.post(
            "/game/backend-terminal", headers=h, json={"request_id": str(uuid4())}
        ).status_code
        == 409
    )
    assert (
        client.post("/quests/1/offer", headers=h, json={"npc_id": "boris"}).status_code
        == 200
    )
    assert client.post("/quests/1/accept", headers=h).json()["status"] == "active"
    assert (
        client.put("/quests/tracked", headers=h, json={"quest_id": 1}).status_code
        == 200
    )
    assert client.get("/quests/1", headers=headers(2)).json()["status"] == "available"

    def action(kind, target, payload=None, request_id=None):
        return client.post(
            "/game/interactions",
            headers=h,
            json={
                "request_id": request_id or str(uuid4()),
                "event_type": kind,
                "target_key": target,
                "payload": payload or {},
            },
        )

    assert (
        action("terminal_problem_fixed", "backend_terminal", {"port": 8080}).status_code
        == 409
    )
    request_id = str(uuid4())
    first = action("object_inspected", "backend_server", request_id=request_id)
    assert first.status_code == 200
    assert (
        action("object_inspected", "backend_server", request_id=request_id).json()
        == first.json()
    )
    assert action("npc_reported", "boris", request_id=request_id).status_code == 409
    assert action("terminal_investigated", "backend_terminal").status_code == 409
    assert (
        client.post(
            "/game/backend-terminal", headers=h, json={"request_id": str(uuid4())}
        ).json()["port"]
        == 8000
    )
    assert action("terminal_investigated", "backend_terminal").status_code == 200
    assert (
        action("terminal_problem_fixed", "backend_terminal", {"port": 8000}).status_code
        == 422
    )
    assert (
        action("terminal_problem_fixed", "backend_terminal", {"port": 8080}).status_code
        == 200
    )
    assert action("npc_reported", "boris").json()["changes"][0]["quest_completed"]
    final = client.get("/quests/1", headers=h).json()
    assert final["status"] == "completed"
    assert not final["tracked"]
    assert client.post("/quests/1/accept", headers=h).status_code == 409


def test_multiple_quests_tracking_and_abandonment(client):
    from app.quest_models import QuestDefinition, QuestObjective

    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    quest = QuestDefinition(
        slug="second",
        title="Второе дело",
        description="Ещё одна задача",
        category="side",
        giver_npc_id="boris",
        location_slug="backend",
        availability_config={},
        is_published=True,
    )
    session.add(quest)
    session.flush()
    session.add(
        QuestObjective(
            quest_id=quest.id,
            title="Необязательная цель",
            description="Дополнительно",
            order_index=0,
            objective_type="object_inspected",
            target_key="optional",
            required_count=1,
            validation_config={},
            is_required=False,
        )
    )
    session.add(
        QuestObjective(
            quest_id=quest.id,
            title="Обязательная цель",
            description="Основная работа",
            order_index=1,
            objective_type="object_inspected",
            target_key="required",
            required_count=1,
            validation_config={},
            is_required=True,
        )
    )
    session.commit()
    generator.close()
    h = headers()
    for quest_id in (1, 2):
        assert (
            client.post(
                f"/quests/{quest_id}/offer", headers=h, json={"npc_id": "boris"}
            ).status_code
            == 200
        )
        assert client.post(f"/quests/{quest_id}/accept", headers=h).status_code == 200
    assert (
        client.put("/quests/tracked", headers=h, json={"quest_id": 1}).status_code
        == 200
    )
    assert (
        client.put("/quests/tracked", headers=h, json={"quest_id": 2}).status_code
        == 200
    )
    quests = client.get("/quests", headers=h).json()
    assert [q["status"] for q in quests] == ["active", "active"]
    assert [q["tracked"] for q in quests] == [False, True]
    assert client.post("/quests/2/abandon", headers=h).json()["status"] == "abandoned"
    assert not client.get("/quests/2", headers=h).json()["tracked"]
    assert client.post("/quests/2/accept", headers=h).json()["status"] == "active"
    result = client.post(
        "/game/interactions",
        headers=h,
        json={
            "request_id": str(uuid4()),
            "event_type": "object_inspected",
            "target_key": "required",
        },
    )
    assert result.json()["changes"][0]["quest_completed"] is True
    assert client.get("/quests/1", headers=h).json()["status"] == "active"
    assert client.get("/quests/2", headers=headers(2)).json()["status"] == "available"
