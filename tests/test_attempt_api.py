"""Public API evidence for the stage 3 attempt and profile flow."""

from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models import Achievement, InterestEvent, TaskAttempt, User, UserRole
from app.security import create_access_token


@pytest.fixture
def attempt_client() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
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
            for email in (
                "admin@example.com",
                "player@example.com",
                "other@example.com",
            ):
                response = client.post(
                    "/auth/register",
                    json={"email": email, "password": "safe-password"},
                )
                assert response.status_code == 201
            with sessions() as session:
                admin = session.get(User, 1)
                assert admin is not None
                admin.role = UserRole.ADMIN
                session.add(
                    Achievement(
                        slug="first-task",
                        title="Первое задание",
                        description="Верно выполнено первое задание",
                    )
                )
                session.commit()
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def create_scenario(client: TestClient) -> tuple[int, int, int]:
    direction = client.post(
        "/admin/directions",
        headers=auth(1),
        json={"slug": "backend", "title": "Backend", "description": "Server"},
    )
    assert direction.status_code == 201
    direction_id = direction.json()["id"]
    scenario = client.post(
        "/admin/scenarios",
        headers=auth(1),
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
        headers=auth(1),
        json={
            "kind": "choice",
            "title": "Choose a method",
            "content": {"prompt": "Which HTTP method reads data?"},
            "validation_config": {"correct": "GET"},
            "correct_explanation": "GET retrieves a resource.",
            "incorrect_explanation": "POST creates a resource; try again.",
        },
    )
    assert task.status_code == 201
    return direction_id, scenario_id, task.json()["id"]


def publish_and_start(client: TestClient, scenario_id: int, task_id: int) -> None:
    assert (
        client.put(f"/admin/tasks/{task_id}/publish", headers=auth(1)).status_code
        == 200
    )
    assert (
        client.put(
            f"/admin/scenarios/{scenario_id}/publish", headers=auth(1)
        ).status_code
        == 200
    )
    assert (
        client.put(f"/scenarios/{scenario_id}/start", headers=auth(2)).status_code
        == 200
    )


def submit(
    client: TestClient, task_id: int, answer: str, request_id: str | None = None
):
    return client.post(
        f"/tasks/{task_id}/attempts",
        headers=auth(2),
        json={"request_id": request_id or str(uuid4()), "answer": answer},
    )


def test_wrong_then_correct_attempt_updates_saved_player_state(attempt_client) -> None:
    client, sessions = attempt_client
    direction_id, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)

    wrong = submit(client, task_id, "POST")
    assert wrong.status_code == 201
    assert wrong.json() == {
        "id": wrong.json()["id"],
        "task_id": task_id,
        "is_correct": False,
        "reaction": "retry",
        "explanation": "POST creates a resource; try again.",
        "scenario_state": "active",
    }
    assert client.get("/progress", headers=auth(2)).json() == [
        {"scenario_id": scenario_id, "state": "active"}
    ]

    correct = submit(client, task_id, "GET")
    assert correct.status_code == 201
    assert correct.json()["is_correct"] is True
    assert correct.json()["reaction"] == "completed"
    assert correct.json()["explanation"] == "GET retrieves a resource."
    assert correct.json()["scenario_state"] == "completed"
    assert correct.json()["id"] != wrong.json()["id"]
    assert client.get("/progress", headers=auth(2)).json() == [
        {"scenario_id": scenario_id, "state": "completed"}
    ]
    profile = client.get("/interest-profile", headers=auth(2))
    assert profile.status_code == 200
    assert profile.json()["event_count"] >= 1
    assert profile.json()["direction_scores"][str(direction_id)] > 0
    events = client.get("/interest-events", headers=auth(2))
    assert events.status_code == 200
    assert any(
        event["task_id"] == task_id and event["direction_id"] == direction_id
        for event in events.json()
    )
    recommendation = client.get("/recommendation", headers=auth(2))
    assert recommendation.status_code == 200
    assert recommendation.json()["direction_id"] == direction_id
    assert recommendation.json()["explanation"]
    achievements = client.get("/achievements", headers=auth(2))
    assert achievements.status_code == 200
    assert [item["slug"] for item in achievements.json()] == ["first-task"]
    with sessions() as session:
        attempts = session.scalars(
            select(TaskAttempt).where(TaskAttempt.user_id == 2).order_by(TaskAttempt.id)
        ).all()
        assert [(item.answer, item.is_correct) for item in attempts] == [
            ("POST", False),
            ("GET", True),
        ]
        assert all(item.submitted_at is not None for item in attempts)


def test_every_attempt_records_interest_evidence(attempt_client) -> None:
    client, sessions = attempt_client
    _, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)
    assert submit(client, task_id, "POST").status_code == 201

    with sessions() as session:
        attempt = session.scalar(select(TaskAttempt).where(TaskAttempt.user_id == 2))
        assert attempt is not None
        events = session.scalars(
            select(InterestEvent).where(InterestEvent.attempt_id == attempt.id)
        ).all()
        assert events, "Предметное ТЗ §8: каждая попытка создаёт InterestEvent"
        assert all(event.explanation and event.source for event in events)


def test_scenario_completes_only_after_all_published_tasks(attempt_client) -> None:
    client, sessions = attempt_client
    direction_id, scenario_id, first_task_id = create_scenario(client)
    second = client.post(
        f"/admin/scenarios/{scenario_id}/tasks",
        headers=auth(1),
        json={
            "kind": "choice",
            "title": "Choose a status",
            "content": {"prompt": "Created?", "options": ["201", "404"]},
            "validation_config": {"correct": "201"},
            "correct_explanation": "201 means created.",
            "incorrect_explanation": "Try 201.",
        },
    )
    assert second.status_code == 201
    second_task_id = second.json()["id"]
    assert (
        client.put(f"/admin/tasks/{first_task_id}/publish", headers=auth(1)).status_code
        == 200
    )
    assert (
        client.put(
            f"/admin/tasks/{second_task_id}/publish", headers=auth(1)
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/admin/scenarios/{scenario_id}/publish", headers=auth(1)
        ).status_code
        == 200
    )
    assert (
        client.put(f"/scenarios/{scenario_id}/start", headers=auth(2)).status_code
        == 200
    )

    assert submit(client, first_task_id, "GET").json()["scenario_state"] == "active"
    assert submit(client, second_task_id, "404").json()["scenario_state"] == "active"
    assert submit(client, second_task_id, "201").json()["scenario_state"] == "completed"
    profile = client.get("/interest-profile", headers=auth(2)).json()
    assert profile == {"direction_scores": {str(direction_id): 2}, "event_count": 2}
    with sessions() as session:
        events = session.scalars(select(InterestEvent).order_by(InterestEvent.id)).all()
        assert [event.weight for event in events] == [1, 0, 1]


def test_published_scenario_cannot_gain_new_playable_tasks(attempt_client) -> None:
    client, _ = attempt_client
    _, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)
    second = client.post(
        f"/admin/scenarios/{scenario_id}/tasks",
        headers=auth(1),
        json={
            "kind": "choice",
            "title": "Later task",
            "content": {"prompt": "Later?"},
            "validation_config": {"correct": "yes"},
            "correct_explanation": "Yes.",
            "incorrect_explanation": "Try yes.",
        },
    )
    assert second.status_code == 201
    assert (
        client.put(
            f"/admin/tasks/{second.json()['id']}/publish", headers=auth(1)
        ).status_code
        == 409
    )


def test_repeated_request_is_idempotent_and_changed_payload_conflicts(
    attempt_client,
) -> None:
    client, sessions = attempt_client
    _, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)
    request_id = str(uuid4())

    first = submit(client, task_id, "GET", request_id)
    repeated = submit(client, task_id, "GET", request_id)
    assert first.status_code == repeated.status_code == 201
    assert repeated.json() == first.json()
    assert submit(client, task_id, "POST", request_id).status_code == 409
    assert submit(client, task_id, "GET").status_code == 409
    with sessions() as session:
        assert len(session.scalars(select(TaskAttempt)).all()) == 1
        assert len(session.scalars(select(InterestEvent)).all()) >= 1
    assert client.get("/interest-profile", headers=auth(2)).json()["event_count"] == 1
    assert len(client.get("/achievements", headers=auth(2)).json()) == 1


def test_replay_keeps_original_state_after_later_completion(attempt_client) -> None:
    client, _ = attempt_client
    _, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)
    request_id = str(uuid4())
    wrong = submit(client, task_id, "POST", request_id)
    assert wrong.json()["scenario_state"] == "active"
    assert submit(client, task_id, "GET").json()["scenario_state"] == "completed"
    assert submit(client, task_id, "POST", request_id).json() == wrong.json()


def test_recommendation_updates_across_directions_and_breaks_ties(
    attempt_client,
) -> None:
    client, _ = attempt_client
    first_direction_id, first_scenario_id, first_task_id = create_scenario(client)
    publish_and_start(client, first_scenario_id, first_task_id)
    assert submit(client, first_task_id, "GET").status_code == 201

    direction = client.post(
        "/admin/directions",
        headers=auth(1),
        json={"slug": "analytics", "title": "Analytics", "description": "Data"},
    )
    assert direction.status_code == 201
    second_direction_id = direction.json()["id"]
    scenario = client.post(
        "/admin/scenarios",
        headers=auth(1),
        json={
            "direction_id": second_direction_id,
            "slug": "first-analysis",
            "title": "First analysis",
            "description": "Read data",
        },
    )
    assert scenario.status_code == 201
    second_scenario_id = scenario.json()["id"]
    task = client.post(
        f"/admin/scenarios/{second_scenario_id}/tasks",
        headers=auth(1),
        json={
            "kind": "choice",
            "title": "Choose a chart",
            "content": {"prompt": "Chart?", "options": ["bar", "pie"]},
            "validation_config": {"correct": "bar"},
            "correct_explanation": "Bar shows categories.",
            "incorrect_explanation": "Try bar.",
        },
    )
    assert task.status_code == 201
    second_task_id = task.json()["id"]
    assert (
        client.put(
            f"/admin/tasks/{second_task_id}/publish", headers=auth(1)
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/admin/scenarios/{second_scenario_id}/publish", headers=auth(1)
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/scenarios/{second_scenario_id}/start", headers=auth(2)
        ).status_code
        == 200
    )
    assert submit(client, second_task_id, "bar").status_code == 201

    profile = client.get("/interest-profile", headers=auth(2)).json()
    assert profile == {
        "direction_scores": {
            str(first_direction_id): 1,
            str(second_direction_id): 1,
        },
        "event_count": 2,
    }
    recommendation = client.get("/recommendation", headers=auth(2)).json()
    assert recommendation["direction_id"] == min(
        first_direction_id, second_direction_id
    )
    assert "Предварительно" in recommendation["explanation"]


def test_attempt_requires_owned_active_published_scenario(attempt_client) -> None:
    client, sessions = attempt_client
    _, scenario_id, task_id = create_scenario(client)
    assert submit(client, task_id, "GET").status_code == 404
    assert (
        client.put(f"/admin/tasks/{task_id}/publish", headers=auth(1)).status_code
        == 200
    )
    assert submit(client, task_id, "GET").status_code == 404
    assert (
        client.put(
            f"/admin/scenarios/{scenario_id}/publish", headers=auth(1)
        ).status_code
        == 200
    )
    assert submit(client, task_id, "GET").status_code == 409
    assert client.post(f"/tasks/{task_id}/attempts", json={}).status_code == 401
    assert (
        client.put(f"/scenarios/{scenario_id}/start", headers=auth(2)).status_code
        == 200
    )
    assert (
        client.post(
            f"/tasks/{task_id}/attempts",
            headers=auth(3),
            json={"request_id": str(uuid4()), "answer": "GET"},
        ).status_code
        == 409
    )
    assert submit(client, 99999, "GET").status_code == 404
    assert submit(client, task_id, "GET").status_code == 201
    for path in (
        "/progress",
        "/interest-profile",
        "/interest-events",
        "/recommendation",
        "/achievements",
    ):
        response = client.get(path, headers=auth(3))
        assert response.status_code == 200
        assert response.json() in (
            [],
            {},
            None,
            {"direction_scores": {}, "event_count": 0},
        )
    with sessions() as session:
        assert {
            item.user_id for item in session.scalars(select(TaskAttempt)).all()
        } == {2}


@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "not-a-uuid", "answer": "GET"},
        {"request_id": str(uuid4()), "answer": ""},
        {"request_id": str(uuid4()), "answer": "GET", "is_correct": True},
        {"request_id": str(uuid4())},
    ],
)
def test_malformed_attempt_is_rejected_without_side_effects(
    attempt_client, payload
) -> None:
    client, sessions = attempt_client
    _, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)

    response = client.post(f"/tasks/{task_id}/attempts", headers=auth(2), json=payload)
    assert response.status_code == 422
    with sessions() as session:
        assert session.scalars(select(TaskAttempt)).all() == []
    assert client.get("/interest-profile", headers=auth(2)).json() == {
        "direction_scores": {},
        "event_count": 0,
    }


def test_final_report_uses_only_current_users_persisted_interest_events(
    attempt_client,
) -> None:
    client, _ = attempt_client
    assert client.get("/final-report").status_code == 401
    assert client.get("/final-report", headers=auth(3)).json() == {
        "event_count": 0,
        "completed_task_count": 0,
        "directions": [],
        "observations": ["Пока нет попыток: отчёт появится после прохождения заданий."],
        "next_steps": ["Откройте любой доступный сценарий и выполните первое задание."],
    }
    direction_id, scenario_id, task_id = create_scenario(client)
    publish_and_start(client, scenario_id, task_id)
    assert submit(client, task_id, "POST").status_code == 201
    assert submit(client, task_id, "GET").status_code == 201

    report = client.get("/final-report", headers=auth(2))
    assert report.status_code == 200
    assert report.json() == {
        "event_count": 2,
        "completed_task_count": 1,
        "directions": [
            {
                "direction_id": direction_id,
                "title": "Backend",
                "score": 1,
                "reason": "Верно выполнено заданий в направлении: 1.",
            }
        ],
        "observations": [
            "Зафиксировано попыток: 2.",
            "Верно выполнено заданий: 1.",
        ],
        "next_steps": ["Продолжите изучать направление «Backend»."],
    }
    assert client.get("/final-report", headers=auth(3)).json()["event_count"] == 0
