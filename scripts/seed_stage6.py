# ruff: noqa: E501
"""Create the published three-direction content set for roadmap stage 6.

Run with ``python -m scripts.seed_stage6`` after applying migrations.  It is
idempotent and refuses to silently replace an existing task with other content.
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.database import SessionLocal
from app.models import CareerDirection, Scenario, Task


@dataclass(frozen=True)
class Choice:
    title: str
    context: str
    prompt: str
    options: tuple[str, str, str]
    correct_explanation: str
    incorrect_explanation: str


@dataclass(frozen=True)
class ScenarioSeed:
    slug: str
    title: str
    description: str
    choice: Choice


@dataclass(frozen=True)
class DirectionSeed:
    slug: str
    title: str
    description: str
    scenarios: tuple[ScenarioSeed, ScenarioSeed, ScenarioSeed, ScenarioSeed]


def scenario(
    slug: str,
    title: str,
    description: str,
    task_title: str,
    context: str,
    prompt: str,
    correct: str,
    first_wrong: str,
    second_wrong: str,
    correct_explanation: str,
    incorrect_explanation: str,
) -> ScenarioSeed:
    return ScenarioSeed(
        slug,
        title,
        description,
        Choice(
            task_title,
            context,
            prompt,
            (correct, first_wrong, second_wrong),
            correct_explanation,
            incorrect_explanation,
        ),
    )


DIRECTIONS = (
    DirectionSeed(
        "backend",
        "Backend",
        "Разработка серверных приложений, API и данных.",
        (
            scenario(
                "api-contract",
                "Контракт API",
                "Клиент ждёт данные профиля.",
                "Выбрать метод чтения",
                "Ты реализуешь экран профиля: нужно получить существующие данные без изменения состояния.",
                "Какой HTTP-метод подходит для чтения профиля?",
                "GET",
                "POST",
                "DELETE",
                "Верно: GET используют для получения представления существующего ресурса.",
                "Не совсем: чтение существующего ресурса обычно оформляют методом GET.",
            ),
            scenario(
                "validation-boundary",
                "Граница валидации",
                "Endpoint получает параметры отчёта.",
                "Отклонить неверный ввод",
                "Пользователь передал дату в недопустимом формате; до бизнес-логики запрос ещё не дошёл.",
                "Как должен поступить API?",
                "Вернуть ошибку валидации",
                "Подставить случайную дату",
                "Удалить отчёт",
                "Верно: сервер проверяет входные данные и сообщает о некорректном запросе.",
                "Не совсем: некорректные входные данные нельзя молча исправлять или превращать в другое действие.",
            ),
            scenario(
                "database-change",
                "Изменение схемы",
                "Для профиля требуется новое поле в PostgreSQL.",
                "Выбрать безопасное изменение",
                "Модель SQLAlchemy уже дополнена полем, но существующая база ещё не знает о новом столбце.",
                "Что нужно подготовить вместе с изменением модели?",
                "Миграцию Alembic",
                "Только перезапуск браузера",
                "Новый CSS-файл",
                "Верно: миграция Alembic фиксирует воспроизводимое изменение схемы базы данных.",
                "Не совсем: изменение Python-модели само по себе не меняет схему существующей базы.",
            ),
            scenario(
                "incident-response",
                "Разбор ошибки",
                "После релиза запрос завершился ошибкой 500.",
                "Начать расследование",
                "Пользователь сообщает время и URL неудачного запроса; проблема не воспроизводится на главной странице.",
                "Что полезнее всего проверить сначала?",
                "Структурированные логи запроса",
                "Цвет кнопки",
                "Удалить базу данных",
                "Верно: логи с контекстом запроса помогают локализовать серверную ошибку.",
                "Не совсем: сначала нужна наблюдаемая причина сбоя, а не разрушительное действие.",
            ),
        ),
    ),
    DirectionSeed(
        "frontend",
        "Frontend",
        "Создание понятных и доступных пользовательских интерфейсов.",
        (
            scenario(
                "loading-state",
                "Состояние загрузки",
                "Экран рекомендаций ждёт ответ API.",
                "Показать ожидание",
                "Запрос ещё выполняется, а данные рекомендаций пока недоступны.",
                "Что должен увидеть пользователь до ответа сервера?",
                "Индикатор загрузки",
                "Устаревшие данные как новые",
                "Пустую белую страницу",
                "Верно: явное состояние загрузки объясняет, что приложение работает и ожидает данные.",
                "Не совсем: скрывать ожидание или выдавать старые данные за новые создаёт недоверие.",
            ),
            scenario(
                "form-feedback",
                "Обратная связь формы",
                "Пользователь отправляет регистрацию без пароля.",
                "Объяснить ошибку",
                "Проверка на клиенте обнаружила, что обязательное поле пустое.",
                "Какую реакцию интерфейса выбрать?",
                "Показать понятное сообщение у поля",
                "Молча очистить email",
                "Отправить форму всё равно",
                "Верно: привязанная к полю подсказка помогает пользователю исправить ввод.",
                "Не совсем: пользователь должен понять причину ошибки и способ её исправить.",
            ),
            scenario(
                "component-state",
                "Состояние компонента",
                "Модальное окно задания закрывается после успеха.",
                "Обновить UI после успеха",
                "API подтвердил правильный ответ, и игрок возвращается к сцене.",
                "Что должно быть источником состояния завершения?",
                "Подтверждённый ответ API",
                "Случайный таймер",
                "Только локальная догадка до запроса",
                "Верно: UI отражает подтверждённый сервером результат и прогресс переживает перезагрузку.",
                "Не совсем: локальная догадка до ответа сервера может расходиться с сохранённым прогрессом.",
            ),
            scenario(
                "accessible-action",
                "Доступное действие",
                "В хабе есть запуск сценария.",
                "Сделать действие доступным",
                "Пользователь управляет интерфейсом клавиатурой и должен понимать назначение элемента.",
                "Какой элемент лучше использовать для запуска сценария?",
                "Семантическую кнопку с названием",
                "Кликабельный div без подписи",
                "Только декоративную иконку",
                "Верно: семантическая кнопка поддерживает клавиатуру и передаёт назначение вспомогательным технологиям.",
                "Не совсем: интерактивный элемент должен быть доступен не только мышью и иметь понятное название.",
            ),
        ),
    ),
    DirectionSeed(
        "analytics",
        "Analytics",
        "Анализ данных, метрик и обоснование решений.",
        (
            scenario(
                "metric-question",
                "Вопрос к данным",
                "Команда изучает возвращаемость игроков.",
                "Сформулировать метрику",
                "Нужно измерить долю пользователей, которые вернулись и прошли ещё один сценарий.",
                "Какой подход корректнее?",
                "Определить retention и период измерения",
                "Сразу выбрать самый красивый график",
                "Удалить неполные события",
                "Верно: сначала фиксируют вопрос, определение метрики и период, а затем выбирают визуализацию.",
                "Не совсем: без определения метрики график не отвечает на продуктовый вопрос.",
            ),
            scenario(
                "data-quality",
                "Качество данных",
                "В событиях появились пустые идентификаторы сценария.",
                "Проверить аномалию",
                "Часть строк не связывается со сценарием и может исказить отчёт.",
                "Какое действие выполнить перед расчётом метрики?",
                "Проверить источник и долю пропусков",
                "Считать пустые значения нулём без проверки",
                "Скрыть столбец",
                "Верно: качество данных оценивают до интерпретации результата.",
                "Не совсем: подмена или сокрытие пропусков без проверки делает выводы ненадёжными.",
            ),
            scenario(
                "category-comparison",
                "Сравнение категорий",
                "Нужно сравнить завершения сценариев в трёх направлениях.",
                "Выбрать визуализацию",
                "Есть три независимые категории и количество завершений в каждой.",
                "Какой график лучше показывает сравнение категорий?",
                "Столбчатая диаграмма",
                "Круговая диаграмма с десятками секторов",
                "Случайный набор цветов",
                "Верно: столбчатая диаграмма наглядно сравнивает величины между категориями.",
                "Не совсем: для точного сравнения важнее общая шкала, а не декоративность.",
            ),
            scenario(
                "experiment-result",
                "Результат эксперимента",
                "После изменения подсказки выросла конверсия.",
                "Сообщить вывод честно",
                "Разница многообещающая, но выборка ещё не достигла заранее заданного размера.",
                "Как корректно представить результат команде?",
                "Отметить неопределённость и продолжить сбор данных",
                "Объявить победу без оговорок",
                "Удалить неудобные наблюдения",
                "Верно: аналитик отделяет наблюдаемый сигнал от уверенного вывода и сообщает ограничения выборки.",
                "Не совсем: преждевременный вывод или выборочное удаление данных искажает решение команды.",
            ),
        ),
    ),
)


def content(choice: Choice) -> dict[str, object]:
    return {
        "context": choice.context,
        "prompt": choice.prompt,
        "options": list(choice.options),
    }


def seed() -> tuple[int, int]:
    """Create missing stage-6 scenarios and tasks without touching user data."""
    created_scenarios = 0
    created_tasks = 0
    with SessionLocal.begin() as session:
        for direction_seed in DIRECTIONS:
            direction = session.scalar(
                select(CareerDirection).where(
                    CareerDirection.slug == direction_seed.slug
                )
            )
            if direction is None:
                direction = CareerDirection(
                    slug=direction_seed.slug,
                    title=direction_seed.title,
                    description=direction_seed.description,
                )
                session.add(direction)
                session.flush()
            for scenario_seed in direction_seed.scenarios:
                item = session.scalar(
                    select(Scenario).where(
                        Scenario.direction_id == direction.id,
                        Scenario.slug == scenario_seed.slug,
                    )
                )
                if item is None:
                    item = Scenario(
                        direction_id=direction.id,
                        slug=scenario_seed.slug,
                        title=scenario_seed.title,
                        description=scenario_seed.description,
                        is_published=False,
                    )
                    session.add(item)
                    session.flush()
                    created_scenarios += 1
                task = session.scalar(
                    select(Task).where(
                        Task.scenario_id == item.id,
                        Task.title == scenario_seed.choice.title,
                    )
                )
                expected_content = content(scenario_seed.choice)
                expected_validation = {"correct": scenario_seed.choice.options[0]}
                if task is None:
                    if item.is_published:
                        raise ValueError(
                            "Cannot add tasks to an already published scenario"
                        )
                    task = Task(
                        scenario_id=item.id,
                        kind="choice",
                        title=scenario_seed.choice.title,
                        content=expected_content,
                        validation_config=expected_validation,
                        correct_explanation=scenario_seed.choice.correct_explanation,
                        incorrect_explanation=scenario_seed.choice.incorrect_explanation,
                        is_published=True,
                    )
                    session.add(task)
                    created_tasks += 1
                elif (
                    task.kind != "choice"
                    or task.content != expected_content
                    or task.validation_config != expected_validation
                    or task.correct_explanation
                    != scenario_seed.choice.correct_explanation
                    or task.incorrect_explanation
                    != scenario_seed.choice.incorrect_explanation
                ):
                    raise ValueError(
                        f"Task {scenario_seed.choice.title!r} already exists with different content"
                    )
                else:
                    task.is_published = True
                item.is_published = True
    return created_scenarios, created_tasks


if __name__ == "__main__":
    scenarios, tasks = seed()
    print(f"Stage 6: {scenarios} scenarios and {tasks} tasks created; published.")
