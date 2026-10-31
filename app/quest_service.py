from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.quest_models import (
    PlayerQuest,
    PlayerQuestObjective,
    QuestEvent,
    TrackedQuest,
    now,
)
from app.quest_repository import QuestRepository


class QuestService:
    def __init__(self, session: Session, user_id: int):
        self.session, self.user_id = session, user_id
        self.repo = QuestRepository(session)

    def definition(self, quest_id):
        quest = self.repo.definition(quest_id)
        if quest is None:
            raise HTTPException(404, "Quest not found")
        return quest

    def available(self, quest):
        prerequisites = quest.availability_config.get("completed_quests", [])
        if not isinstance(prerequisites, list):
            return False
        completed = set(
            self.session.scalars(
                select(PlayerQuest.quest_id).where(
                    PlayerQuest.user_id == self.user_id,
                    PlayerQuest.status == "completed",
                )
            )
        )
        return set(prerequisites) <= completed

    def view(self, quest):
        player = self.repo.player(self.user_id, quest.id)
        progress = self.repo.progress(player.id) if player else {}
        tracked = self.session.get(TrackedQuest, self.user_id)
        return {
            "id": quest.id,
            "slug": quest.slug,
            "title": quest.title,
            "description": quest.description,
            "category": quest.category,
            "location_slug": quest.location_slug,
            "giver_npc_id": quest.giver_npc_id,
            "status": player.status
            if player and player.status != "offered"
            else ("available" if self.available(quest) else "locked"),
            "accepted_at": player.accepted_at if player else None,
            "completed_at": player.completed_at if player else None,
            "tracked": bool(
                player and tracked and tracked.player_quest_id == player.id
            ),
            "objectives": [
                {
                    "id": o.id,
                    "title": o.title,
                    "description": o.description,
                    "objective_type": o.objective_type,
                    "required_count": o.required_count,
                    "current_count": progress[o.id].current_count
                    if o.id in progress
                    else 0,
                    "completed": bool(o.id in progress and progress[o.id].completed_at),
                    "is_required": o.is_required,
                }
                for o in self.repo.objectives(quest.id)
            ],
        }

    def offer(self, quest_id, npc_id):
        self.repo.lock_user(self.user_id)
        quest = self.definition(quest_id)
        if quest.giver_npc_id != npc_id or not self.available(quest):
            raise HTTPException(404, "Quest not available from this NPC")
        player = self.repo.player(self.user_id, quest_id)
        if not player:
            player = PlayerQuest(
                user_id=self.user_id,
                quest_id=quest_id,
                status="offered",
                offered_at=now(),
            )
            self.session.add(player)
            self.session.commit()
        return self.view(quest)

    def accept(self, quest_id):
        self.repo.lock_user(self.user_id)
        quest = self.definition(quest_id)
        player = self.repo.player(self.user_id, quest_id)
        if not player or not self.available(quest):
            raise HTTPException(409, "Quest must be offered first")
        if player.status == "active":
            return self.view(quest)
        if player.status not in ("offered", "abandoned"):
            raise HTTPException(409, "Quest cannot be accepted")
        player.status = "active"
        player.accepted_at = player.accepted_at or now()
        player.abandoned_at = None
        self.session.commit()
        return self.view(quest)

    def abandon(self, quest_id):
        self.repo.lock_user(self.user_id)
        quest = self.definition(quest_id)
        player = self.repo.player(self.user_id, quest_id)
        if (
            not player
            or player.status not in ("active", "abandoned")
            or quest.category == "main"
        ):
            raise HTTPException(409, "Quest cannot be abandoned")
        if player.status == "active":
            player.status, player.abandoned_at = "abandoned", now()
            tracked = self.session.get(TrackedQuest, self.user_id)
            if tracked and tracked.player_quest_id == player.id:
                self.session.delete(tracked)
            self.session.commit()
        return self.view(quest)

    def track(self, quest_id):
        self.repo.lock_user(self.user_id)
        tracked = self.session.get(TrackedQuest, self.user_id)
        if quest_id is None:
            if tracked:
                self.session.delete(tracked)
        else:
            quest = self.definition(quest_id)
            player = self.repo.player(self.user_id, quest.id)
            if not player or player.status != "active":
                raise HTTPException(409, "Only active quests can be tracked")
            if tracked:
                tracked.player_quest_id = player.id
            else:
                self.session.add(
                    TrackedQuest(user_id=self.user_id, player_quest_id=player.id)
                )
        self.session.commit()

    def terminal(self, request_id):
        self.repo.lock_user(self.user_id)
        previous = self.repo.event(self.user_id, request_id)
        if previous:
            if (
                previous.event_type != "terminal_opened"
                or previous.target_key != "backend_terminal"
            ):
                raise HTTPException(409, "Request ID has different content")
            return previous.result
        for quest in self.repo.definitions():
            if quest.slug != "server-on-vacation":
                continue
            player = self.repo.player(self.user_id, quest.id)
            if not player or player.status != "active":
                break
            objectives = self.repo.objectives(quest.id)
            progress = self.repo.progress(player.id)
            current = next(
                (
                    o
                    for o in objectives
                    if not (o.id in progress and progress[o.id].completed_at)
                ),
                None,
            )
            if current and current.objective_type in (
                "terminal_investigated",
                "terminal_problem_fixed",
            ):
                result = {
                    "log": (
                        "Проверка: прокси ожидает порт 8080; сервер слушает порт 8000."
                    ),
                    "port": 8000,
                }
                self.session.add(
                    QuestEvent(
                        user_id=self.user_id,
                        request_id=request_id,
                        event_type="terminal_opened",
                        target_key="backend_terminal",
                        payload={},
                        result=result,
                    )
                )
                self.session.commit()
                return result
        raise HTTPException(409, "Terminal is not available yet")

    def interact(self, request_id, event_type, target_key, payload):
        self.repo.lock_user(self.user_id)
        previous = self.repo.event(self.user_id, request_id)
        if previous:
            if (previous.event_type, previous.target_key, previous.payload) != (
                event_type,
                target_key,
                payload,
            ):
                raise HTTPException(409, "Request ID has different content")
            return previous.result
        changed = []
        for quest in self.repo.definitions():
            player = self.repo.player(self.user_id, quest.id)
            if not player or player.status != "active":
                continue
            objectives = self.repo.objectives(quest.id)
            progress = self.repo.progress(player.id)
            # Optional objectives do not prevent the next required objective.
            # A later objective cannot be reached while an earlier required one is open.
            current = next(
                (
                    o
                    for o in objectives
                    if (o.objective_type, o.target_key) == (event_type, target_key)
                    and not (o.id in progress and progress[o.id].completed_at)
                    and all(
                        not prior.is_required
                        or prior.order_index >= o.order_index
                        or (prior.id in progress and progress[prior.id].completed_at)
                        for prior in objectives
                    )
                ),
                None,
            )
            if not current:
                continue
            if event_type in ("terminal_investigated", "terminal_problem_fixed"):
                issued = self.session.scalar(
                    select(QuestEvent.id).where(
                        QuestEvent.user_id == self.user_id,
                        QuestEvent.event_type == "terminal_opened",
                        QuestEvent.target_key == target_key,
                    )
                )
                if not issued:
                    raise HTTPException(409, "Open the terminal first")
            expected = current.validation_config.get("payload", {})
            if not isinstance(expected, dict) or any(
                payload.get(k) != v for k, v in expected.items()
            ):
                raise HTTPException(422, "Configuration check failed")
            item = progress.get(current.id)
            if not item:
                item = PlayerQuestObjective(
                    player_quest_id=player.id, objective_id=current.id, current_count=0
                )
                self.session.add(item)
                progress[current.id] = item
            item.current_count = min(item.current_count + 1, current.required_count)
            if item.current_count >= current.required_count:
                item.completed_at = now()
            if all(
                not o.is_required or (o.id in progress and progress[o.id].completed_at)
                for o in objectives
            ):
                player.status, player.completed_at = "completed", now()
                tracked = self.session.get(TrackedQuest, self.user_id)
                if tracked and tracked.player_quest_id == player.id:
                    self.session.delete(tracked)
            changed.append(
                {
                    "quest_id": quest.id,
                    "objective_id": current.id,
                    "objective_completed": bool(item.completed_at),
                    "quest_completed": player.status == "completed",
                }
            )
        if not changed:
            raise HTTPException(409, "Interaction is not valid for a current objective")
        result = {"accepted": True, "changes": changed}
        self.session.add(
            QuestEvent(
                user_id=self.user_id,
                request_id=request_id,
                event_type=event_type,
                target_key=target_key,
                payload=payload,
                result=result,
            )
        )
        self.session.commit()
        return result
