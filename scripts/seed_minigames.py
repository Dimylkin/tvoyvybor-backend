"""Publish six interactive quests; retain historical definitions and progress."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import CareerDirection
from app.quest_catalog import QUESTS, STAGES
from app.quest_models import QuestDefinition, QuestObjective


def seed(session):
    old = session.scalar(
        select(QuestDefinition).where(QuestDefinition.slug == "server-on-vacation")
    )
    if old:
        old.is_published = False
    for slug, title, direction, npc, kind, description in QUESTS:
        if session.scalar(
            select(QuestDefinition.id).where(QuestDefinition.slug == slug)
        ):
            continue
        career = session.scalar(
            select(CareerDirection).where(CareerDirection.slug == direction)
        )
        if not career:
            raise ValueError(f"Seed career directions first: {direction}")
        quest = QuestDefinition(
            slug=slug,
            title=title,
            description=description,
            category="professional",
            direction_id=career.id,
            giver_npc_id=npc,
            location_slug=direction,
            availability_config={"engine": 2, "kind": kind},
            is_published=True,
        )
        session.add(quest)
        session.flush()
        for index, (stage, name, detail) in enumerate(STAGES):
            session.add(
                QuestObjective(
                    quest_id=quest.id,
                    order_index=index,
                    title=name,
                    description=detail,
                    objective_type=stage,
                    target_key=slug,
                    required_count=1,
                    is_required=True,
                    validation_config={},
                )
            )
    session.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
