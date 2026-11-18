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
