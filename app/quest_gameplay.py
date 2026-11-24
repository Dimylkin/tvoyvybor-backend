"""Server-authoritative mini-game transitions, telemetry and rewards."""

import ast
import json
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import (
    Achievement,
    CareerDirection,
    InterestEvent,
    InterestProfile,
    Recommendation,
    UserAchievement,
)
from app.quest_catalog import REWARDS
from app.quest_dtos import AwardResult, GameActionResult
from app.quest_errors import QuestError
from app.quest_models import PlayerQuestObjective, QuestEvent, TrackedQuest, now
from app.quest_python import check_code

REACTIONS = {"more", "interesting", "not-mine", "enough"}
RESPONSIVE = {"width": "100%", "layout": "column", "position": "static"}
UX = {
    "button": "Зарегистрироваться",
    "error": "Проверьте адрес: нужен символ @",
    "hint": "Не менее 8 символов",
    "reveal": "show",
    "order": "email-first",
}
ASSISTANT_QUESTIONS = {
    "none",
    "average",
    "empty",
    "zero",
    "logic",
    "why-zero",
    "sum",
    "tests",
    "loop",
    "function",
    "python",
    "javascript",
    "example",
}
QUESTIONS = {
    "who",
    "why",
    "what",
    "format",
    "pain",
    "schedule",
    "color",
    "after",
    "frequency",
    "recipient",
    "place",
    "bigger",
    "font",
}


def responsive_checks(properties, viewport):
    """Geometry of the restricted editor, mirrored by its visual preview."""
    p = {
        "width": "600px",
        "layout": "row",
        "position": "absolute",
        "gap": "16",
        "fontSize": "16",
        **properties,
    }
    available = viewport - 32
    width = p["width"]
    card = (
        available
        if width == "auto"
        else float(width[:-2])
        if width.endswith("px")
        else available * float(width.rstrip("%")) / 100
    )
    gap = float(p["gap"])
    return {
        "overflow": 128 <= card <= available,
        "cards": card >= (240 + gap if p["layout"] == "row" else 120),
        "button": p["position"] != "absolute",
        "readability": 14 <= float(p["fontSize"]) <= 24,
    }


def ux_checks(properties):
    p = properties
    button = p.get("button", "").lower()
    error = p.get("error", "").lower()
    hint = p.get("hint", "").lower()
    return {
        "order": p.get("order") == "email-first",
        "button": any(word in button for word in ("регистр", "аккаунт", "создать")),
        "error": (
            any(word in error for word in ("адрес", "email", "почт"))
            and any(word in error for word in ("@", "пример", "исправ", "проверь"))
        ),
        "hint": "8" in hint
        and any(word in hint for word in ("символ", "знак", "длин")),
        "reveal": p.get("reveal") == "show",
    }


def additional_check(kind, state, payload):
    key, value = payload.get("key"), payload.get("value")
    if kind == "diagnosis":
        require(key == "endpoint" and value in ("/api/profile", "/api/users"))
        return f"GET {value} → 200. Соседний endpoint отвечает после исправления."
    if kind == "responsive":
        require(key == "viewport" and value == "280")
        passed = all(responsive_checks(state.get("properties", {}), 280).values())
        return "Экран 280px: " + (
            "переполнений нет." if passed else "нужна дополнительная адаптация."
        )
    if kind == "ux":
        require(key == "form" and value == "typo-corrected")
        require(all(ux_checks(state.get("properties", {})).values()))
        return "Опечатка исправлена в прототипе; регистрация проверена повторно."
    if kind == "interview":
        require(key == "question" and value in ("color", "empty-week"))
        return "Заказчик: если заказов нет, сообщить об этом вместо пустого CSV."
    if kind == "data":
        require(key == "slice" and value in ("regions", "products", "period"))
        return {
            "regions": "Без тестов: Урал 94, Центр 100, остальные 36 тыс. ₽.",
            "products": "Без тестов: кружки 42, блокноты 38, худи 150 тыс. ₽.",
            "period": "Очищенная выручка: 110, 105, 115, 112, 118 тыс. ₽.",
        }[value]
    require(kind == "code" and key == "input" and isinstance(value, str))
    try:
        values = json.loads(value)
    except (ValueError, TypeError):
        require(False, "Введите JSON-массив чисел и null")
    require(
        isinstance(values, list)
        and len(values) <= 20
        and all(v is None or type(v) in (int, float) for v in values),
        "Не более 20 чисел или null",
    )
    from app.quest_python import Interpreter

    try:
        result = Interpreter().run(state["code"], values)
    except (ValueError, TypeError, ZeroDivisionError):
        return "Дополнительный вход вызвал ошибку функции. Основной результат сохранён."
    return f"Дополнительный вход {values} → {result}."


def initial_state():
    return {
        "stage": "intro",
        "intro_line": 0,
        "debrief_line": 0,
        "failed_checks": 0,
        "seen": [],
        "choices": [],
        "attempts": 0,
        "hints": 0,
        "example_used": False,
        "extra_exploration": 0,
        "active_seconds": 0,
        "voluntary": True,
        "success": False,
        "feedback": "Поговорите с наставником перед работой на станции.",
    }


def state_for(service, quest):
    event = service.session.scalar(
        select(QuestEvent)
        .where(
            QuestEvent.user_id == service.user_id,
            QuestEvent.target_key == f"quest:{quest.id}",
            QuestEvent.event_type.in_(("minigame_action", "minigame_reset")),
        )
        .order_by(QuestEvent.id.desc())
    )
    return deepcopy(event.result["state"]) if event else initial_state()


def require(condition, message="Сначала завершите предыдущий этап"):
    if not condition:
        raise QuestError(409, message)


def transition(kind, state, action, payload):
    s = deepcopy(state)
    seen = set(s["seen"])
    value = payload.get("value")
    rewards = []
    if action == "engage":
        return s, []
    if action == "intro-line":
        require(s["stage"] == "intro" and not s.get("intro_deferred"))
        require(isinstance(value, str) and value.isdigit())
        line = int(value)
        require(line == s.get("intro_line", 0) + 1 and line <= 6)
        s["intro_line"] = line
    elif action == "intro-defer":
        require(s["stage"] == "intro" and s.get("intro_line", 0) == 4)
        s["intro_deferred"] = True
    elif action == "intro-resume":
        require(s["stage"] == "intro" and s.get("intro_deferred"))
        s["intro_deferred"] = False
        s["intro_line"] = 5
    elif action == "intro-complete":
        require(s["stage"] == "intro" and s.get("intro_line", 0) >= 6)
        s["stage"] = "interaction"
        s["feedback"] = "Подойдите к рабочей станции."
    elif action == "debrief-answer":
        require(
            kind == "code"
            and s["stage"] == "return"
            and s.get("debrief_line", 0) == 0
            and value in ("yes", "partly", "help", "silence")
        )
        s["code_answer"] = value
        s["debrief_line"] = 1
    elif action == "dialogue-line":
        require(s["stage"] == "return" and payload.get("key") == "debrief")
        require(isinstance(value, str) and value.isdigit())
        line = int(value)
        require(line == s.get("debrief_line", 0) + 1 and line <= 2)
        s["debrief_line"] = line
    elif action == "open":
        require(s["stage"] in ("interaction", "mini-game"))
        s["stage"] = "mini-game"
        s["feedback"] = (
            "Рабочая станция готова. Начните с наблюдений; "
            "изменения можно проверять и исправлять."
        )
    elif action == "report":
        require(s["stage"] == "return" and s.get("debrief_line", 0) >= 2)
        s["stage"] = "result"
        s["feedback"] = "Результат обсуждён. Что думаете об этой работе?"
    elif action == "react":
        require(s["stage"] == "result" and value in REACTIONS)
        s["reaction"] = value
        s["stage"] = "complete"
    elif action == "finish":
        require(s["stage"] in ("result", "complete") and not payload)
        s["stage"] = "complete"
    else:
        require(s["stage"] in ("mini-game", "return"))
        if action == "explore":
            require(s["stage"] == "return")
            s["feedback"] = additional_check(kind, s, payload)
            signature = f"{payload.get('key')}:{value}"
            explored = set(s.get("explored", []))
            explored.add(signature)
            s["explored"] = sorted(explored)
            s["extra_exploration"] = len(explored)
            s["extra_result"] = s["feedback"]
        elif action in ("hint", "assistant-question"):
            if action == "assistant-question":
                key = payload.get("key")
                require(
                    kind == "code" and key in ASSISTANT_QUESTIONS,
                    "Выберите вопрос из списка помощника",
                )
                s.setdefault("assistant_questions", []).append(key)
                s["feedback"] = "Ответ помощника готов."
            s["hints"] = min(3, s["hints"] + 1)
            s["example_shown"] = (
                bool(s.get("example_shown"))
                or kind == "code"
                and (
                    action == "assistant-question"
                    and payload.get("key") == "example"
                    or action == "hint"
                    and s["hints"] == 3
                )
            )
            if kind == "code":
                rewards.append("pair-programming")
        elif kind == "diagnosis":
            if action == "inspect":
                require(value in ("services", "deploy", "logs"))
                seen.add(value)
                s["feedback"] = {
                    "services": (
                        "API — ERROR; DATABASE и CACHE — ONLINE. Отказ локален."
                    ),
                    "deploy": (
                        "Релиз orders-1.8 начался в 20:14:33. Через секунду "
                        "выросли ответы 500."
                    ),
                    "logs": (
                        "Поток запущен. Нажмите на подозрительную запись; она "
                        "повторяется."
                    ),
                }[value]
            elif action == "log":
                require("logs" in seen)
                if value == "syntax":
                    seen.add("anomaly")
                    rewards.append("critical-log")
                    s["feedback"] = (
                        "OrderService: SyntaxError, orders/service.py:247. "
                        "Сопоставьте время с релизом."
                    )
                else:
                    s["attempts"] += 1
                    s["feedback"] = (
                        "Это успешный запрос. Он показывает, что часть API "
                        "продолжает отвечать."
                    )
            elif action == "hypothesis":
                require("anomaly" in seen)
                s["attempts"] += 1
                s["choices"].append(str(value))
                if value == "release":
                    seen.add("cause")
                    s["feedback"] = (
                        "Совпали время, сервис и трассировка. Найдена "
                        "незакрытая строка в релизе."
                    )
                else:
                    s["feedback"] = (
                        "Наблюдения не подтверждают гипотезу. База и сеть "
                        "отвечают; ошибка синтаксическая."
                    )
            elif action == "draft-repair":
                require(isinstance(value, str) and len(value) <= 4000)
                s["repair_code"] = value
            elif action == "repair":
                require("cause" in seen)
                s["attempts"] += 1
                s["repair_code"] = value
                valid_patch = value == "close-quote"
                if isinstance(value, str) and value != "close-quote":
                    try:
                        tree = ast.parse(value)
                        function = tree.body[0] if len(tree.body) == 1 else None
                        body = (
                            function.body
                            if isinstance(function, ast.FunctionDef)
                            else []
                        )
                        valid_patch = (
                            function.name == "order_status"
                            and len(body) == 2
                            and isinstance(body[0], ast.Assign)
                            and len(body[0].targets) == 1
                            and isinstance(body[0].targets[0], ast.Name)
                            and body[0].targets[0].id == "message"
                            and isinstance(body[0].value, ast.Constant)
                            and body[0].value.value == "Order created"
                            and isinstance(body[1], ast.Return)
                            and isinstance(body[1].value, ast.Name)
                            and body[1].value.id == "message"
                        )
                    except (SyntaxError, AttributeError):
                        valid_patch = False
                if valid_patch:
                    seen.add("patched")
                    s["feedback"] = "Строка закрыта. Теперь проверьте API."
                else:
                    s["feedback"] = (
                        "Перезапуск повторил SyntaxError. Сначала исправьте "
                        "причину в коде."
                    )
            elif action == "verify":
                require("patched" in seen)
                s["success"] = True
                s["feedback"] = (
                    "GET /api/orders → 200. Контрольный заказ → 201. "
                    "Индикатор сервера стал зелёным."
                )
            else:
                require(False, "Неизвестное действие диагностики")
        elif kind == "code":
            if action == "use-example":
                require(s.get("example_shown") or s["hints"] >= 3)
                s["example_used"] = True
                s["feedback"] = (
                    "Пример взят в работу. Прочитайте его и запустите тесты."
                )
            elif action == "draft":
                require(isinstance(value, str) and len(value) <= 4000)
                s["code"] = value
            elif action == "run":
                require(isinstance(value, str) and len(value) <= 4000)
                s["code"] = value
                s["tests"] = check_code(value)
                s["attempts"] += 1
                s["success"] = all(t["passed"] for t in s["tests"])
                s["feedback"] = (
                    "Все тесты прошли. Вернитесь к Борису."
                    if s["success"]
                    else (
                        "Есть несовпадения. Посмотрите входные данные и "
                        "ожидаемый результат, поправьте функцию."
                    )
                )
            else:
                require(False, "Неизвестное действие редактора")
        elif kind == "responsive":
            if action == "device":
                require(value in ("Desktop", "Tablet", "Mobile"))
                seen.add(value)
                dimensions = {"Desktop": 960, "Tablet": 600, "Mobile": 320}
                checks = responsive_checks(s.get("properties", {}), dimensions[value])
                s.setdefault("device_results", {})[value] = checks
                checked = set(s.get("checked", []))
                if all(checks.values()):
                    checked.add(value)
                else:
                    checked.discard(value)
                s["checked"] = sorted(checked)
                s["feedback"] = f"{value}: " + (
                    "макет помещается."
                    if all(checks.values())
                    else "проверьте переполнение, карточки, кнопку и читаемость."
                )
            elif action == "property":
                key = payload.get("key")
                require(isinstance(value, str))
                valid = (
                    key == "width"
                    and (
                        value in ("600px", "100%", "auto")
                        or value.isdigit()
                        and 40 <= int(value) <= 100
                    )
                    or key == "layout"
                    and value in ("row", "column", "wrap")
                    or key == "position"
                    and value in ("absolute", "static", "relative")
                    or key == "gap"
                    and value.isdigit()
                    and 0 <= int(value) <= 40
                    or key == "fontSize"
                    and value.isdigit()
                    and 12 <= int(value) <= 24
                )
                require(valid, "Недопустимое значение свойства")
                s.setdefault("properties", {})[key] = value
                s["checked"] = []
                s["device_results"] = {}
                s["feedback"] = "Макет обновлён. Проверьте изменения на устройствах."
            elif action == "verify":
                s["attempts"] += 1
                s["success"] = len(s.get("checked", [])) == 3 and all(
                    all(responsive_checks(s.get("properties", {}), width).values())
                    for width in (960, 600, 320)
                )
                s["feedback"] = (
                    "Три экрана прошли проверку. Можно показать Фронтине."
                    if s["success"]
                    else "Есть непроверенные экраны или проблемы макета."
                )
            else:
                require(False, "Неизвестное действие макета")
        elif kind == "ux":
            if action == "property":
                key = payload.get("key")
                require(
                    key in {*UX, "emailLabel", "passwordLabel"}
                    and isinstance(value, str)
                    and 1 <= len(value.strip()) <= 100
                )
                s.setdefault("properties", {})[key] = value
                s["feedback"] = "Прототип обновлён. Проверьте путь пользователя."
            elif action == "simulate":
                s["attempts"] += 1
                checks = ux_checks(s.get("properties", {}))
                descriptions = {
                    "order": "Сначала ищу адрес, затем пароль.",
                    "button": "Понимаю, что создаю аккаунт.",
                    "error": "Ввожу student.campus и ищу, как исправить адрес.",
                    "hint": "Выбираю пароль и проверяю минимальную длину.",
                    "reveal": "Показываю пароль и исправляю опечатку.",
                }
                trace = []
                for key, passed in checks.items():
                    trace.append(
                        {"step": key, "passed": passed, "message": descriptions[key]}
                    )
                    if not passed:
                        break
                s["user_trace"] = trace
                s["user_checks"] = {row["step"]: row["passed"] for row in trace}
                s["user_step"] = sum(row["passed"] for row in trace)
                s["success"] = all(checks.values())
                s["feedback"] = (
                    "Пользователь зарегистрировался без обращения в поддержку!"
                    if s["success"]
                    else "Пользователь остановился: " + trace[-1]["message"]
                )
            else:
                require(False, "Неизвестное действие формы")
        elif kind == "interview":
            if action == "question":
                require(value in QUESTIONS)
                seen.add(value)
                s["choices"].append(value)
                s.setdefault("interview_history", []).append(value)
                s["feedback"] = (
                    "Ответ заказчика записан в заметки интервью. Свяжите "
                    "факты, прежде чем предлагать решение."
                )
            elif action == "compose":
                require(
                    "why" in seen
                    and ("pain" in seen or "after" in seen)
                    and ("schedule" in seen or "frequency" in seen),
                    "Пока неясны цель, ручная работа или срок. Спросите заказчика.",
                )
                try:
                    proposal = json.loads(value or "")
                except (ValueError, TypeError):
                    require(False, "Не удалось прочитать решение")
                require(isinstance(proposal, dict))
                s["attempts"] += 1
                s["proposal_draft"] = proposal
                expected = {
                    "problem": "manual",
                    "automation": "weekly-report",
                    "delivery": "friday-director",
                    "data": "paid-csv",
                }
                s["success"] = proposal == expected
                s["feedback"] = (
                    "Да! Готовый CSV с оплаченными заказами за неделю директору "
                    "по пятницам в 16:00. Настройки только у меня; "
                    "если заказов нет — уведомление. Договорились!"
                    if s["success"]
                    else "Мне всё ещё придётся собирать отчёт руками или ждать его. "
                    "Давайте сверим решение с перепиской."
                )
            elif action == "proposal":
                require({"who", "why", "what", "format", "pain", "schedule"} <= seen)
                s["attempts"] += 1
                s["choices"].append(str(value))
                if value == "scheduled-report":
                    seen.add("proposal")
                    s["feedback"] = (
                        "Заказчик: да, нужен готовый отчёт по пятницам, а не "
                        "ещё одна ручная операция. Уточним критерии приёмки."
                    )
                else:
                    s["feedback"] = (
                        "Заказчик: выгрузка всех данных всё ещё оставляет два "
                        "часа ручной работы. Цель не достигнута."
                    )
            elif action == "criteria":
                require("proposal" in seen)
                s["attempts"] += 1
                s["success"] = value == "friday-filtered-csv"
                s["feedback"] = (
                    (
                        "Согласовано: пятница 16:00, оплаченные за неделю, CSV, "
                        "директор, доступ только руководителю."
                    )
                    if s["success"]
                    else (
                        "Не хватает срока, состава отчёта или ограничения "
                        "доступа. Вернитесь к заметкам."
                    )
                )
            else:
                require(False, "Неизвестное действие интервью")
        elif kind == "data":
            if action == "slice":
                require(
                    value
                    in (
                        "orders",
                        "average",
                        "regions",
                        "products",
                        "period",
                        "operations",
                    )
                )
                seen.add(value)
                s["feedback"] = (
                    "Срез открыт. Сравните рост выручки с количеством "
                    "заказов и источником операций."
                )
            elif action == "operation":
                require("operations" in seen)
                if value == "TEST-409":
                    seen.add("source")
                    s["feedback"] = (
                        "TEST-409: internal=true, environment=test, "
                        "корпоративная проверка оплаты. "
                        "Источник попал в production-витрину."
                    )
                else:
                    s["attempts"] += 1
                    s["feedback"] = (
                        "Обычная оплаченная покупка. Она не объясняет скачок "
                        "среднего чека."
                    )
            elif action == "conclusion":
                require("source" in seen)
                s["attempts"] += 1
                s["choices"].append(str(value))
                if value == "exclude-test":
                    seen.add("filtered")
                    s["feedback"] = (
                        "Тестовые операции исключены из копии отчёта. Теперь "
                        "сравните очищенный ряд с исходным."
                    )
                else:
                    s["feedback"] = (
                        "Удалять крупные реальные заказы нельзя. Фильтр должен "
                        "опираться на источник, а не на желаемый график."
                    )
            elif action == "compare":
                require("filtered" in seen)
                s["success"] = True
                s["feedback"] = (
                    "Было: 110, 105, 115, 390, 410. Стало: 110, 105, 115, "
                    "112, 118. Резкий рост был тестовым трафиком."
                )
            else:
                require(False, "Неизвестное действие dashboard")
        else:
            require(False, "Неизвестная мини-игра")
        if action in ("verify", "run", "simulate", "criteria", "compose"):
            if not s["success"] and not state["success"]:
                s["failed_checks"] = s.get("failed_checks", 0) + 1
        # Optional experiments cannot undo the already accepted main result.
        s["success"] = s["success"] or state["success"]
        if s["success"]:
            s["stage"] = "return"
    s["seen"] = sorted(seen)
    return s, rewards


def award(service, slug):
    title, description = REWARDS[slug]
    achievement = service.session.scalar(
        select(Achievement).where(Achievement.slug == slug)
    )
    if not achievement:
        achievement = Achievement(slug=slug, title=title, description=description)
        service.session.add(achievement)
        service.session.flush()
    exists = service.session.scalar(
        select(UserAchievement.id).where(
            UserAchievement.user_id == service.user_id,
            UserAchievement.achievement_id == achievement.id,
        )
    )
    if exists:
        return None
    service.session.add(
        UserAchievement(user_id=service.user_id, achievement_id=achievement.id)
    )
    return AwardResult(slug=slug, title=title, description=description)


def act(service, quest_id, request_id, action, payload):
    service.repo.lock_user(service.user_id)
    quest = service.definition(quest_id)
    require(quest.availability_config.get("engine") == 2)
    target = f"quest:{quest.id}"
    previous = service.repo.event(service.user_id, request_id)
    content = {"action": action, "payload": payload}
    if previous:
        require(
            (previous.event_type, previous.target_key, previous.payload)
            == ("minigame_action", target, content),
            "Request ID has different content",
        )
        return GameActionResult(
            state=previous.result["state"],
            awards=[AwardResult(**item) for item in previous.result["awards"]],
        )
    player = service.repo.player(service.user_id, quest.id)
    require(
        player
        and (
            player.status == "active"
            or (action == "finish" and player.status == "completed")
        ),
        "Примите задание у NPC",
    )
    state = state_for(service, quest)
    new, rewards = transition(quest.availability_config["kind"], state, action, payload)
    # Server clocks bound engagement time; a forged client duration is never accepted.
    timestamp = datetime.now(UTC)
    prior_time = (
        datetime.fromisoformat(state["last_action"])
        if state.get("last_action")
        else timestamp
    )
    new["active_seconds"] += max(
        0, min(90, int((timestamp - prior_time).total_seconds()))
    )
    new["last_action"] = timestamp.isoformat()
    new["action_count"] = state.get("action_count", 0) + 1
    if action in ("react", "finish") and player.status == "active":
        player.status, player.completed_at = "completed", now()
        rewards.append(quest.slug)
        tracked = service.session.get(TrackedQuest, service.user_id)
        if tracked and tracked.player_quest_id == player.id:
            service.session.delete(tracked)
        if action == "react":
            record_interest(service, quest, new)
    stage_order = ["interaction", "mini-game", "return", "result", "complete"]
    stage_index = stage_order.index(new["stage"]) if new["stage"] != "intro" else 0
    progress = service.repo.progress(player.id)
    for index, objective in enumerate(service.repo.objectives(quest.id)):
        if index < stage_index and objective.id not in progress:
            service.session.add(
                PlayerQuestObjective(
                    player_quest_id=player.id,
                    objective_id=objective.id,
                    current_count=1,
                    completed_at=now(),
                )
            )
    awarded = [item for slug in rewards if (item := award(service, slug))]
    result = GameActionResult(state=new, awards=awarded)
    service.session.add(
        QuestEvent(
            user_id=service.user_id,
            request_id=request_id,
            event_type="minigame_action",
            target_key=target,
            payload=content,
            result={
                "state": result.state,
                "awards": [
                    {
                        "slug": item.slug,
                        "title": item.title,
                        "description": item.description,
                    }
                    for item in result.awards
                ],
            },
        )
    )
    service.session.commit()
    return result


def record_interest(service, quest, state):
    if quest.direction_id is None:
        return
    # Curiosity and self-report dominate correctness. Assistance never subtracts.
    weight = {"more": 4, "interesting": 3, "not-mine": 0, "enough": 0}[
        state["reaction"]
    ]
    weight += min(1, state["extra_exploration"]) + int(state["active_seconds"] >= 120)
    profile = service.session.scalar(
        select(InterestProfile).where(InterestProfile.user_id == service.user_id)
    )
    if not profile:
        profile = InterestProfile(
            user_id=service.user_id, direction_scores={}, event_count=0
        )
        service.session.add(profile)
    scores = dict(profile.direction_scores)
    key = str(quest.direction_id)
    scores[key] = scores.get(key, 0) + weight
    profile.direction_scores = scores
    profile.event_count += 1
    service.session.add(
        InterestEvent(
            user_id=service.user_id,
            task_id=None,
            direction_id=quest.direction_id,
            source="quest-experience",
            weight=weight,
            explanation=(
                f"{quest.title}: реакция {state['reaction']}; "
                f"попыток {state['attempts']}; помощь {state['hints']}."
            ),
        )
    )

    service.session.flush()
    events = service.session.scalars(
        select(InterestEvent).where(
            InterestEvent.user_id == service.user_id,
            InterestEvent.source == "quest-experience",
        )
    )
    signals = {}
    for event in events:
        signals[event.direction_id] = signals.get(event.direction_id, 0) + event.weight
    positive = [key for key in signals if signals[key] > 0]
    leader = min(positive, key=lambda key: (-signals[key], key)) if positive else None
    direction = service.session.get(CareerDirection, leader) if leader else None
    recommendation = service.session.scalar(
        select(Recommendation).where(Recommendation.user_id == service.user_id)
    )
    if recommendation is None:
        recommendation = Recommendation(user_id=service.user_id)
        service.session.add(recommendation)
    recommendation.direction_id = leader
    recommendation.explanation = (
        f"Попробуйте ещё занятия в направлении {direction.title}: "
        "вы отметили интерес или продолжили исследование. "
        "Это ориентир, не оценка способностей."
        if direction
        else "Продолжайте сравнивать направления по собственным впечатлениям."
    )
