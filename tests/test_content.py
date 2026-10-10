from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.content_service import ContentConflictError, state_after_start
from app.database import Base, get_session
from app.main import app
from app.models import Progress, ScenarioState, User, UserRole
from app.security import create_access_token


@pytest.fixture
def content_client() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def test_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            for email in ("admin@example.com", "user@example.com", "other@example.com"):
                assert (
                    client.post(
                        "/auth/register",
                        json={"email": email, "password": "safe-password"},
                    ).status_code
                    == 201
                )
            with sessions() as session:
                admin = session.get(User, 1)
                assert admin is not None
                admin.role = UserRole.ADMIN
                session.commit()
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def seed_scenario(client: TestClient) -> tuple[int, int, int]:
    direction = client.post(
        "/admin/directions",
        headers=headers(1),
        json={"slug": "backend", "title": "Backend", "description": "Server"},
    )
    assert direction.status_code == 201
    direction_id = direction.json()["id"]
    scenario = client.post(
        "/admin/scenarios",
        headers=headers(1),
        json={
            "direction_id": direction_id,
            "slug": "first-api",
            "title": "First API",
            "description": "Build an endpoint",
        },
    )
    assert scenario.status_code == 201
    scenario_id = scenario.json()["id"]
    task = client.post(
        f"/admin/scenarios/{scenario_id}/tasks",
        headers=headers(1),
        json={
            "kind": "choice",
            "title": "Choose a method",
            "content": {"prompt": "Which method?"},
            "validation_config": {"correct": "GET"},
            "correct_explanation": "GET retrieves data",
            "incorrect_explanation": "Other methods have different purposes",
        },
    )
    assert task.status_code == 201
    assert task.json()["correct_explanation"] == "GET retrieves data"
    assert (
        task.json()["incorrect_explanation"] == "Other methods have different purposes"
    )
    return direction_id, scenario_id, task.json()["id"]


@pytest.mark.parametrize(
    ("current", "allowed"),
    [
        (ScenarioState.LOCKED, False),
        (ScenarioState.AVAILABLE, True),
        (ScenarioState.ACTIVE, True),
        (ScenarioState.COMPLETED, False),
        (ScenarioState.SKIPPED, False),
    ],
)
def test_start_transition_for_each_state(current: ScenarioState, allowed: bool) -> None:
    if allowed:
        assert state_after_start(current) == ScenarioState.ACTIVE
    else:
        with pytest.raises(ContentConflictError):
            state_after_start(current)


def test_admin_publishes_and_user_starts_scenario(content_client) -> None:
    client, sessions = content_client
    assert client.post("/admin/directions", json={}).status_code == 401
    assert (
        client.post("/admin/directions", headers=headers(2), json={}).status_code == 403
    )
    direction_id, scenario_id, task_id = seed_scenario(client)
    assert client.get("/directions", headers=headers(2)).json() == []
    assert client.get("/scenarios", headers=headers(2)).json() == []
    assert (
        client.get(f"/scenarios/{scenario_id}", headers=headers(2)).status_code == 404
    )
    assert (
        client.put(
            f"/admin/scenarios/{scenario_id}/publish", headers=headers(1)
        ).status_code
        == 409
    )
    for _ in range(2):
        assert (
            client.put(
                f"/admin/tasks/{task_id}/publish", headers=headers(1)
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/admin/scenarios/{scenario_id}/publish", headers=headers(1)
            ).status_code
            == 200
        )
    assert client.get("/directions", headers=headers(2)).json()[0]["id"] == direction_id
    scenarios = client.get("/scenarios", headers=headers(2)).json()
    assert len(scenarios) == 1
    assert scenarios[0]["state"] == "available"
    detail = client.get(f"/scenarios/{scenario_id}", headers=headers(2)).json()
    assert detail["tasks"] == [
        {
            "id": task_id,
            "kind": "choice",
            "title": "Choose a method",
            "content": {"prompt": "Which method?"},
        }
    ]
    assert detail["completed_task_ids"] == []
    assert "validation_config" not in str(detail)
    assert "correct_explanation" not in str(detail)
    assert "incorrect_explanation" not in str(detail)
    for _ in range(2):
        result = client.put(f"/scenarios/{scenario_id}/start", headers=headers(2))
        assert result.status_code == 200
        assert result.json() == {"scenario_id": scenario_id, "state": "active"}
    assert client.get("/progress", headers=headers(2)).json() == [
        {"scenario_id": scenario_id, "state": "active"}
    ]
    assert (
        client.get("/scenarios", headers=headers(3)).json()[0]["state"] == "available"
    )
    assert client.get("/progress", headers=headers(3)).json() == []
    with sessions() as session:
        assert session.query(Progress).count() == 1


def test_scenario_detail_returns_only_successfully_completed_tasks(
    content_client,
) -> None:
    client, _ = content_client
    _, scenario_id, task_id = seed_scenario(client)
    client.put(f"/admin/tasks/{task_id}/publish", headers=headers(1))
    client.put(f"/admin/scenarios/{scenario_id}/publish", headers=headers(1))
    assert (
        client.put(f"/scenarios/{scenario_id}/start", headers=headers(2)).status_code
        == 200
    )

    wrong = client.post(
        f"/tasks/{task_id}/attempts",
        headers=headers(2),
        json={"request_id": "c47f97b9-4cf1-45f3-81f1-659fe9e93106", "answer": "POST"},
    )
    assert wrong.status_code == 201
    assert (
        client.get(f"/scenarios/{scenario_id}", headers=headers(2)).json()[
            "completed_task_ids"
        ]
        == []
    )

    correct = client.post(
        f"/tasks/{task_id}/attempts",
        headers=headers(2),
        json={"request_id": "fd18e062-5d4d-4193-8776-20f6a565f7dd", "answer": "GET"},
    )
    assert correct.status_code == 201
    assert client.get(f"/scenarios/{scenario_id}", headers=headers(2)).json()[
        "completed_task_ids"
    ] == [task_id]


def test_draft_task_hidden_and_locked_progress_cannot_start(content_client) -> None:
    client, sessions = content_client
    _, scenario_id, task_id = seed_scenario(client)
    published = client.post(
        f"/admin/scenarios/{scenario_id}/tasks",
        headers=headers(1),
        json={
            "kind": "choice",
            "title": "Public task",
            "content": {"prompt": "Public"},
            "validation_config": {"correct": "yes"},
            "correct_explanation": "Why yes",
            "incorrect_explanation": "Why not",
        },
    ).json()
    client.put(f"/admin/tasks/{published['id']}/publish", headers=headers(1))
    client.put(f"/admin/scenarios/{scenario_id}/publish", headers=headers(1))
    detail = client.get(f"/scenarios/{scenario_id}", headers=headers(2)).json()
    assert [task["id"] for task in detail["tasks"]] == [published["id"]]
    assert task_id not in [task["id"] for task in detail["tasks"]]
    with sessions() as session:
        session.add(
            Progress(user_id=2, scenario_id=scenario_id, state=ScenarioState.LOCKED)
        )
        session.commit()
    assert (
        client.put(f"/scenarios/{scenario_id}/start", headers=headers(2)).status_code
        == 409
    )
    assert (
        client.get(f"/scenarios/{scenario_id}", headers=headers(2)).json()["state"]
        == "locked"
    )


def test_saved_available_progress_transitions_to_active(content_client) -> None:
    client, sessions = content_client
    _, scenario_id, task_id = seed_scenario(client)
    client.put(f"/admin/tasks/{task_id}/publish", headers=headers(1))
    client.put(f"/admin/scenarios/{scenario_id}/publish", headers=headers(1))
    with sessions() as session:
        session.add(
            Progress(user_id=2, scenario_id=scenario_id, state=ScenarioState.AVAILABLE)
        )
        session.commit()

    result = client.put(f"/scenarios/{scenario_id}/start", headers=headers(2))
    assert result.status_code == 200
    assert result.json() == {"scenario_id": scenario_id, "state": "active"}
    with sessions() as session:
        progress = (
            session.query(Progress).filter_by(user_id=2, scenario_id=scenario_id).one()
        )
        assert progress.state == ScenarioState.ACTIVE


def test_invalid_content_and_missing_resources(content_client) -> None:
    client, _ = content_client
    assert client.get("/directions").status_code == 401
    assert (
        client.post(
            "/admin/directions",
            headers=headers(1),
            json={"slug": "Bad Slug", "title": "X", "description": ""},
        ).status_code
        == 422
    )
    direction_id, scenario_id, _ = seed_scenario(client)
    assert (
        client.post(
            "/admin/directions",
            headers=headers(1),
            json={"slug": "backend", "title": "Other", "description": ""},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/admin/scenarios",
            headers=headers(1),
            json={
                "direction_id": direction_id,
                "slug": "first-api",
                "title": "X",
                "description": "",
            },
        ).status_code
        == 409
    )
    assert client.put("/scenarios/999/start", headers=headers(2)).status_code == 404
    assert client.put("/admin/tasks/999/publish", headers=headers(1)).status_code == 404
    assert (
        client.put("/admin/scenarios/999/publish", headers=headers(1)).status_code
        == 404
    )
    assert (
        client.get(f"/scenarios/{scenario_id}", headers=headers(2)).status_code == 404
    )
