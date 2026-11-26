"""Explicit activity reflections and deterministic, explainable suggestions."""

from collections import defaultdict

from sqlalchemy import select

from app.quest_catalog import QUESTS
from app.quest_errors import QuestError
from app.quest_models import PlayerQuest, QuestDefinition, QuestEvent
from app.quest_service import QuestService

LABELS = {
    "investigation": "Искать причины",
    "coding": "Работать над кодом",
    "verification": "Проверять результат",
    "interface": "Менять интерфейс",
    "users": "Разбираться в действиях пользователя",
    "requirements": "Формулировать требования",
    "data": "Исследовать данные",
}
KINDS = {
    "diagnosis": ("investigation", "coding", "verification"),
    "code": ("coding", "verification"),
    "responsive": ("interface", "verification"),
    "ux": ("interface", "users"),
    "interview": ("users", "requirements"),
    "data": ("investigation", "data", "verification"),
}
CAREERS = {
    "investigation": [
        ("QA", "В QA ищут причины сбоев."),
        ("Аналитика данных", "Аналитики объясняют аномалии в данных."),
    ],
    "coding": [("Backend", "В backend пишут логику сервисов.")],
    "verification": [("QA", "В QA проверяют поведение продукта.")],
    "interface": [("Frontend", "Во frontend создают и меняют интерфейсы.")],
    "users": [("UX Research", "Исследователи изучают действия пользователей.")],
    "requirements": [("Бизнес-анализ", "Аналитики уточняют потребности и требования.")],
    "data": [("Аналитика данных", "Аналитики исследуют срезы данных.")],
}
ORDER = {item[0]: index for index, item in enumerate(QUESTS)}
EXERCISES = {
    "investigation": (
        "Выясни, почему выросла выручка при прежнем числе заказов: "
        "запиши две версии и проверь одну."
    ),
    "coding": "Напиши функцию расчёта скидки и проверь её на нескольких заказах.",
    "verification": "Проверь обычный и граничный случаи простой функции или формы.",
    "interface": "Измени элемент страницы и посмотри на него на узком экране.",
    "users": "Попроси человека выполнить задачу и отметь, где он остановился.",
    "requirements": "Опиши пользователя, его проблему и результат, который ему нужен.",
    "data": "Сравни две группы в небольшой таблице и запиши замеченное различие.",
}
INTERESTS = {
    "investigation": "тебе интересно искать причины и проверять версии",
    "coding": "тебе интересно писать и изучать код",
    "verification": "тебе интересно проверять результат и находить ошибки",
    "interface": "тебе интересно менять и улучшать интерфейсы",
    "users": "тебе интересно разбираться в действиях и трудностях пользователей",
    "requirements": "тебе интересно выяснять потребности и формулировать требования",
    "data": "тебе интересно изучать данные и сравнивать показатели",
}


def evidence_description(quest, code, response, event):
    """Describe the accepted action without exposing input or inventing success."""
    kind = quest.availability_config.get("kind")
    action = event.payload.get("action") if event else None
    descriptions = {
        ("diagnosis", "log"): "просмотрел запись журнала",
        ("diagnosis", "hypothesis"): "проверил версию о причине сбоя",
        ("diagnosis", "repair"): "отправил попытку исправления сбоя",
        ("diagnosis", "verify"): "проверил работу API",
        ("code", "run"): "запустил тесты функции с написанным кодом",
        ("responsive", "property"): "изменил свойство макета",
        ("responsive", "device"): "проверил макет на устройстве",
        ("responsive", "verify"): "отправил макет на проверку",
        ("ux", "property"): "изменил форму регистрации",
        ("ux", "simulate"): "провёл сценарий регистрации пользователя",
        ("interview", "question"): "задал вопрос о пользователе или его работе",
        ("interview", "compose"): "отправил предложение заказчику",
        ("interview", "proposal"): "отправил предложение заказчику",
        ("interview", "criteria"): "отправил критерии приёмки",
        ("data", "slice"): "открыл срез данных",
        ("data", "operation"): "просмотрел операцию",
        ("data", "conclusion"): "проверил версию о причине изменения показателей",
        ("data", "compare"): "сравнил исходный и очищенный ряды данных",
    }
    action_text = descriptions.get((kind, action))
    choice = "захотел повторить" if response == "repeat" else "отметил, что не твоё"
    if action_text:
        return f"В «{quest.title}» ты {action_text} и {choice}: {LABELS[code].lower()}."
    return f"В «{quest.title}» ты {choice}: {LABELS[code].lower()}."


EXPLORE_CODES = {
    "diagnosis": "verification",
    "code": "verification",
    "responsive": "verification",
    "ux": "users",
    "interview": "users",
    "data": "data",
}
CONTEXTS = {
    "diagnosis": "выяснить причину сбоя сервиса",
    "code": "написать и проверить функцию",
    "responsive": "адаптировать макет для разных устройств",
    "ux": "улучшить форму регистрации",
    "interview": "выяснить потребность заказчика",
    "data": "объяснить аномалию в данных о продажах",
}


def observed(kind, event):
    """Classify only server-accepted actions, never drafts or success alone."""
    if event.event_type != "minigame_action":
        return ()
    action = event.payload.get("action")
    payload = event.payload.get("payload", {})
    value = payload.get("value")
    if kind == "diagnosis":
        return {
            "log": ("investigation",),
            "hypothesis": ("investigation",),
            "repair": ("coding",),
            "verify": ("verification",),
        }.get(action, ())
    if kind == "code":
        return (
            ("coding", "verification")
            if action == "run" and isinstance(value, str) and value.strip()
            else ()
        )
    if kind == "responsive":
        return {
            "property": ("interface",),
            "device": ("verification",),
            "verify": ("verification",),
        }.get(action, ())
    if kind == "ux":
        return {"property": ("interface",), "simulate": ("users",)}.get(action, ())
    if kind == "interview":
        if action == "question" and value in ("who", "after", "pain"):
            return ("users",)
        return (
            ("requirements",) if action in ("compose", "proposal", "criteria") else ()
        )
    if kind == "data":
        return {
            "operation": ("investigation",),
            "conclusion": ("investigation",),
            "slice": ("data",),
            "compare": ("verification",),
        }.get(action, ())
    return ()


def current_actions(events, kind):
    found = {}
    for event in events:
        if event.event_type == "minigame_reset":
            found.clear()
        for code in observed(kind, event):
            found[code] = event.id
    return found


def save_reflection(service, quest_id, request_id, response, activity_code, barrier):
    service.repo.lock_user(service.user_id)
    quest = service.definition(quest_id)
    target = f"quest:{quest_id}"
    payload = {"response": response, "activity_code": activity_code, "barrier": barrier}
    previous = service.repo.event(service.user_id, request_id)
    if previous:
        if (previous.event_type, previous.target_key, previous.payload) != (
            "activity_reflection",
            target,
            payload,
        ):
            raise QuestError(409, "Request ID has different content")
        return previous.result
    player = service.repo.player(service.user_id, quest_id)
    kind = quest.availability_config.get("kind")
    if (
        quest.availability_config.get("engine") != 2
        or not player
        or player.status not in ("active", "completed")
    ):
        raise QuestError(409, "Reflection is not available")
    events = service.session.scalars(
        select(QuestEvent)
        .where(QuestEvent.user_id == service.user_id, QuestEvent.target_key == target)
        .order_by(QuestEvent.id)
    ).all()
    actions = current_actions(events, kind)
    if (
        not actions
        or (response == "repeat" and not activity_code)
        or (activity_code and activity_code not in actions)
    ):
        raise QuestError(409, "Activity is not available")
    result = {
        **payload,
        "evidence_event_id": actions.get(activity_code)
        if activity_code
        else next(iter(actions.values())),
    }
    service.session.add(
        QuestEvent(
            user_id=service.user_id,
            request_id=request_id,
            event_type="activity_reflection",
            target_key=target,
            payload=payload,
            result=result,
        )
    )
    service.session.commit()
    return result


def activity_profile(session, user_id):
    service = QuestService(session, user_id)
    all_definitions = list(
        session.scalars(
            select(QuestDefinition).where(
                QuestDefinition.availability_config.is_not(None)
            )
        ).all()
    )
    definitions = [
        q
        for q in all_definitions
        if q.availability_config.get("engine") == 2
        and q.availability_config.get("kind") in KINDS
    ]
    definitions.sort(key=lambda q: (ORDER.get(q.slug, len(ORDER)), q.id))
    players = {
        p.quest_id: p
        for p in session.scalars(
            select(PlayerQuest).where(PlayerQuest.user_id == user_id)
        ).all()
    }
    events_by_target = defaultdict(list)
    for event in session.scalars(
        select(QuestEvent).where(QuestEvent.user_id == user_id).order_by(QuestEvent.id)
    ):
        events_by_target[event.target_key].append(event)
    definitions.extend(
        q
        for q in all_definitions
        if q not in definitions
        and any(
            e.event_type == "activity_reflection"
            for e in events_by_target[f"quest:{q.id}"]
        )
    )
    history = []
    positive = defaultdict(list)
    negative = defaultdict(list)
    for quest in definitions:
        player = players.get(quest.id)
        events = events_by_target[f"quest:{quest.id}"]
        reflections = [e for e in events if e.event_type == "activity_reflection"]
        if (not player or player.status == "offered") and not reflections:
            continue
        kind = quest.availability_config.get("kind")
        actions = current_actions(events, kind)
        reflection = reflections[-1].result if reflections else None
        editable = (
            quest.is_published and player and player.status in ("active", "completed")
        )
        history.append(
            {
                "quest_id": quest.id,
                "title": quest.title,
                "status": player.status if player else "abandoned",
                "published": quest.is_published,
                "activities": [
                    {"code": code, "label": LABELS[code]}
                    for code in KINDS.get(kind, ())
                    if code in actions
                ]
                if editable
                else [],
                "reflection": reflection,
                "legacy_reaction": next(
                    (
                        e.payload.get("payload", {}).get("value")
                        for e in reversed(events)
                        if e.event_type == "minigame_action"
                        and e.payload.get("action") == "react"
                    ),
                    None,
                ),
            }
        )
        if reflection and reflection.get("activity_code") in LABELS:
            code = reflection["activity_code"]
            evidence_id = reflection.get("evidence_event_id") or reflections[-1].id
            evidence_event = next(
                (
                    e
                    for e in events
                    if e.id == evidence_id and code in observed(kind, e)
                ),
                None,
            )
            description = evidence_description(
                quest, code, reflection["response"], evidence_event
            )
            start = max(
                (
                    e.id
                    for e in events
                    if e.event_type == "minigame_reset" and e.id < evidence_id
                ),
                default=0,
            )
            end = min(
                (
                    e.id
                    for e in events
                    if e.event_type == "minigame_reset" and e.id > evidence_id
                ),
                default=float("inf"),
            )
            if EXPLORE_CODES.get(kind) == code and any(
                e.event_type == "minigame_action"
                and e.payload.get("action") == "explore"
                and start < e.id < end
                for e in events
            ):
                description += " Ты также попробовал дополнительное исследование."
            item = {
                "quest_id": quest.id,
                "title": quest.title,
                "description": description,
            }
            if reflection["response"] == "repeat":
                positive[code].append(item)
            elif reflection["response"] == "not_mine":
                negative[code].append(item)
    insights = []
    for code in LABELS:
        if positive[code]:
            mixed = bool(negative[code])
            insights.append(
                {
                    "activity_code": code,
                    "label": LABELS[code],
                    "status": "mixed"
                    if mixed
                    else "repeated"
                    if len(positive[code]) >= 2
                    else "hypothesis",
                    "evidence": (
                        positive[code][:1]
                        + negative[code][:1]
                        + positive[code][1:]
                        + negative[code][1:]
                        if mixed
                        else positive[code]
                    ),
                }
            )
    priorities = {"repeated": 0, "hypothesis": 1, "mixed": 2}
    insights.sort(
        key=lambda insight: (
            priorities[insight["status"]],
            -len(positive[insight["activity_code"]]),
            list(LABELS).index(insight["activity_code"]),
        )
    )
    main_observation = None
    if insights:
        main = insights[0]
        code = main["activity_code"]
        interest = INTERESTS[code]
        headline = (
            f"Похоже, {interest}."
            if main["status"] == "hypothesis"
            else f"В разных ситуациях у тебя разные впечатления: {interest}."
            if main["status"] == "mixed"
            else f"Похоже, {interest} — этот интерес повторился."
        )
        main_observation = {
            "activity_code": code,
            "status": main["status"],
            "headline": headline,
            "interest": interest[0].upper() + interest[1:] + ".",
            "direction": CAREERS[code][0][0],
            "example": EXERCISES[code],
        }
    careers = []
    for insight in insights[:1]:
        if insight["status"] == "repeated":
            for name, explanation in CAREERS[insight["activity_code"]]:
                if name not in [c["name"] for c in careers] and len(careers) < 3:
                    careers.append({"name": name, "explanation": explanation})
    next_step = None
    if insights:
        insight = insights[0]
        code = insight["activity_code"]
        source = next(
            q for q in definitions if q.id == insight["evidence"][0]["quest_id"]
        )
        candidates = []
        for q in definitions:
            player = players.get(q.id)
            if (
                not q.is_published
                or q.id == source.id
                or code not in KINDS.get(q.availability_config.get("kind"), ())
                or (player and player.status == "completed")
                or not service.available(q)
            ):
                continue
            if not (player and player.status == "active") and any(
                p.status == "active"
                and p.quest_id != q.id
                and other.giver_npc_id == q.giver_npc_id
                and other.category == "professional"
                for other in all_definitions
                if (p := players.get(other.id))
            ):
                continue
            candidates.append(q)
        candidates.sort(
            key=lambda q: (
                q.location_slug == source.location_slug,
                not (players.get(q.id) and players[q.id].status == "active"),
                ORDER.get(q.slug, len(ORDER)),
                q.id,
            )
        )
        if candidates:
            q = candidates[0]
            next_step = {
                "quest_id": q.id,
                "title": q.title,
                "explanation": (
                    f"В «{q.title}» тоже можно попробовать: "
                    f"{LABELS[code].lower()}: "
                    f"{CONTEXTS[q.availability_config['kind']]}."
                ),
            }
        else:
            next_step = {
                "quest_id": None,
                "title": "Небольшая самостоятельная проба",
                "explanation": EXERCISES[code],
            }
    else:
        explored = {
            q.location_slug
            for q in definitions
            if q.id in players and players[q.id].accepted_at
        }
        for q in definitions:
            p = players.get(q.id)
            if (
                q.is_published
                and q.location_slug not in explored
                and not (p and p.status == "completed")
                and service.available(q)
                and not any(
                    player.status == "active"
                    and other.giver_npc_id == q.giver_npc_id
                    and other.category == "professional"
                    for other in all_definitions
                    if (player := players.get(other.id))
                )
            ):
                next_step = {
                    "quest_id": q.id,
                    "title": q.title,
                    "explanation": "Попробуй новую ситуацию в незнакомом корпусе.",
                }
                break
    groups = [
        {
            "code": i["activity_code"],
            "name": i["label"],
            "description": "Разные впечатления в разных ситуациях."
            if i["status"] == "mixed"
            else "Повторившийся интерес."
            if i["status"] == "repeated"
            else "Пока это предположение после одной пробы.",
            "score": len(positive[i["activity_code"]]),
            "evidence_count": len(i["evidence"]),
            "evidence": [e["description"] for e in i["evidence"]],
        }
        for i in insights
    ]
    return {
        "event_count": len(history),
        "performance_score": sum(p.status == "completed" for p in players.values()),
        "preliminary": not any(i["status"] == "repeated" for i in insights),
        "groups": groups,
        "careers": careers,
        "learning": [],
        "additional": None,
        "observations": len(history),
        "history": history,
        "insights": insights,
        "next_step": next_step,
        "main_observation": main_observation,
    }


def save_reflection_v2(
    service, quest_id, request_id, changes, repeat, clear_repeat=False
):
    """Apply only explicitly submitted values backed by current-run actions."""
    service.repo.lock_user(service.user_id)
    quest = service.definition(quest_id)
    target = f"quest:{quest_id}"
    payload = {"changes": changes, "repeat": repeat}
    if clear_repeat:
        payload["clear_repeat"] = True
    previous = service.repo.event(service.user_id, request_id)
    if previous:
        if (previous.event_type, previous.target_key, previous.payload) != (
            "activity_reflection_v2",
            target,
            payload,
        ):
            raise QuestError(409, "Request ID has different content")
        return previous.result
    player = service.repo.player(service.user_id, quest_id)
    kind = quest.availability_config.get("kind")
    if (
        quest.availability_config.get("engine") != 2
        or not player
        or player.status not in ("active", "completed")
    ):
        raise QuestError(409, "Reflection is not available")
    events = list(
        service.session.scalars(
            select(QuestEvent)
            .where(
                QuestEvent.user_id == service.user_id, QuestEvent.target_key == target
            )
            .order_by(QuestEvent.id)
        )
    )
    actions = current_actions(events, kind)
    if not actions or any(change["code"] not in actions for change in changes):
        raise QuestError(409, "Activity is not available")
    result = {
        "version": 2,
        "changes": [
            {**change, "evidence_event_id": actions[change["code"]]}
            for change in changes
        ],
        "repeat": repeat,
    }
    if clear_repeat:
        result["clear_repeat"] = True
    service.session.add(
        QuestEvent(
            user_id=service.user_id,
            request_id=request_id,
            event_type="activity_reflection_v2",
            target_key=target,
            payload=payload,
            result=result,
        )
    )
    service.session.commit()
    return result
