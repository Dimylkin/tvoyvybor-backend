"""Versioned, explainable career indices from explicit player ratings."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from app.activity_profile import LABELS
from app.career_profile_rules import practice, rounded, survey_contexts
from app.quest_models import PlayerQuest, QuestDefinition, QuestEvent
from app.quest_service import QuestService
from app.questionnaire_catalog_v2 import QUESTIONS_V2
from app.questionnaire_catalog_v3 import QUESTIONS_V3
from app.questionnaire_catalog_v4 import QUESTIONS_V4
from app.questionnaire_interpretation_v2 import interpret
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
    survey = (
        signals(completed["answers"])
        if completed and completed["catalog_version"] == 1
        else {}
    )
    survey_result = (
        interpret(
            completed["answers"],
            {2: QUESTIONS_V2, 3: QUESTIONS_V3, 4: QUESTIONS_V4}[
                completed["catalog_version"]
            ],
        )
        if completed and completed["catalog_version"] in (2, 3, 4)
        else None
    )
    contexts = survey_contexts(
        survey_result, completed["interpretation_version"] if completed else 2
    )
    if completed and completed["catalog_version"] == 1:
        # The old catalogue has absolute ratings but no situational context.
        # Retain it as a limited historical source without treating it as practice.
        legacy = {
            "B": ("code", "systems"),
            "F": ("interfaces",),
            "D": ("data", "analysis"),
            "R": ("requirements", "people"),
        }
        contexts = {
            key: {
                "label": "positive"
                if sum(survey.get(t, 0) >= 4 for t in traits) >= 2
                else "insufficient",
                "positive_questions": [],
                "negative_questions": [],
                "neither_questions": [],
                "absolute_questions": [],
                "historical": True,
            }
            for key, traits in legacy.items()
        }
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
        if event.result.get("clear_repeat"):
            repeat.pop(quest_id, None)
        elif event.result.get("repeat") is not None:
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
    observations = []
    for (quest_id, code), item in latest.items():
        quest = quests.get(quest_id)
        if not quest or type(item["rating"]) is not int:
            continue
        action = action_events.get(item.get("evidence_event_id"))
        if action is None:
            continue
        rated_quests.add(quest_id)
        action_time = action.created_at.isoformat()
        observations.append(
            {
                "quest_id": quest_id,
                "kind": quest.availability_config.get("kind"),
                "title": quest.title,
                "code": code,
                "activity": LABELS.get(code, code),
                **item,
            }
        )
        survey_order = None
        if completed and action_time:
            survey_time = datetime.fromisoformat(completed["completed_at"])
            event_time = action.created_at
            if (
                survey_time.utcoffset() is not None
                and event_time.utcoffset() is not None
            ):
                survey_order = "before" if survey_time < event_time else "after"
        observations[-1]["questionnaire_order"] = survey_order
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
        value = g if g is not None else q
        traits[trait] = {
            "value": value,
            "questionnaire": q,
            "game": g,
            "divergent": q is not None and g is not None and abs(q - g) >= 1.5,
            "evidence": evidence[trait],
        }
    players = {
        p.quest_id: p
        for p in session.scalars(
            select(PlayerQuest).where(PlayerQuest.user_id == user_id)
        )
    }
    attempted_kinds = {
        quests[qid].availability_config.get("kind")
        for qid, player in players.items()
        if qid in quests and player.status in ("active", "completed")
    }
    directions, leaders, conclusion = practice(observations, attempted_kinds, contexts)
    for direction in directions:
        direction["repeat_support"] = any(
            repeat.get(o["quest_id"]) is True and o["rating"] >= 4
            for trial in direction["trials"]
            for o in trial["observations"]
        )
        direction["mixed_repeat"] = any(
            (repeat.get(o["quest_id"]) is False and o["rating"] >= 4)
            or (repeat.get(o["quest_id"]) is True and o["rating"] <= 2)
            for trial in direction["trials"]
            for o in trial["observations"]
        )
        direction["divergent"] = bool(
            leaders
            and direction["code"] not in leaders
            and any(
                v["label"] == "positive" for v in direction["questionnaire"].values()
            )
        )
    # Cards require evidence from the relevant direction, never a shared trait score.
    cards = []
    card_specs = [
        ("backend", "backend", "Backend-разработчик", "B", ("diagnosis", "code")),
        ("frontend", "frontend", "Frontend-разработчик", "F", ("responsive", "ux")),
        ("analytics", "analytics", "Аналитик данных", "D", ("data",)),
        ("business", "analytics", "Бизнес-аналитик", "R", ("interview",)),
    ]
    primary_actions = {
        "diagnosis": {"investigation", "coding"},
        "code": {"coding"},
        "responsive": {"interface"},
        "ux": {"interface"},
        "data": {"data", "investigation"},
        "interview": {"requirements", "users"},
    }
    for card_code, direction_code, title, context, kinds in card_specs:
        direction = next(d for d in directions if d["code"] == direction_code)
        branch = [
            o
            for o in observations
            if o["kind"] in kinds and o["code"] in primary_actions[o["kind"]]
        ]
        relevant = [o for o in branch if o["rating"] >= 4]
        survey_positive = contexts.get(context, {}).get("label") == "positive"
        branch_score = (
            rounded(sum(o["rating"] for o in branch) / len(branch)) if branch else None
        )
        card_score = (
            branch_score
            if card_code in ("analytics", "business")
            else direction["score"]
        )
        qualified = (
            direction["sufficient"]
            and card_score is not None
            and card_score >= 3.5
            and bool(relevant)
        )
        first_impressions = (
            card_code in ("analytics", "business") and len(relevant) >= 2
        )
        if not (qualified or first_impressions or survey_positive):
            continue
        tasks, skills, exercises = CAREER_DETAILS[card_code]
        cards.append(
            {
                "code": card_code,
                "title": title,
                "score": card_score
                if relevant and (qualified or first_impressions)
                else None,
                "traits": [],
                "coverage": direction["coverage"],
                "tasks": tasks,
                "skills": skills,
                "exercises": exercises,
                "represented": True,
                "evidence": relevant,
                "basis": "practice"
                if qualified or first_impressions
                else "questionnaire",
            }
        )

    positive_sources = defaultdict(set)
    if survey_result:
        for trait, data in survey_result["comparative"].items():
            positive_sources[trait].update(
                f"q:{item['question_id']}"
                for item in data["evidence"]
                if item["value"] > 0
            )
        for trait, questions in survey_result["choices"].items():
            positive_sources[trait].update(f"q:{qid}" for qid in questions)
        for qid, data in survey_result["absolute"].items():
            if data["value"] >= 4:
                for trait in data["signals"]:
                    positive_sources[trait].add(f"q:{qid}")
    for observation in observations:
        if observation["rating"] < 4:
            continue
        source = f"quest:{observation['quest_id']}"
        for trait in TRAITS.get(observation["kind"], {}).get(observation["code"], ()):
            positive_sources[trait].add(source)
        if observation["kind"] in ("diagnosis", "code") and observation["code"] in (
            "coding",
            "investigation",
        ):
            positive_sources["B"].add(source)
        if (
            observation["kind"] in ("responsive", "ux")
            and observation["code"] == "interface"
        ):
            positive_sources["F"].add(source)
        if observation["code"] == "verification":
            positive_sources["software"].add(source)
        if observation["kind"] == "ux" and observation["code"] == "users":
            positive_sources["user_research"].add(source)
    adjacent = [
        (
            "fullstack",
            "Fullstack-разработчик",
            ("B",),
            ("F",),
        ),
        ("qa", "QA-инженер", ("testing",), ("testing",)),
        ("system", "Системный аналитик", ("systems",), ("R", "requirements")),
        ("uxresearch", "UX-исследователь", ("user_research",), ("needs", "people")),
        (
            "design",
            "UI/UX-дизайнер",
            ("F", "interfaces"),
            ("needs", "people", "user_research"),
        ),
    ]
    for code, title, left, right in adjacent:
        left_sources = set().union(*(positive_sources[t] for t in left))
        right_sources = set().union(*(positive_sources[t] for t in right))
        if code == "fullstack":
            right_sources &= (
                positive_sources["improvement"] | positive_sources["creation"]
            )
        pairs = [(a, b) for a in left_sources for b in right_sources if a != b]
        if code == "qa":
            pairs = [
                (a, b)
                for a, b in pairs
                if a in positive_sources["software"]
                or b in positive_sources["software"]
            ]
        if not pairs:
            continue
        tasks, skills, exercises = CAREER_DETAILS[code]
        ids = set(sorted(pairs)[0])
        related = [
            o
            for o in observations
            if f"quest:{o['quest_id']}" in ids and o["rating"] >= 4
        ]
        question_contexts = {
            q["id"]: q.get("context", q["text"])
            for q in [*QUESTIONS_V2, *QUESTIONS_V3, *QUESTIONS_V4]
        }
        explanations = [
            question_contexts[source[2:]]
            for source in sorted(ids)
            if source.startswith("q:") and source[2:] in question_contexts
        ]
        cards.append(
            {
                "code": code,
                "title": title,
                "score": None,
                "traits": [],
                "coverage": 0,
                "tasks": tasks,
                "skills": skills,
                "exercises": exercises,
                "represented": False,
                "basis": "combined",
                "evidence": related,
                "source_ids": sorted(ids),
                "question_contexts": explanations,
            }
        )

    next_step = None
    suggested = leaders or [
        d["code"] for d in directions if d["score"] is not None and d["score"] >= 3.5
    ]
    if not suggested:
        suggested = [
            d["code"]
            for d in directions
            if any(v["label"] == "positive" for v in d["questionnaire"].values())
        ]
    if conclusion == "local":
        suggested += [
            d["code"]
            for d in directions
            if not d["sufficient"] and d["code"] not in suggested
        ]
    if suggested:
        service = QuestService(session, user_id)
        players = {
            p.quest_id: p
            for p in session.scalars(
                select(PlayerQuest).where(PlayerQuest.user_id == user_id)
            )
        }
        for direction in suggested:
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
    hard = any(
        o["rating"] <= 2 and o.get("reason") in ("difficulty", "knowledge", "interface")
        for o in observations
    )
    mixed = any(d["mixed_repeat"] for d in directions)
    if next_step and hard:
        next_step["explanation"] += (
            " Начни с более простого примера: сложность могла повлиять на впечатление."
        )
    if next_step and mixed:
        next_step["explanation"] += (
            " Сравни впечатление от задания с желанием его повторить."
        )
    if next_step is None and suggested:
        exercises = {
            "backend": "Напиши простую функцию или попробуй API.",
            "frontend": "Сделай адаптивную форму и проверь её на двух экранах.",
            "analytics": " ".join(
                ["Сравни группы данных", "или проведи интервью и опиши требования."]
            ),
        }
        next_step = {
            "quest_id": None,
            "title": "Небольшая самостоятельная проба",
            "explanation": exercises[suggested[0]],
        }
        if hard:
            next_step["explanation"] += " Начни с простого примера."
        if mixed:
            next_step["explanation"] += " Сравни впечатления и желание повторить."
    return {
        "version": 3,
        "status": "empty"
        if conclusion == "empty"
        else "established"
        if conclusion in ("leaders", "weak", "no_clear_direction")
        else "preliminary",
        "conclusion": conclusion,
        "survey_contexts": contexts,
        "survey_available": completed is not None,
        "survey_results": survey_result,
        "rated_quests": len(rated_quests),
        "questionnaire": state,
        "traits": traits,
        "directions": directions,
        "leaders": leaders,
        "careers": cards,
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
