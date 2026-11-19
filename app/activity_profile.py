"""Explainable activity-interest profile built from gameplay evidence."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InterestEvent, Scenario, Task
from app.quest_models import PlayerQuest, QuestDefinition, QuestEvent

GROUPS = {
    "coding": (
        "Работа с кодом",
        "Тебе было интересно писать код и разбираться в логике решения.",
    ),
    "investigation": (
        "Поиск причин",
        "Тебя увлекало выяснять, почему система ведёт себя именно так.",
    ),
    "data": (
        "Работа с данными",
        "Ты задерживался на сравнении показателей и проверке данных.",
    ),
    "visual": (
        "Визуальная часть",
        "Тебе было интересно менять отображение и замечать детали интерфейса.",
    ),
    "users": (
        "Взаимодействие с пользователем",
        "Ты обращал внимание на то, как человеку пользоваться системой.",
    ),
    "requirements": (
        "Исследование требований",
        "Тебе было интересно задавать вопросы и выяснять настоящую потребность.",
    ),
    "systems": (
        "Системное мышление",
        "Ты разбирался, как части системы связаны друг с другом.",
    ),
    "practical": (
        "Практическая техническая работа",
        "Тебе было интересно настраивать инструменты и проверять результат "
        "на практике.",
    ),
    "experimentation": (
        "Экспериментирование",
        "Ты пробовал варианты и смотрел, как меняется результат.",
    ),
    "uncertainty": (
        "Работа с неопределённостью",
        "Тебе было интересно разбираться без заранее известного ответа.",
    ),
    "patterns": (
        "Поиск закономерностей",
        "Ты проверял гипотезы и искал повторяющиеся связи.",
    ),
}

IMPACTS = {
    "diagnosis": ("investigation", "systems", "practical", "uncertainty"),
    "code": ("coding", "systems", "experimentation", "practical"),
    "responsive": ("visual", "users", "experimentation", "systems"),
    "ux": ("users", "visual", "requirements", "patterns"),
    "interview": ("requirements", "uncertainty", "systems", "users"),
    "data": ("data", "patterns", "investigation", "uncertainty"),
}

CAREERS = {
    "coding": [
        (
            "Software Development",
            "Здесь много программирования, логики и автоматизации.",
        ),
        ("Backend", "В backend часто проектируют логику сервисов и работу с данными."),
        ("Automation", "Автоматизация превращает повторяющиеся действия в программы."),
    ],
    "investigation": [
        ("QA", "В QA ищут причины сбоев и проверяют поведение продукта."),
        ("DevOps", "В DevOps диагностируют сервисы и автоматизируют их работу."),
        (
            "Cybersecurity",
            "В безопасности исследуют уязвимости и причины подозрительных событий.",
        ),
    ],
    "data": [
        (
            "Data Analytics",
            "Здесь исследуют показатели и помогают принимать решения на основе данных.",
        ),
        ("Data Science", "Можно проверять гипотезы и искать сигналы в наборах данных."),
        ("BI", "BI связывает данные с понятными отчётами и метриками."),
        (
            "Data Engineering",
            "Data Engineering готовит надёжные потоки данных для анализа.",
        ),
        (
            "Machine Learning",
            "В машинном обучении модели находят закономерности в данных.",
        ),
    ],
    "visual": [
        ("UI/UX Design", "Дизайнеры продумывают вид и понятность интерфейсов."),
        ("Frontend", "Frontend превращает интерфейсный замысел в работающий экран."),
        ("Data Visualization", "Визуализация помогает ясно показывать сложные данные."),
    ],
    "users": [
        ("UX Research", "Исследователи изучают реальные сценарии и затруднения людей."),
        ("Product Design", "Здесь улучшают целостный пользовательский опыт."),
        ("Frontend", "Во frontend много решений о взаимодействии с интерфейсом."),
    ],
    "requirements": [
        (
            "Business Analysis",
            "Бизнес-аналитики уточняют потребности и формулируют требования.",
        ),
        (
            "System Analysis",
            "Системные аналитики переводят потребности в поведение и контракты систем.",
        ),
        (
            "Product Management",
            "В продуктовой работе связывают проблемы пользователей и цели команды.",
        ),
    ],
    "systems": [
        (
            "Software Development",
            "Разработка объединяет код, логику и взаимодействие частей приложения.",
        ),
        (
            "QA",
            "Проверка системы помогает находить ошибки во взаимодействии её частей.",
        ),
        (
            "System Analysis",
            "Системный анализ рассматривает компоненты и связи целиком.",
        ),
        ("Backend", "Backend соединяет бизнес-логику, API и данные."),
        (
            "Data Engineering",
            "Data Engineering строит потоки между источниками и хранилищами.",
        ),
    ],
    "practical": [
        ("DevOps", "DevOps включает настройку окружений, инструментов и сервисов."),
        (
            "System Administration",
            "Системные администраторы настраивают и поддерживают инфраструктуру.",
        ),
        (
            "Embedded Systems",
            "В embedded сочетаются код и настройка физических устройств.",
        ),
    ],
    "experimentation": [
        ("QA", "Тестирование позволяет менять условия и наблюдать результат."),
        ("R&D", "В исследованиях и разработке проверяют разные подходы."),
        ("Machine Learning", "В ML экспериментируют с данными и качеством моделей."),
    ],
    "uncertainty": [
        (
            "Product Management",
            "В продукте часто приходится проверять, какую проблему стоит решать.",
        ),
        ("Cybersecurity", "Расследование угроз требует работы с неполными данными."),
        (
            "Data Science",
            "В Data Science гипотезы проверяют при неопределённых результатах.",
        ),
    ],
    "patterns": [
        ("Data Science", "Здесь ищут закономерности и проверяют гипотезы на данных."),
        ("Machine Learning", "ML учится находить повторяющиеся связи в примерах."),
        ("Data Analytics", "Аналитики сравнивают показатели и объясняют их изменения."),
    ],
}

LEARNING = {
    "coding": [
        ("Python или JavaScript", "Выбери один язык и сделай небольшой проект."),
        ("Задачи на логику", "Попробуй реализовать несколько простых алгоритмов."),
    ],
    "investigation": [
        ("Debugging", "Разбери небольшую ошибку по логам и проверь гипотезу."),
        ("Тестирование", "Попробуй найти граничные случаи и проверить их."),
    ],
    "data": [
        ("SQL", "Потренируйся задавать вопросы небольшой таблице."),
        (
            "Небольшой датасет",
            "Сравни показатели и проверь, чем объясняется заметное изменение.",
        ),
    ],
    "visual": [
        ("Figma или HTML/CSS", "Собери экран и проверь его на телефоне и компьютере.")
    ],
    "users": [
        (
            "Проверка интерфейса",
            "Попроси человека выполнить задачу и запиши, где он остановился.",
        )
    ],
    "requirements": [
        ("Описание проблемы", "Опиши пользователя, его затруднение и нужный результат.")
    ],
    "systems": [
        (
            "Схема сервиса",
            "Нарисуй компоненты небольшого приложения и потоки данных между ними.",
        )
    ],
    "practical": [
        (
            "Docker и Linux",
            "Запусти небольшой сервис локально и изучи его конфигурацию.",
        )
    ],
    "experimentation": [
        ("Мини-эксперимент", "Измени один параметр и сравни результат до и после.")
    ],
    "uncertainty": [
        (
            "Проверка гипотез",
            "Выбери вопрос, запиши возможные объяснения и найди данные для проверки.",
        )
    ],
    "patterns": [
        (
            "Таблица наблюдений",
            "Собери несколько примеров и поищи повторяющийся признак.",
        )
    ],
}

LEGACY_TASK_GROUPS = {
    "api-contract": ("coding", "systems"),
    "validation-boundary": ("coding", "investigation"),
    "database-change": ("systems", "practical"),
    "incident-response": ("investigation", "uncertainty"),
    "loading-state": ("visual", "users"),
    "form-feedback": ("users", "visual"),
    "component-state": ("systems", "experimentation"),
    "accessible-action": ("users", "visual"),
    "metric-question": ("data", "requirements"),
    "data-quality": ("data", "investigation"),
    "category-comparison": ("data", "visual", "patterns"),
    "experiment-result": ("data", "experimentation", "uncertainty"),
}


def activity_profile(session: Session, user_id: int) -> dict:
    scores: dict[str, int] = defaultdict(int)
    evidence: dict[str, list[str]] = defaultdict(list)
    performance = 0
    sessions = 0
    definitions = session.scalars(
        select(QuestDefinition).where(QuestDefinition.is_published.is_(True))
    ).all()
    for quest in definitions:
        player = session.scalar(
            select(PlayerQuest).where(
                PlayerQuest.user_id == user_id, PlayerQuest.quest_id == quest.id
            )
        )
        if not player:
            continue
        state_event = session.scalar(
            select(QuestEvent)
            .where(
                QuestEvent.user_id == user_id,
                QuestEvent.target_key == f"quest:{quest.id}",
                QuestEvent.event_type.in_(("minigame_action", "minigame_reset")),
            )
            .order_by(QuestEvent.id.desc())
        )
        state = state_event.result.get("state", {}) if state_event else {}
        kind = quest.availability_config.get("kind")
        impacts = IMPACTS.get(kind, ())
        if not impacts or not (
            player.status == "completed"
            or state.get("action_count", 0)
            or state.get("attempts", 0)
            or state.get("seen")
        ):
            continue
        sessions += 1
        reaction = state.get("reaction")
        # Self-reported interest and voluntary exploration outweigh task success.
        base = {"more": 4, "interesting": 3, "enough": 1, "not-mine": 0}.get(
            reaction, 1
        )
        engagement = min(2, int(bool(state.get("extra_exploration")))) + int(
            state.get("active_seconds", 0) >= 120
        )
        value = base + engagement
        for group in impacts:
            scores[group] += value
            reason = f"{quest.title}: {GROUPS[group][1]}"
            if reaction in ("more", "interesting"):
                reason += (
                    " Ты отметил, что было интересно."
                    if reaction == "interesting"
                    else " Ты захотел продолжить."
                )
            if engagement:
                reason += " Ты продолжал исследовать задачу."
            evidence[group].append(reason)
        performance += int(bool(state.get("success")))

    # Reconstruct a modest preliminary profile from old completed tasks; historical
    # records contain correctness but no self-reported interest or engagement.
    legacy = session.scalars(
        select(InterestEvent).where(
            InterestEvent.user_id == user_id,
            InterestEvent.source == "task_completed",
        )
    ).all()
    seen_legacy: set[int] = set()
    for event in legacy:
        if not event.task_id or event.task_id in seen_legacy:
            continue
        seen_legacy.add(event.task_id)
        slug = session.scalar(
            select(Scenario.slug)
            .join(Task, Task.scenario_id == Scenario.id)
            .where(Task.id == event.task_id)
        )
        for group in LEGACY_TASK_GROUPS.get(slug, ()):
            scores[group] += 1
            evidence[group].append(
                "Восстановлено по завершённому заданию; прежние данные "
                "не содержат самооценки интереса."
            )
        performance += 1
    ranked = sorted(
        (key for key, score in scores.items() if score > 0),
        key=lambda key: (-scores[key], key),
    )
    top = ranked[:5]
    career_scores: dict[str, int] = defaultdict(int)
    career_reasons: dict[str, list[str]] = defaultdict(list)
    career_order: list[str] = []
    for group in top:
        for name, reason in CAREERS[group]:
            if name not in career_order:
                career_order.append(name)
            career_scores[name] += scores[group]
            career_reasons[name].append(reason)
    careers = sorted(
        career_scores, key=lambda name: (-career_scores[name], career_order.index(name))
    )[:6]
    learning = []
    for group in top:
        for title, action in LEARNING[group]:
            if title not in {item["title"] for item in learning}:
                learning.append(
                    {"title": title, "action": action, "group": GROUPS[group][0]}
                )
            if len(learning) == 4:
                break
        if len(learning) == 4:
            break
    return {
        "event_count": sessions + len(seen_legacy),
        "performance_score": performance,
        "preliminary": sessions < 3,
        "groups": [
            {
                "code": key,
                "name": GROUPS[key][0],
                "description": GROUPS[key][1],
                "score": scores[key],
                "evidence_count": len(evidence[key]),
                "evidence": evidence[key][:3],
            }
            for key in top
        ],
        "careers": [
            {"name": name, "explanation": " ".join(dict.fromkeys(career_reasons[name]))}
            for name in careers
        ],
        "learning": learning,
        "additional": (
            "Data Engineering",
            "Похоже, тебе интересны и данные, и устройство систем. "
            "Data Engineering соединяет эти виды работы.",
        )
        if "data" in top and "systems" in top
        else None,
        "observations": sessions,
    }
