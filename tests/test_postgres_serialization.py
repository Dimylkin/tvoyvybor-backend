import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import User
from app.quest_repository import QuestRepository

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not configured")
def test_user_lock_serializes_independent_postgres_sessions() -> None:
    assert POSTGRES_URL is not None
    assert POSTGRES_URL.startswith("postgresql+")
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    email = f"lock-{uuid4()}@example.test"
    started = Event()
    acquired = Event()

    try:
        with Session(engine) as setup:
            user = User(email=email, password_hash="test-hash")
            setup.add(user)
            setup.commit()
            user_id = user.id

        blocker = Session(engine)
        QuestRepository(blocker).lock_user(user_id)

        def acquire_lock() -> None:
            with Session(engine) as contender:
                started.set()
                QuestRepository(contender).lock_user(user_id)
                acquired.set()
                contender.commit()

        with ThreadPoolExecutor(max_workers=1) as executor:
            contender = executor.submit(acquire_lock)
            try:
                assert started.wait(timeout=2)
                assert not acquired.wait(timeout=0.15)
            finally:
                blocker.commit()
            assert acquired.wait(timeout=3)
            contender.result(timeout=1)
        blocker.close()
    finally:
        with Session(engine) as cleanup:
            cleanup.query(User).filter(User.email == email).delete()
            cleanup.commit()
        engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not configured")
def test_concurrent_reflections_serialize_and_retry_keeps_latest() -> None:
    from sqlalchemy import select

    from app.activity_profile import activity_profile, save_reflection
    from app.quest_models import PlayerQuest, QuestDefinition, QuestEvent
    from app.quest_service import QuestService

    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    email = f"reflection-{uuid4()}@example.test"
    slug = f"reflection-{uuid4()}"
    started = Event()
    finished = Event()
    first_id, second_id = str(uuid4()), str(uuid4())
    user_id = quest_id = None
    try:
        with Session(engine) as setup:
            user = User(email=email, password_hash="test-hash")
            quest = QuestDefinition(
                slug=slug,
                title="Проба",
                description="Проба",
                category="professional",
                giver_npc_id="mentor",
                location_slug="backend",
                availability_config={"engine": 2, "kind": "code"},
                is_published=True,
            )
            setup.add_all([user, quest])
            setup.flush()
            user_id, quest_id = user.id, quest.id
            setup.add(PlayerQuest(user_id=user_id, quest_id=quest_id, status="active"))
            setup.add(
                QuestEvent(
                    user_id=user_id,
                    request_id=str(uuid4()),
                    event_type="minigame_action",
                    target_key=f"quest:{quest_id}",
                    payload={"action": "run", "payload": {"value": "return 0"}},
                    result={"state": {}},
                )
            )
            setup.commit()

        def second_write():
            with Session(engine) as session:
                started.set()
                result = save_reflection(
                    QuestService(session, user_id),
                    quest_id,
                    second_id,
                    "unsure",
                    None,
                    None,
                )
                finished.set()
                return result

        with Session(engine) as first, ThreadPoolExecutor(max_workers=1) as executor:
            QuestRepository(first).lock_user(user_id)
            future = executor.submit(second_write)
            try:
                assert started.wait(2)
                assert not finished.wait(0.2)
                initial = save_reflection(
                    QuestService(first, user_id),
                    quest_id,
                    first_id,
                    "repeat",
                    "coding",
                    None,
                )
            finally:
                first.rollback()
            assert future.result(timeout=5)["response"] == "unsure"
        with Session(engine) as verify:
            retried = save_reflection(
                QuestService(verify, user_id),
                quest_id,
                first_id,
                "repeat",
                "coding",
                None,
            )
            assert retried == initial
            result = activity_profile(verify, user_id)
            assert (
                next(
                    item for item in result["history"] if item["quest_id"] == quest_id
                )["reflection"]["response"]
                == "unsure"
            )
            events = verify.scalars(
                select(QuestEvent).where(
                    QuestEvent.user_id == user_id,
                    QuestEvent.event_type == "activity_reflection",
                )
            ).all()
            assert len(events) == 2
    finally:
        with Session(engine) as cleanup:
            if user_id is not None:
                cleanup.query(QuestEvent).filter_by(user_id=user_id).delete()
                cleanup.query(PlayerQuest).filter_by(user_id=user_id).delete()
                cleanup.query(User).filter_by(id=user_id).delete()
            if quest_id is not None:
                cleanup.query(QuestDefinition).filter_by(id=quest_id).delete()
            cleanup.commit()
        engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not configured")
def test_questionnaire_conflicting_revisions_are_serialized():
    from fastapi import HTTPException

    from app.questionnaire_models import (
        QuestionnaireAnswer,
        QuestionnaireAttempt,
        QuestionnaireOperation,
    )
    from app.questionnaire_service import QuestionnaireService

    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    email = f"questionnaire-{uuid4()}@example.test"
    user_id = None
    try:
        with Session(engine) as session:
            user = User(email=email, password_hash="test-hash")
            session.add(user)
            session.commit()
            user_id = user.id
            service = QuestionnaireService(session, user_id)
            initial, _ = service.execute(
                str(uuid4()), "start", {"retake": False}, lambda: service.start(False)
            )
        started, finished = Event(), Event()

        def second_write():
            with Session(engine) as session:
                service = QuestionnaireService(session, user_id)
                started.set()
                try:
                    service.execute(
                        str(uuid4()),
                        "progress",
                        {"attempt": initial["id"], "revision": 0},
                        lambda: service.progress(initial["id"], 0, "Q03", None),
                    )
                except HTTPException as error:
                    assert error.status_code == 409
                else:
                    pytest.fail("Stale revision was accepted")
                finally:
                    finished.set()

        with Session(engine) as first, ThreadPoolExecutor(max_workers=1) as pool:
            QuestRepository(first).lock_user(user_id)
            future = pool.submit(second_write)
            assert started.wait(2)
            assert not finished.wait(0.2)
            service = QuestionnaireService(first, user_id)
            service.execute(
                str(uuid4()),
                "progress",
                {"attempt": initial["id"], "revision": 0},
                lambda: service.progress(initial["id"], 0, "Q02", None),
            )
            future.result(timeout=5)
    finally:
        with Session(engine) as cleanup:
            if user_id is not None:
                ids = cleanup.query(QuestionnaireAttempt.id).filter_by(user_id=user_id)
                cleanup.query(QuestionnaireAnswer).filter(
                    QuestionnaireAnswer.attempt_id.in_(ids)
                ).delete(synchronize_session=False)
                cleanup.query(QuestionnaireOperation).filter_by(
                    user_id=user_id
                ).delete()
                cleanup.query(QuestionnaireAttempt).filter_by(user_id=user_id).delete()
                cleanup.query(User).filter_by(id=user_id).delete()
                cleanup.commit()
        engine.dispose()
