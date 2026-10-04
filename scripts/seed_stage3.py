"""Create a small published choice scenario for manual stage 3 checks.

Run with ``python -m scripts.seed_stage3`` after applying migrations.
The script uses DATABASE_URL and other backend settings from the environment.
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.database import SessionLocal
from app.models import CareerDirection, Scenario, Task

DIRECTION_SLUG = "backend"
SCENARIO_SLUG = "stage-3-choice-demo"


@dataclass(frozen=True)
class Choice:
    title: str
    prompt: str
    options: tuple[str, ...]
    correct: str
    correct_explanation: str
    incorrect_explanation: str


CHOICES = (
    Choice(
        title="Метод для чтения данных",
        prompt="Какой HTTP-метод обычно используют для получения ресурса?",
        options=("GET", "POST", "DELETE"),
        correct="GET",
        correct_explanation="GET запрашивает представление ресурса.",
        incorrect_explanation="Для чтения ресурса обычно используют GET.",
    ),
    Choice(
        title="Код успешного создания",
        prompt="Какой HTTP-статус означает, что ресурс создан?",
        options=("200", "201", "404"),
        correct="201",
        correct_explanation="201 Created означает успешное создание ресурса.",
        incorrect_explanation="Создание ресурса обозначают статусом 201 Created.",
    ),
    Choice(
        title="Код отсутствующего ресурса",
        prompt="Какой статус вернуть, если ресурс по указанному ID не найден?",
        options=("400", "404", "500"),
        correct="404",
        correct_explanation="404 Not Found сообщает, что ресурс не найден.",
        incorrect_explanation="Отсутствующему ресурсу соответствует 404 Not Found.",
    ),
    Choice(
        title="Формат тела запроса",
        prompt="Какой Content-Type у JSON-тела HTTP-запроса?",
        options=("application/json", "text/plain", "image/png"),
        correct="application/json",
        correct_explanation="Для JSON используют Content-Type: application/json.",
        incorrect_explanation="JSON-тело передают с Content-Type: application/json.",
    ),
    Choice(
        title="Проверка входных данных",
        prompt="Что должен сделать API с некорректным входным значением?",
        options=("Принять без проверки", "Вернуть ошибку валидации", "Удалить ресурс"),
        correct="Вернуть ошибку валидации",
        correct_explanation="Некорректный запрос должен получить ошибку валидации.",
        incorrect_explanation="API должен отклонить некорректные входные данные.",
    ),
)


def seed() -> tuple[int, int]:
    """Create missing seed rows without modifying unrelated content or users."""
    with SessionLocal.begin() as session:
        direction = session.scalar(
            select(CareerDirection).where(CareerDirection.slug == DIRECTION_SLUG)
        )
        if direction is None:
            direction = CareerDirection(
                slug=DIRECTION_SLUG,
                title="Backend",
                description="Разработка серверных приложений и API.",
            )
            session.add(direction)
            session.flush()

        scenario = session.scalar(
            select(Scenario).where(
                Scenario.direction_id == direction.id,
                Scenario.slug == SCENARIO_SLUG,
            )
        )
        if scenario is None:
            scenario = Scenario(
                direction_id=direction.id,
                slug=SCENARIO_SLUG,
                title="Пробный сценарий: основы API",
                description="Пять вопросов для проверки механики попыток.",
                is_published=False,
            )
            session.add(scenario)
            session.flush()

        existing_tasks = {
            task.title: task
            for task in session.scalars(
                select(Task).where(Task.scenario_id == scenario.id)
            )
        }
        if scenario.is_published and any(
            choice.title not in existing_tasks for choice in CHOICES
        ):
            raise ValueError("Cannot add tasks to an already published scenario")
        created = 0
        for choice in CHOICES:
            task = existing_tasks.get(choice.title)
            if task is None:
                session.add(
                    Task(
                        scenario_id=scenario.id,
                        kind="choice",
                        title=choice.title,
                        content={
                            "prompt": choice.prompt,
                            "options": list(choice.options),
                        },
                        validation_config={"correct": choice.correct},
                        correct_explanation=choice.correct_explanation,
                        incorrect_explanation=choice.incorrect_explanation,
                        is_published=True,
                    )
                )
                created += 1
            else:
                expected_content = {
                    "prompt": choice.prompt,
                    "options": list(choice.options),
                }
                if (
                    task.kind != "choice"
                    or task.content != expected_content
                    or task.validation_config != {"correct": choice.correct}
                ):
                    raise ValueError(
                        f"Task {choice.title!r} already exists with different content"
                    )
                task.is_published = True

        session.flush()
        scenario.is_published = True
        return scenario.id, created


if __name__ == "__main__":
    scenario_id, created = seed()
    print(f"Scenario {scenario_id}: {created} tasks created; published.")
