from sqlalchemy.exc import IntegrityError

from app.content_repository import ContentRepository
from app.models import CareerDirection, Progress, Scenario, ScenarioState, Task


class ContentNotFoundError(Exception):
    pass


class ContentConflictError(Exception):
    pass


def state_after_start(current: ScenarioState) -> ScenarioState:
    """Validate the stage 2 start transition without persistence concerns."""
    if current in (ScenarioState.AVAILABLE, ScenarioState.ACTIVE):
        return ScenarioState.ACTIVE
    raise ContentConflictError("Scenario cannot be started")


class ContentService:
    def __init__(self, repository: ContentRepository) -> None:
        self.repository = repository

    def create_direction(
        self, slug: str, title: str, description: str
    ) -> CareerDirection:
        try:
            return self.repository.add(
                CareerDirection(slug=slug, title=title, description=description)
            )
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise ContentConflictError("Direction slug already exists") from exc

    def create_scenario(
        self, direction_id: int, slug: str, title: str, description: str
    ) -> Scenario:
        if self.repository.direction(direction_id) is None:
            raise ContentNotFoundError
        try:
            return self.repository.add(
                Scenario(
                    direction_id=direction_id,
                    slug=slug,
                    title=title,
                    description=description,
                    is_published=False,
                )
            )
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise ContentConflictError("Scenario slug already exists") from exc

    def create_task(
        self,
        scenario_id: int,
        kind: str,
        title: str,
        content: dict,
        validation_config: dict,
        correct_explanation: str,
        incorrect_explanation: str,
    ) -> Task:
        if self.repository.scenario(scenario_id) is None:
            raise ContentNotFoundError
        return self.repository.add(
            Task(
                scenario_id=scenario_id,
                kind=kind,
                title=title,
                content=content,
                validation_config=validation_config,
                correct_explanation=correct_explanation,
                incorrect_explanation=incorrect_explanation,
                is_published=False,
            )
        )

    def publish_task(self, task_id: int) -> Task:
        task = self.repository.task(task_id)
        if task is None:
            raise ContentNotFoundError
        if not task.is_published:
            task.is_published = True
            self.repository.save()
        return task

    def publish_scenario(self, scenario_id: int) -> Scenario:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if not scenario.is_published:
            if not self.repository.tasks(scenario_id, published_only=True):
                raise ContentConflictError("Publish at least one task first")
            scenario.is_published = True
            self.repository.save()
        return scenario

    def published_scenario(self, scenario_id: int) -> Scenario:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None or not scenario.is_published:
            raise ContentNotFoundError
        return scenario

    def scenario_state(self, user_id: int, scenario_id: int) -> ScenarioState:
        self.published_scenario(scenario_id)
        progress = self.repository.progress(user_id, scenario_id)
        return progress.state if progress is not None else ScenarioState.AVAILABLE

    def start_scenario(self, user_id: int, scenario_id: int) -> ScenarioState:
        self.published_scenario(scenario_id)
        progress = self.repository.progress(user_id, scenario_id)
        if progress is None:
            try:
                self.repository.add(
                    Progress(
                        user_id=user_id,
                        scenario_id=scenario_id,
                        state=state_after_start(ScenarioState.AVAILABLE),
                    )
                )
            except IntegrityError as exc:
                self.repository.session.rollback()
                progress = self.repository.progress(user_id, scenario_id)
                if progress is None:
                    raise ContentConflictError("Scenario cannot be started") from exc
            else:
                return ScenarioState.ACTIVE
        next_state = state_after_start(progress.state)
        if progress.state != next_state:
            progress.state = next_state
            self.repository.save()
        return next_state
