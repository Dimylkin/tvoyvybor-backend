from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_api import current_user
from app.database import get_session
from app.models import Achievement, CareerDirection, User, UserAchievement
from app.quest_models import PlayerQuest, QuestDefinition

router = APIRouter(prefix="/game", tags=["game state"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]


class StoryState(BaseModel):
    intro_completed: bool
    final_quest_unlocked: bool
    final_quest_completed: bool
    main_story_completed: bool


def final_unlocked(session: Session, user_id: int) -> bool:
    required_directions = {"backend", "frontend", "analytics"}
    definitions = list(
        session.scalars(
            select(QuestDefinition).where(QuestDefinition.is_published.is_(True))
        )
    )
    required = [
        quest
        for quest in definitions
        if quest.availability_config.get("engine") == 2
        and quest.availability_config.get("kind")
        and quest.direction_id is not None
    ]
    directions = {
        slug
        for quest in required
        if (
            slug := session.scalar(
                select(CareerDirection.slug).where(
                    CareerDirection.id == quest.direction_id
                )
            )
        )
    }
    if not required or not required_directions <= directions:
        return False
    completed = set(
        session.scalars(
            select(PlayerQuest.quest_id).where(
                PlayerQuest.user_id == user_id,
                PlayerQuest.status == "completed",
            )
        )
    )
    return all(quest.id in completed for quest in required)


@router.get("/state", response_model=StoryState)
def state(session: SessionDep, user: UserDep) -> StoryState:
    return StoryState(
        intro_completed=user.intro_completed,
        final_quest_unlocked=final_unlocked(session, user.id),
        final_quest_completed=user.main_story_completed,
        main_story_completed=user.main_story_completed,
    )


@router.put("/intro-complete", response_model=StoryState)
def complete_intro(session: SessionDep, user: UserDep) -> StoryState:
    user.intro_completed = True
    user.onboarding_completed = True
    session.commit()
    return state(session, user)


@router.put("/final-quest/complete", response_model=StoryState)
def complete_final(session: SessionDep, user: UserDep) -> StoryState:
    locked_user = session.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    if not final_unlocked(session, user.id):
        raise HTTPException(409, "Final quest is not unlocked")
    if locked_user is not None and not locked_user.main_story_completed:
        achievement = session.scalar(
            select(Achievement).where(Achievement.slug == "tried-everything")
        )
        if achievement is None:
            achievement = Achievement(
                slug="tried-everything",
                title="Теперь хотя бы не наугад",
                description=(
                    "Познакомиться со всеми доступными IT-направлениями "
                    "и завершить итоговый разговор."
                ),
            )
            session.add(achievement)
            session.flush()
        if not session.scalar(
            select(UserAchievement.id).where(
                UserAchievement.user_id == user.id,
                UserAchievement.achievement_id == achievement.id,
            )
        ):
            session.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
        locked_user.main_story_completed = True
        session.commit()
    return state(session, user)
