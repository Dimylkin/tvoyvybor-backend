import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import CareerDirection, Scenario, Task


def load_seed_module():
    path = Path(__file__).parents[1] / "scripts" / "seed_stage6.py"
    spec = importlib.util.spec_from_file_location("seed_stage6", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage6_seed_creates_three_playable_directions_idempotently(
    monkeypatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    seed_stage6 = load_seed_module()
    monkeypatch.setattr(seed_stage6, "SessionLocal", sessions)

    assert seed_stage6.seed() == (12, 12)
    assert seed_stage6.seed() == (0, 0)

    with sessions() as session:
        directions = session.scalars(
            select(CareerDirection).order_by(CareerDirection.slug)
        ).all()
        scenarios = session.scalars(select(Scenario).order_by(Scenario.id)).all()
        tasks = session.scalars(select(Task).order_by(Task.id)).all()

    assert [item.slug for item in directions] == ["analytics", "backend", "frontend"]
    assert len(scenarios) == len(tasks) == 12
    assert all(item.is_published for item in scenarios)
    assert all(
        item.is_published
        and item.kind == "choice"
        and set(item.content) == {"context", "prompt", "options"}
        and len(item.content["options"]) == 3
        and item.validation_config == {"correct": item.content["options"][0]}
        and item.correct_explanation
        and item.incorrect_explanation
        for item in tasks
    )
