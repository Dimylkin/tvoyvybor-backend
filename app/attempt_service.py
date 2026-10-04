from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.attempt_repository import AttemptRepository
from app.content_repository import ContentRepository
from app.models import (
    InterestEvent,
    InterestProfile,
    Recommendation,
    ScenarioState,
    TaskAttempt,
    UserAchievement,
)
from app.task_strategy import strategy_for


class AttemptNotFoundError(Exception):
    pass


class AttemptConflictError(Exception):
    pass


@dataclass(frozen=True)
class TaskCompleted:
    user_id: int
    task_id: int
    direction_id: int
    attempt_id: int


@dataclass(frozen=True)
class AttemptResult:
    id: int
    task_id: int
    is_correct: bool
    explanation: str
    scenario_state: ScenarioState


def leading_direction(scores: dict[str, int]) -> int | None:
    if not scores:
        return None
    return min((int(key) for key in scores), key=lambda key: (-scores[str(key)], key))


class AttemptService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AttemptRepository(session)
        self.content = ContentRepository(session)

    def submit(
        self, user_id: int, task_id: int, request_id: str, answer: str
    ) -> AttemptResult:
        # Serialize this user's attempts across scenarios before updating the
        # shared profile, recommendation and one-time achievement.
        self.repository.lock_user(user_id)
        task = self.repository.task(task_id)
        if task is None or not task.is_published:
            raise AttemptNotFoundError
        scenario = self.content.scenario(task.scenario_id)
        if scenario is None or not scenario.is_published:
            raise AttemptNotFoundError

        progress = self.repository.locked_progress(user_id, scenario.id)
        if progress is None:
            raise AttemptConflictError("Start the scenario first")
        previous = self.repository.request_attempt(user_id, request_id)
        if previous is not None:
            if previous.task_id != task_id or previous.answer != answer:
                raise AttemptConflictError("Request ID has different content")
            return AttemptResult(
                id=previous.id,
                task_id=task_id,
                is_correct=previous.is_correct,
                explanation=previous.explanation,
                scenario_state=previous.scenario_state,
            )
        if progress.state != ScenarioState.ACTIVE:
            raise AttemptConflictError("Scenario is not active")

        completed_ids = self.repository.completed_task_ids(user_id, scenario.id)
        if task_id in completed_ids:
            raise AttemptConflictError("Task already completed")
        correct = strategy_for(task.kind).validate(answer, task.validation_config)
        explanation = (
            task.correct_explanation if correct else task.incorrect_explanation
        )
        attempt = TaskAttempt(
            user_id=user_id,
            task_id=task_id,
            request_id=request_id,
            answer=answer,
            is_correct=correct,
            explanation=explanation,
            scenario_state=progress.state,
        )
        self.session.add(attempt)
        self.session.flush()

        if correct:
            completed = TaskCompleted(
                user_id, task_id, scenario.direction_id, attempt.id
            )
            self._task_completed(completed)
            completed_ids.add(task_id)
            published_ids = {
                item.id for item in self.content.tasks(scenario.id, published_only=True)
            }
            if published_ids <= completed_ids:
                progress.state = ScenarioState.COMPLETED
        else:
            self.session.add(
                InterestEvent(
                    user_id=user_id,
                    task_id=task_id,
                    attempt_id=attempt.id,
                    source="task_attempt",
                    trait=None,
                    direction_id=scenario.direction_id,
                    weight=0,
                    explanation="Неверный ответ; задание можно попробовать снова",
                )
            )
        state = progress.state
        attempt.scenario_state = state
        result = AttemptResult(attempt.id, task_id, correct, explanation, state)
        self.session.commit()
        return result

    def _task_completed(self, completed: TaskCompleted) -> None:
        event = InterestEvent(
            user_id=completed.user_id,
            task_id=completed.task_id,
            attempt_id=completed.attempt_id,
            source="task_completed",
            trait=None,
            direction_id=completed.direction_id,
            weight=1,
            explanation="Верно выполнено задание направления",
        )
        self.session.add(event)
        profile = self.repository.profile(completed.user_id)
        if profile is None:
            profile = InterestProfile(
                user_id=completed.user_id,
                trait_scores={},
                direction_scores={},
                event_count=0,
            )
            self.session.add(profile)
        scores = dict(profile.direction_scores)
        key = str(completed.direction_id)
        scores[key] = scores.get(key, 0) + 1
        profile.direction_scores = scores
        profile.event_count += 1
        profile.updated_at = datetime.now(UTC)

        leader = leading_direction(scores)
        direction = self.content.direction(leader) if leader is not None else None
        explanation = (
            f"Предварительно: {direction.title}. "
            f"Верно выполнено заданий в направлении: {scores[str(leader)]}."
            if direction is not None
            else "Пока недостаточно выполненных заданий"
        )
        recommendation = self.repository.recommendation(completed.user_id)
        if recommendation is None:
            recommendation = Recommendation(
                user_id=completed.user_id,
                direction_id=leader,
                explanation=explanation,
            )
            self.session.add(recommendation)
        else:
            recommendation.direction_id = leader
            recommendation.explanation = explanation
            recommendation.updated_at = datetime.now(UTC)

        achievement = self.repository.first_task_achievement()
        if achievement is not None and not self.repository.achievement_awarded(
            completed.user_id, achievement.id
        ):
            self.session.add(
                UserAchievement(
                    user_id=completed.user_id, achievement_id=achievement.id
                )
            )
