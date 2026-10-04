from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Achievement,
    InterestEvent,
    InterestProfile,
    Progress,
    Recommendation,
    Task,
    TaskAttempt,
    User,
    UserAchievement,
)


class AttemptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def task(self, task_id: int) -> Task | None:
        return self.session.get(Task, task_id)

    def lock_user(self, user_id: int) -> None:
        self.session.scalar(select(User.id).where(User.id == user_id).with_for_update())

    def locked_progress(self, user_id: int, scenario_id: int) -> Progress | None:
        return self.session.scalar(
            select(Progress)
            .where(Progress.user_id == user_id, Progress.scenario_id == scenario_id)
            .with_for_update()
        )

    def request_attempt(self, user_id: int, request_id: str) -> TaskAttempt | None:
        return self.session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.user_id == user_id,
                TaskAttempt.request_id == request_id,
            )
        )

    def completed_task_ids(self, user_id: int, scenario_id: int) -> set[int]:
        return set(
            self.session.scalars(
                select(InterestEvent.task_id)
                .join(Task, Task.id == InterestEvent.task_id)
                .where(
                    InterestEvent.user_id == user_id,
                    InterestEvent.source == "task_completed",
                    Task.scenario_id == scenario_id,
                )
            )
        )

    def profile(self, user_id: int) -> InterestProfile | None:
        return self.session.scalar(
            select(InterestProfile)
            .where(InterestProfile.user_id == user_id)
            .with_for_update()
        )

    def recommendation(self, user_id: int) -> Recommendation | None:
        return self.session.scalar(
            select(Recommendation).where(Recommendation.user_id == user_id)
        )

    def first_task_achievement(self) -> Achievement | None:
        return self.session.scalar(
            select(Achievement).where(Achievement.slug == "first-task")
        )

    def achievement_awarded(self, user_id: int, achievement_id: int) -> bool:
        return (
            self.session.scalar(
                select(UserAchievement.id).where(
                    UserAchievement.user_id == user_id,
                    UserAchievement.achievement_id == achievement_id,
                )
            )
            is not None
        )

    def user_achievements(
        self, user_id: int
    ) -> list[tuple[UserAchievement, Achievement]]:
        return list(
            self.session.execute(
                select(UserAchievement, Achievement)
                .join(Achievement, Achievement.id == UserAchievement.achievement_id)
                .where(UserAchievement.user_id == user_id)
                .order_by(UserAchievement.id)
            )
        )

    def events(self, user_id: int) -> list[InterestEvent]:
        return list(
            self.session.scalars(
                select(InterestEvent)
                .where(InterestEvent.user_id == user_id)
                .order_by(InterestEvent.id)
            )
        )
