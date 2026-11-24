"""Versioned, explainable career indices from explicit player ratings."""

from collections import defaultdict

from sqlalchemy import select

from app.activity_profile import LABELS
from app.quest_models import PlayerQuest, QuestDefinition, QuestEvent
from app.quest_service import QuestService
from app.questionnaire_service import QuestionnaireService, signals

# Each observed action has an action trait and a subject trait in its own context.
TRAITS = {
    "diagnosis": {
        "investigation": ("investigation", "systems"),
        "coding": ("fixing", "code"),
        "verification": ("testing", "systems"),
    },
    "code": {"coding": ("creation", "code"), "verification": ("testing", "code")},
    "responsive": {
        "interface": ("improvement", "interfaces"),
        "verification": ("testing", "interfaces"),
    },
    "ux": {"interface": ("improvement", "interfaces"), "users": ("needs", "people")},
    "interview": {
        "users": ("needs", "people"),
        "requirements": ("structuring", "requirements"),
    },
    "data": {
        "investigation": ("investigation", "data"),
        "data": ("analysis", "data"),
        "verification": ("testing", "data"),
    },
}
ROWS = [
    (
        "backend",
        "Backend",
        {"code": 3, "systems": 3, "fixing": 2, "investigation": 2, "testing": 1},
    ),
    (
        "frontend",
        "Frontend",
        {"interfaces": 3, "improvement": 3, "creation": 2, "code": 1, "testing": 1},
    ),
    (
        "analytics",
        "Аналитика",
        {"data": 3, "analysis": 3, "patterns": 2, "investigation": 1, "structuring": 1},
    ),
    (
        "fullstack",
        "Fullstack-разработчик",
        {"code": 3, "systems": 2, "interfaces": 2, "creation": 2, "testing": 1},
    ),
    (
        "qa",
        "QA-инженер",
        {"testing": 3, "details": 2, "investigation": 2, "requirements": 1},
    ),
    (
        "business",
        "Бизнес-аналитик",
        {"requirements": 3, "needs": 3, "structuring": 2, "people": 1},
    ),
    (
        "system",
        "Системный аналитик",
        {"systems": 3, "requirements": 3, "structuring": 2, "systemic": 1},
    ),
    (
        "uxresearch",
        "UX-исследователь",
        {"people": 3, "needs": 3, "analysis": 2, "experiment": 1},
    ),
    (
        "design",
        "UI/UX-дизайнер",
        {"interfaces": 3, "improvement": 2, "people": 2, "creative": 1},
    ),
]


CAREER_DETAILS = {
    "backend": (
        "Создаёт правила и сервисы, которые работают за интерфейсом.",
        ["Функции", "API", "Хранение данных"],
        ["Напиши простую функцию.", "Получи данные через API."],
    ),
    "frontend": (
        "Создаёт интерфейсы и проверяет их работу на разных устройствах.",
        ["HTML и CSS", "Состояние интерфейса", "Доступность"],
        ["Сделай форму.", "Проверь её на двух ширинах экрана."],
    ),
    "analytics": (
        "Исследует данные и проверяет предположения о причинах изменений.",
        ["Таблицы", "Сравнение групп", "Гипотезы"],
        ["Сравни две группы данных.", "Проверь одну гипотезу."],
    ),
    "fullstack": (
        "Работает с интерфейсом и серверной частью продукта.",
        ["Интерфейсы", "API", "Данные"],
        ["Создай форму.", "Свяжи её с простым хранилищем."],
    ),
    "qa": (
        "Проверяет поведение продукта и помогает находить ошибки.",
        ["Сценарии проверки", "Граничные случаи", "Описание дефектов"],
        ["Проверь обычный сценарий формы.", "Попробуй пограничный случай."],
    ),
    "business": (
        "Уточняет потребности людей и описывает требования к продукту.",
        ["Интервью", "Требования", "Структурирование"],
        ["Расспроси участника.", "Опиши его потребность."],
    ),
    "system": (
        "Описывает связи и правила взаимодействия компонентов системы.",
        ["Модели систем", "Требования", "API"],
        ["Нарисуй связи сервиса.", "Опиши один обмен данными."],
    ),
    "uxresearch": (
        "Изучает, как люди решают задачи с помощью продукта.",
        ["Наблюдение", "Интервью", "Анализ"],
        ["Попроси человека выполнить задачу.", "Запиши места затруднений."],
    ),
    "design": (
        "Проектирует понятные и удобные интерфейсы.",
        ["Композиция", "Прототипы", "Обратная связь"],
        ["Предложи два варианта формы.", "Попроси человека их попробовать."],
    ),
}


def career_profile(session, user_id, old_profile):
    questionnaire = QuestionnaireService(session, user_id)
    state = questionnaire.state()
    completed = state["last_completed"]
    survey = signals(completed["answers"]) if completed else {}
    quests = {q.id: q for q in session.scalars(select(QuestDefinition))}
    latest = {}
    repeat = {}
    for event in session.scalars(
        select(QuestEvent)
        .where(
            QuestEvent.user_id == user_id,
            QuestEvent.event_type == "activity_reflection_v2",
        )
        .order_by(QuestEvent.id)
    ):
        try:
            quest_id = int(event.target_key.removeprefix("quest:"))
        except ValueError:
            continue
        for change in event.result["changes"]:
            latest[(quest_id, change["code"])] = {
                **change,
                "recorded_at": event.created_at.isoformat(),
            }
        if event.result.get("repeat") is not None:
            repeat[quest_id] = event.result["repeat"]
    evidence_ids = [
        item["evidence_event_id"]
        for item in latest.values()
        if item.get("evidence_event_id")
    ]
    action_events = (
        {
            event.id: event
            for event in session.scalars(
                select(QuestEvent).where(
                    QuestEvent.user_id == user_id, QuestEvent.id.in_(evidence_ids)
                )
            )
        }
        if evidence_ids
        else {}
    )
    per_quest = defaultdict(lambda: defaultdict(list))
    evidence = defaultdict(list)
    rated_quests = set()
    for (quest_id, code), item in latest.items():
        quest = quests.get(quest_id)
        if not quest or type(item["rating"]) is not int:
            continue
        rated_quests.add(quest_id)
        action = action_events.get(item.get("evidence_event_id"))
        action_time = action.created_at.isoformat() if action else None
        survey_order = None
        if completed and action_time:
            survey_order = (
                "before"
                if completed["completed_at"][:19] < action_time[:19]
                else "after"
            )
        for trait in set(
            TRAITS.get(quest.availability_config.get("kind"), {}).get(code, ())
        ):
            per_quest[trait][quest_id].append(item["rating"])
            evidence[trait].append(
                {
                    "quest_id": quest_id,
                    "title": quest.title,
                    "activity": LABELS.get(code, code),
                    "action_at": action_time,
                    "questionnaire_order": survey_order,
                    **item,
                }
            )
    game = {
        trait: sum(sum(values) / len(values) for values in groups.values())
        / len(groups)
        for trait, groups in per_quest.items()
    }
    traits = {}
    for trait in sorted(set(survey) | set(game)):
        q, g = survey.get(trait), game.get(trait)
        value = (
            g * 0.7 + q * 0.3
            if g is not None and q is not None
            else g
            if g is not None
            else q
        )
        traits[trait] = {
            "value": value,
            "questionnaire": q,
            "game": g,
            "divergent": q is not None and g is not None and abs(q - g) >= 1.5,
            "evidence": evidence[trait],
        }
    rows = []
    for code, title, weights in ROWS:
        available = [
            (traits[t]["value"], weight) for t, weight in weights.items() if t in traits
        ]
        total = sum(weight for _, weight in available)
        score = (
            sum(value * weight for value, weight in available) / total
            if len(available) >= 2 and total >= sum(weights.values()) / 2
            else None
        )
        rows.append(
            {
                "code": code,
                "title": title,
                "score": score,
                "traits": [t for t in weights if t in traits],
                "coverage": total / sum(weights.values()),
            }
        )
    directions = rows[:3]
    ranked = sorted(
        (row for row in directions if row["score"] is not None),
        key=lambda row: -row["score"],
    )
    leaders = (
        [
            row["code"]
            for row in ranked
            if ranked[0]["score"] - row["score"] <= 0.4 + 1e-9 and row["score"] >= 3.5
        ][:2]
        if ranked
        else []
    )
    cards = [
        dict(row) for row in rows if row["score"] is not None and row["score"] >= 3.5
    ]
    cards.sort(
        key=lambda row: (
            row["code"] not in ("backend", "frontend", "analytics"),
            -row["score"],
        )
    )
    for card in cards:
        tasks, skills, exercises = CAREER_DETAILS[card["code"]]
        card.update(
            {
                "title": {
                    "backend": "Backend-разработчик",
                    "frontend": "Frontend-разработчик",
                    "analytics": "Аналитик данных",
                }.get(card["code"], card["title"]),
                "tasks": tasks,
                "skills": skills,
                "exercises": exercises,
                "represented": card["code"] in ("backend", "frontend", "analytics"),
                "evidence": [
                    item for trait in card["traits"] for item in evidence[trait]
                ],
            }
        )

    next_step = None
    if leaders:
        service = QuestService(session, user_id)
        players = {
            p.quest_id: p
            for p in session.scalars(
                select(PlayerQuest).where(PlayerQuest.user_id == user_id)
            )
        }
        for direction in leaders:
            candidates = sorted(
                (
                    q
                    for q in quests.values()
                    if q.is_published
                    and q.location_slug == direction
                    and q.availability_config.get("engine") == 2
                ),
                key=lambda q: q.id,
            )
            for quest in candidates:
                player = players.get(quest.id)
                if player and player.status == "completed":
                    continue
                if not service.available(quest):
                    continue
                if not (player and player.status == "active") and any(
                    p.status == "active"
                    and other.id != quest.id
                    and other.giver_npc_id == quest.giver_npc_id
                    and other.category == "professional"
                    for other in quests.values()
                    if (p := players.get(other.id))
                ):
                    continue
                next_step = {
                    "quest_id": quest.id,
                    "title": quest.title,
                    "explanation": f"Попробуй ещё одно дело направления {direction}.",
                }
                break
            if next_step:
                break
    elif not traits:
        next_step = old_profile["next_step"]
    return {
        "version": 2,
        "status": "empty"
        if not traits
        else "established"
        if len(rated_quests) >= 2 and leaders
        else "preliminary",
        "rated_quests": len(rated_quests),
        "questionnaire": state,
        "traits": traits,
        "directions": directions,
        "leaders": leaders,
        "careers": cards[:3],
        "history": old_profile["history"],
        "reflections": [
            {"quest_id": qid, "code": code, **item}
            for (qid, code), item in latest.items()
        ],
        "repeat": repeat,
        "next_step": next_step
        or {
            "quest_id": None,
            "title": "Небольшая самостоятельная проба",
            "explanation": (
                "Выбери интересную задачу, измени один вариант и сравни результат."
            ),
        },
    }
