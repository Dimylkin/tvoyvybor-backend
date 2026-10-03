from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CareerDirection, Progress, Scenario, Task

ContentEntity = TypeVar("ContentEntity", CareerDirection, Scenario, Task, Progress)


class ContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: ContentEntity) -> ContentEntity:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def save(self) -> None:
        self.session.commit()

    def direction(self, direction_id: int) -> CareerDirection | None:
        return self.session.get(CareerDirection, direction_id)

    def scenario(self, scenario_id: int) -> Scenario | None:
        return self.session.get(Scenario, scenario_id)

    def task(self, task_id: int) -> Task | None:
        return self.session.get(Task, task_id)

    def directions(self) -> list[CareerDirection]:
        return list(
            self.session.scalars(
                select(CareerDirection)
                .join(Scenario, Scenario.direction_id == CareerDirection.id)
                .where(Scenario.is_published.is_(True))
                .distinct()
                .order_by(CareerDirection.id)
            )
        )

    def published_scenarios(self, direction_id: int | None = None) -> list[Scenario]:
        statement = select(Scenario).where(Scenario.is_published.is_(True))
        if direction_id is not None:
            statement = statement.where(Scenario.direction_id == direction_id)
        return list(self.session.scalars(statement.order_by(Scenario.id)))

    def tasks(self, scenario_id: int, *, published_only: bool) -> list[Task]:
        statement = select(Task).where(Task.scenario_id == scenario_id)
        if published_only:
            statement = statement.where(Task.is_published.is_(True))
        return list(self.session.scalars(statement.order_by(Task.id)))

    def progress(self, user_id: int, scenario_id: int) -> Progress | None:
        return self.session.scalar(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.scenario_id == scenario_id,
            )
        )

    def user_progress(self, user_id: int) -> list[Progress]:
        return list(
            self.session.scalars(
                select(Progress)
                .where(Progress.user_id == user_id)
                .order_by(Progress.id)
            )
        )
