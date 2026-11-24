import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from test_quest_api import client as client
from test_quest_api import headers

from app.database import get_session
from app.main import app
from app.models import CareerDirection
from app.quest_gameplay import RESPONSIVE, UX, initial_state, transition
from app.quest_python import check_code

spec = importlib.util.spec_from_file_location(
    "seed_minigames", Path(__file__).parents[1] / "scripts/seed_minigames.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
seed = module.seed

CODE = """def calculate_average(grades):
    values = [g for g in grades if g is not None]
    if len(values) == 0:
        return 0
    return sum(values) / len(values)
"""


@pytest.fixture
def games(client):
    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    for slug in ("backend", "frontend", "analytics"):
        session.add(CareerDirection(slug=slug, title=slug, description=slug))
    session.flush()
    seed(session)
    seed(session)
    generator.close()
    return client


def action(client, qid, name, value=None, key=None, request_id=None, user=1):
    payload = {}
    if value is not None:
        payload["value"] = value
    if key is not None:
        payload["key"] = key
    return client.post(
        f"/quests/{qid}/actions",
        headers=headers(user),
        json={
            "request_id": request_id or str(uuid4()),
            "action": name,
            "payload": payload,
        },
    )


def start(client, kind):
    quests = client.get("/quests", headers=headers()).json()
    assert len(quests) == 6
    assert all(q["slug"] != "server-on-vacation" for q in quests)
    quest = next(q for q in quests if q["gameplay"]["kind"] == kind)
    qid = quest["id"]
    assert action(client, qid, "open").status_code == 409
    assert (
        client.post(
            f"/quests/{qid}/offer",
            headers=headers(),
            json={"npc_id": quest["giver_npc_id"]},
        ).status_code
        == 200
    )
    assert client.post(f"/quests/{qid}/accept", headers=headers()).status_code == 200
    assert action(client, qid, "open").status_code == 409
    for line in range(1, 7):
        assert action(client, qid, "intro-line", str(line)).status_code == 200
    assert action(client, qid, "intro-complete").status_code == 200
    assert action(client, qid, "open").status_code == 200
    return qid


def solve(client, qid, kind):
    def do(name, value=None, key=None):
        response = action(client, qid, name, value, key)
        assert response.status_code == 200, response.text
        return response.json()

    if kind == "diagnosis":
        assert action(client, qid, "verify").status_code == 409
        for value in ("services", "deploy", "logs"):
            do("inspect", value)
        do("log", "ok")
        assert do("log", "syntax")["awards"][0]["slug"] == "critical-log"
        assert do("log", "syntax")["awards"] == []
        assert not do("hypothesis", "database")["state"]["success"]
        do("hypothesis", "release")
        do("repair", "restart")
        do("repair", "close-quote")
        do("verify")
    elif kind == "code":
        assert not do("run", "def calculate_average(grades):\n    return 0")["state"][
            "success"
        ]
        assert do("hint")["awards"][0]["slug"] == "pair-programming"
        assert do("hint")["awards"] == []
        assert do("hint")["state"]["example_shown"]
        do("use-example")
        do("draft", CODE)
        assert (
            client.get(f"/quests/{qid}", headers=headers()).json()["gameplay"]["state"][
                "code"
            ]
            == CODE
        )
        assert do("run", CODE)["state"]["example_used"]
    elif kind == "responsive":
        assert not do("verify")["state"]["success"]
        for key, value in RESPONSIVE.items():
            do("property", value, key)
        for device in ("Mobile", "Tablet", "Desktop"):
            do("device", device)
        do("property", "100%", "width")
        assert not do("verify")["state"]["success"]
        for device in ("Mobile", "Tablet", "Desktop"):
            do("device", device)
        do("verify")
    elif kind == "ux":
        assert not do("simulate")["state"]["success"]
        for key, value in UX.items():
            do("property", value, key)
        do("simulate")
    elif kind == "interview":
        assert action(client, qid, "proposal", "scheduled-report").status_code == 409
        assert action(client, qid, "question", "schedule").status_code == 200
        for question in ("color", "who", "why", "what", "format", "pain", "schedule"):
            do("question", question)
        do("proposal", "export-all")
        do("proposal", "scheduled-report")
        assert not do("criteria", "all-anytime")["state"]["success"]
        do("criteria", "friday-filtered-csv")
    else:
        assert action(client, qid, "operation", "TEST-409").status_code == 409
        for value in (
            "orders",
            "average",
            "regions",
            "products",
            "period",
            "operations",
        ):
            do("slice", value)
        do("operation", "ORD-407")
        do("operation", "TEST-409")
        do("conclusion", "delete-large")
        do("conclusion", "exclude-test")
        do("compare")


@pytest.mark.parametrize(
    "kind", ["diagnosis", "code", "responsive", "ux", "interview", "data"]
)
def test_finish_without_reaction_is_idempotent(games, kind):
    qid = start(games, kind)
    assert action(games, qid, "finish").status_code == 409
    solve(games, qid, kind)
    for line in ("1", "2"):
        assert action(games, qid, "dialogue-line", line, "debrief").status_code == 200
    assert action(games, qid, "report").status_code == 200
    request_id = str(uuid4())
    first = action(games, qid, "finish", request_id=request_id)
    assert first.status_code == 200
    assert action(games, qid, "finish", request_id=request_id).json() == first.json()
    again = action(games, qid, "finish")
    assert again.status_code == 200 and again.json()["awards"] == []
    quest = games.get(f"/quests/{qid}", headers=headers()).json()
    assert quest["status"] == "completed"
    assert all(objective["completed"] for objective in quest["objectives"])
    assert games.get("/interest-events", headers=headers()).json() == []


@pytest.mark.parametrize(
    "kind", ["diagnosis", "code", "responsive", "ux", "interview", "data"]
)
def test_full_experience_persistence_and_consequences(games, kind):
    qid = start(games, kind)
    assert action(games, qid, "react", "more").status_code == 409
    solve(games, qid, kind)
    quest = games.get(f"/quests/{qid}", headers=headers()).json()
    assert quest["gameplay"]["state"]["stage"] == "return"
    assert quest["status"] == "active"
    assert action(games, qid, "report", user=2).status_code == 409
    extras = {
        "diagnosis": ("endpoint", "/api/profile"),
        "code": ("input", "[0, null, 8]"),
        "responsive": ("viewport", "280"),
        "ux": ("form", "typo-corrected"),
        "interview": ("question", "empty-week"),
        "data": ("slice", "regions"),
    }
    key, value = extras[kind]
    assert action(games, qid, "explore").status_code == 409
    assert action(games, qid, "explore", value, key).status_code == 200
    assert (
        action(games, qid, "explore", value, key).json()["state"]["extra_exploration"]
        == 1
    )
    assert action(games, qid, "report").status_code == 409
    for line in ("1", "2"):
        assert action(games, qid, "dialogue-line", line, "debrief").status_code == 200
    assert action(games, qid, "report").status_code == 200
    request = str(uuid4())
    result = action(games, qid, "react", "more", request_id=request)
    assert result.status_code == 200
    assert (
        action(games, qid, "react", "more", request_id=request).json() == result.json()
    )
    assert action(games, qid, "react", "enough", request_id=request).status_code == 409
    quest = games.get(f"/quests/{qid}", headers=headers()).json()
    assert quest["status"] == "completed"
    assert all(o["completed"] for o in quest["objectives"])
    assert quest["gameplay"]["state"]["extra_exploration"] == 1
    assert (
        games.get(f"/quests/{qid}", headers=headers(2)).json()["status"] == "available"
    )
    events = games.get("/interest-events", headers=headers()).json()
    assert len(events) == 1 and events[0]["source"] == "quest-experience"
    assert events[0]["weight"] >= 4
    assert games.get("/achievements", headers=headers()).json()
    assert action(games, qid, "report").status_code == 409


def test_idempotency_validation_and_legacy_bypass(games):
    qid = start(games, "code")
    request = str(uuid4())
    first = action(games, qid, "run", CODE, request_id=request)
    assert first.status_code == 200
    assert action(games, qid, "run", CODE, request_id=request).json() == first.json()
    assert first.json()["state"]["attempts"] == 1
    assert action(games, qid, "report", request_id=request).status_code == 409
    assert action(games, qid, "hint", [1]).status_code == 422
    assert action(games, qid, "run", "x" * 4001).status_code == 422
    assert (
        games.post(
            "/game/interactions",
            headers=headers(),
            json={
                "request_id": str(uuid4()),
                "event_type": "result",
                "target_key": "tiny-feature",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "program",
    [
        "import os",
        "def calculate_average(grades):\n    while True:\n        pass",
        "def calculate_average(grades):\n    return __import__('os').getcwd()",
        "def calculate_average(grades):\n    return grades.__class__",
        "def calculate_average(grades):\n    return 0 / 0",
    ],
)
def test_python_rejects_unsafe_and_unsupported_code(program):
    assert not all(t["passed"] for t in check_code(program))


def test_python_real_logic_and_zero_edge_case():
    assert all(t["passed"] for t in check_code(CODE))
    loop = """def calculate_average(grades):
    total = 0
    count = 0
    for grade in grades:
        if grade is not None:
            total += grade
            count += 1
    if count == 0:
        return 0
    return total / count
"""
    assert all(t["passed"] for t in check_code(loop))
    assert not all(
        t["passed"] for t in check_code(CODE.replace("if g is not None", "if g"))
    )


def test_intro_saved_and_cannot_skip_story(games):
    quest = games.get("/quests", headers=headers()).json()[0]
    qid = quest["id"]
    games.post(
        f"/quests/{qid}/offer",
        headers=headers(),
        json={"npc_id": quest["giver_npc_id"]},
    )
    games.post(f"/quests/{qid}/accept", headers=headers())
    assert action(games, qid, "open").status_code == 409
    assert action(games, qid, "intro-complete").status_code == 409
    assert action(games, qid, "intro-line", "2").status_code == 409
    assert action(games, qid, "intro-line", "1").status_code == 200
    restored = games.get(f"/quests/{qid}", headers=headers()).json()["gameplay"][
        "state"
    ]
    assert restored["stage"] == "intro" and restored["intro_line"] == 1
    assert action(games, qid, "intro-line", "1").status_code == 409


def game_state():
    return {**initial_state(), "stage": "mini-game"}


def test_responsive_accepts_alternative_layouts_and_editing_is_not_attempt():
    for width, layout, position in (
        ("95", "wrap", "relative"),
        ("auto", "column", "static"),
    ):
        state = game_state()
        for key, value in (
            ("width", width),
            ("layout", layout),
            ("position", position),
            ("gap", "20"),
        ):
            state, _ = transition(
                "responsive", state, "property", {"key": key, "value": value}
            )
        assert state["attempts"] == 0
        for device in ("Desktop", "Tablet", "Mobile"):
            state, _ = transition("responsive", state, "device", {"value": device})
        state, _ = transition("responsive", state, "verify", {})
        assert state["success"] and state["attempts"] == 1
        state, _ = transition(
            "responsive", state, "property", {"key": "width", "value": "600px"}
        )
        state, _ = transition("responsive", state, "verify", {})
        assert state["success"] and state["stage"] == "return"


def test_ux_walk_is_sequential_and_accepts_clear_free_text():
    state = game_state()
    state, _ = transition("ux", state, "simulate", {})
    assert len(state["user_trace"]) == 1 and state["user_step"] == 0
    for key, value in {
        "order": "email-first",
        "button": "Создать аккаунт",
        "error": "Исправьте почту: например name@example.ru",
        "hint": "Пароль длиной от 8 символов",
        "reveal": "show",
    }.items():
        state, _ = transition("ux", state, "property", {"key": key, "value": value})
    assert state["attempts"] == 1
    state, _ = transition("ux", state, "simulate", {})
    assert state["success"] and len(state["user_trace"]) == 5


def test_diagnosis_patch_is_code_and_draft_persists():
    state = {**game_state(), "seen": ["cause"]}
    code = 'def order_status():\n    message = "Order created"\n    return message'
    state, _ = transition("diagnosis", state, "draft-repair", {"value": code})
    assert state["repair_code"] == code and state["attempts"] == 0
    state, _ = transition("diagnosis", state, "repair", {"value": code})
    assert "patched" in state["seen"]
    state, _ = transition("diagnosis", state, "verify", {})
    assert state["success"]


def test_data_can_conclude_from_source_without_opening_every_slice():
    state = {**game_state(), "seen": ["source"]}
    state, _ = transition("data", state, "conclusion", {"value": "exclude-test"})
    state, _ = transition("data", state, "compare", {})
    assert state["success"]


def test_legacy_saved_interaction_does_not_lose_progress():
    legacy = {**initial_state(), "stage": "interaction"}
    legacy.pop("intro_line")
    state, _ = transition("code", legacy, "open", {})
    assert state["stage"] == "mini-game"


def test_postpone_resume_and_restart_from_phone(games):
    q = next(
        q
        for q in games.get("/quests", headers=headers()).json()
        if q["gameplay"]["kind"] == "diagnosis"
    )
    qid = q["id"]
    games.post(f"/quests/{qid}/offer", headers=headers(), json={"npc_id": "boris"})
    games.post(f"/quests/{qid}/accept", headers=headers())
    assert action(games, qid, "intro-defer").status_code == 409
    for line in range(1, 5):
        assert action(games, qid, "intro-line", str(line)).status_code == 200
    deferred = action(games, qid, "intro-defer").json()["state"]
    assert deferred["stage"] == "intro" and deferred["intro_line"] == 4
    assert deferred["intro_deferred"] and deferred["attempts"] == 0
    assert action(games, qid, "open").status_code == 409
    assert action(games, qid, "intro-line", "5").status_code == 409
    assert games.get(f"/quests/{qid}", headers=headers()).json()["gameplay"]["state"][
        "intro_deferred"
    ]
    resumed = action(games, qid, "intro-resume").json()["state"]
    assert resumed["intro_line"] == 5 and not resumed["intro_deferred"]
    action(games, qid, "intro-line", "6")
    action(games, qid, "intro-complete")
    action(games, qid, "open")
    action(games, qid, "inspect", "services")
    assert games.post(f"/quests/{qid}/abandon", headers=headers()).status_code == 200
    restarted = games.post(f"/quests/{qid}/accept", headers=headers()).json()
    assert restarted["gameplay"]["state"]["intro_line"] == 0
    assert restarted["gameplay"]["state"]["stage"] == "intro"
    assert restarted["gameplay"]["state"]["seen"] == []
    assert not any(o["completed"] for o in restarted["objectives"])
    assert action(games, qid, "open").status_code == 409


def test_composed_solution_requires_evidence_and_accepts_wrong_attempts():
    import json

    state = {**initial_state(), "stage": "mini-game"}
    correct = {
        "problem": "manual",
        "automation": "weekly-report",
        "delivery": "friday-director",
        "data": "paid-csv",
    }
    from app.quest_errors import QuestError

    with pytest.raises(QuestError) as error:
        transition("interview", state, "compose", {"value": json.dumps(correct)})
    assert error.value.status_code == 409
    for question in ("bigger", "place", "color", "why", "after", "frequency"):
        state, _ = transition("interview", state, "question", {"value": question})
    assert state["interview_history"] == [
        "bigger",
        "place",
        "color",
        "why",
        "after",
        "frequency",
    ]
    wrong, _ = transition(
        "interview",
        state,
        "compose",
        {"value": json.dumps({**correct, "automation": "export"})},
    )
    assert not wrong["success"] and wrong["failed_checks"] == 1
    solved, _ = transition(
        "interview", wrong, "compose", {"value": json.dumps(correct)}
    )
    assert solved["success"] and solved["stage"] == "return"


@pytest.mark.parametrize("answer", ["yes", "partly", "help", "silence"])
def test_code_debrief_preserves_player_answer(answer):
    state = {**initial_state(), "stage": "return", "success": True}
    result, _ = transition("code", state, "debrief-answer", {"value": answer})
    assert result["code_answer"] == answer and result["debrief_line"] == 1
    result, _ = transition(
        "code", result, "dialogue-line", {"key": "debrief", "value": "2"}
    )
    result, _ = transition("code", result, "report", {})
    assert result["stage"] == "result"


def test_assistant_only_accepts_prepared_questions_and_preserves_subject():
    from app.quest_errors import QuestError
    from app.quest_gameplay import ASSISTANT_QUESTIONS

    state = {**initial_state(), "stage": "mini-game"}
    for key in ("123123", "как дела", "", None):
        with pytest.raises(QuestError) as error:
            transition("code", state, "assistant-question", {"key": key})
        assert error.value.status_code == 409
    for key in ASSISTANT_QUESTIONS:
        state, _ = transition("code", state, "assistant-question", {"key": key})
    assert set(state["assistant_questions"]) == ASSISTANT_QUESTIONS
    assert state["example_shown"]
    state, _ = transition("code", state, "use-example", {})
    assert state["example_used"]
    with pytest.raises(QuestError):
        transition("diagnosis", state, "assistant-question", {"key": "none"})


def test_story_can_finish_without_questionnaire_or_ratings(games):
    assert games.put("/game/final-quest/complete", headers=headers()).status_code == 409
    for kind in ("diagnosis", "code", "responsive", "ux", "interview", "data"):
        qid = start(games, kind)
        solve(games, qid, kind)
        for line in ("1", "2"):
            assert (
                action(games, qid, "dialogue-line", line, "debrief").status_code == 200
            )
        assert action(games, qid, "report").status_code == 200
        assert action(games, qid, "finish").status_code == 200
    final = games.put("/game/final-quest/complete", headers=headers())
    assert final.status_code == 200 and final.json()["main_story_completed"] is True
    assert (
        games.put("/game/final-quest/complete", headers=headers()).json()
        == final.json()
    )
    achievements = games.get("/achievements", headers=headers()).json()
    assert sum(a["slug"] == "tried-everything" for a in achievements) == 1
    assert (
        games.get("/questionnaire/state", headers=headers()).json()["status"]
        == "not_started"
    )
