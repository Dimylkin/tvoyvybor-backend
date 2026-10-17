from sqlalchemy.exc import IntegrityError

from app.content_repository import ContentRepository
from app.models import CareerDirection, Progress, Scenario, ScenarioState, Task
from app.task_strategy import (
    InvalidTaskConfigError,
    UnsupportedTaskKindError,
    strategy_for,
)


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
            scenario = self.repository.scenario(task.scenario_id)
            if scenario is None or scenario.is_published:
                raise ContentConflictError("Published scenario content is fixed")
            try:
                strategy_for(task.kind).validate("", task.validation_config)
            except (InvalidTaskConfigError, UnsupportedTaskKindError) as exc:
                raise ContentConflictError("Task validation is not configured") from exc
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

    def update_scenario(
        self,
        scenario_id: int,
        direction_id: int,
        slug: str,
        title: str,
        description: str,
    ) -> Scenario:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if scenario.is_published:
            raise ContentConflictError("Published scenario content is fixed")
        if self.repository.direction(direction_id) is None:
            raise ContentNotFoundError
        scenario.direction_id = direction_id
        scenario.slug = slug
        scenario.title = title
        scenario.description = description
        try:
            self.repository.save()
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise ContentConflictError("Scenario slug already exists") from exc
        return scenario

    def delete_scenario(self, scenario_id: int) -> None:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if scenario.is_published or self._scenario_consumed(scenario_id):
            raise ContentConflictError("Consumed scenario content cannot be deleted")
        for task in self.repository.tasks(scenario_id, published_only=False):
            self.repository.session.delete(task)
        self.repository.delete(scenario)

    def unpublish_scenario(self, scenario_id: int) -> Scenario:
        scenario = self.repository.scenario(scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if self._scenario_consumed(scenario_id):
            raise ContentConflictError(
                "Consumed scenario content cannot be unpublished"
            )
        if scenario.is_published:
            scenario.is_published = False
            for task in self.repository.tasks(scenario_id, published_only=False):
                task.is_published = False
            self.repository.save()
        return scenario

    def update_task(
        self,
        task_id: int,
        kind: str,
        title: str,
        content: dict,
        validation_config: dict,
        correct_explanation: str,
        incorrect_explanation: str,
    ) -> Task:
        task = self.repository.task(task_id)
        if task is None:
            raise ContentNotFoundError
        scenario = self.repository.scenario(task.scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if (
            task.is_published
            or scenario.is_published
            or self.repository.task_has_attempts(task_id)
        ):
            raise ContentConflictError("Published task content is fixed")
        self._validate_task(kind, validation_config)
        task.kind = kind
        task.title = title
        task.content = content
        task.validation_config = validation_config
        task.correct_explanation = correct_explanation
        task.incorrect_explanation = incorrect_explanation
        self.repository.save()
        return task

    def delete_task(self, task_id: int) -> None:
        task = self.repository.task(task_id)
        if task is None:
            raise ContentNotFoundError
        scenario = self.repository.scenario(task.scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if (
            task.is_published
            or scenario.is_published
            or self.repository.task_has_attempts(task_id)
        ):
            raise ContentConflictError("Published task content is fixed")
        self.repository.delete(task)

    def unpublish_task(self, task_id: int) -> Task:
        task = self.repository.task(task_id)
        if task is None:
            raise ContentNotFoundError
        scenario = self.repository.scenario(task.scenario_id)
        if scenario is None:
            raise ContentNotFoundError
        if scenario.is_published or self.repository.task_has_attempts(task_id):
            raise ContentConflictError("Consumed task content cannot be unpublished")
        if task.is_published:
            task.is_published = False
            self.repository.save()
        return task

    def _validate_task(self, kind: str, validation_config: dict) -> None:
        try:
            strategy_for(kind).validate("", validation_config)
        except (InvalidTaskConfigError, UnsupportedTaskKindError) as exc:
            raise ContentConflictError("Task validation is not configured") from exc

    def _scenario_consumed(self, scenario_id: int) -> bool:
        return self.repository.scenario_has_progress(
            scenario_id
        ) or self.repository.scenario_has_attempts(scenario_id)

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
