from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.quest_models import (
    PlayerQuest,
    PlayerQuestObjective,
    QuestDefinition,
    QuestEvent,
    QuestObjective,
)


class QuestRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_user(self, user_id: int) -> None:
        self.session.scalar(select(User.id).where(User.id == user_id).with_for_update())

    def definitions(self):
        return list(
            self.session.scalars(
                select(QuestDefinition)
                .where(QuestDefinition.is_published.is_(True))
                .order_by(QuestDefinition.id)
            )
        )

    def definition(self, quest_id: int):
        return self.session.scalar(
            select(QuestDefinition).where(
                QuestDefinition.id == quest_id, QuestDefinition.is_published.is_(True)
            )
        )

    def player(self, user_id: int, quest_id: int):
        return self.session.scalar(
            select(PlayerQuest).where(
                PlayerQuest.user_id == user_id, PlayerQuest.quest_id == quest_id
            )
        )

    def objectives(self, quest_id: int):
        return list(
            self.session.scalars(
                select(QuestObjective)
                .where(QuestObjective.quest_id == quest_id)
                .order_by(QuestObjective.order_index)
            )
        )

    def progress(self, player_quest_id: int):
        return {
            p.objective_id: p
            for p in self.session.scalars(
                select(PlayerQuestObjective).where(
                    PlayerQuestObjective.player_quest_id == player_quest_id
                )
            )
        }

    def event(self, user_id: int, request_id: str):
        return self.session.scalar(
            select(QuestEvent).where(
                QuestEvent.user_id == user_id, QuestEvent.request_id == request_id
            )
        )
