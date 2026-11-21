from uuid import uuid4

import pytest
from test_minigames import action, solve, start
from test_quest_api import client as client
from test_quest_api import headers

pytest_plugins = ("test_minigames",)


def profile(client):
    return client.get("/activity-profile", headers=headers()).json()


def reflect(client, qid, response, code=None, request_id=None):
    return client.post(
        f"/quests/{qid}/reflection",
        headers=headers(),
        json={
            "request_id": request_id or str(uuid4()),
            "response": response,
            "activity_code": code,
        },
    )


def test_failed_attempt_reflection_is_independent_and_idempotent(games):
    qid = start(games, "code")
    assert action(games, qid, "hint").status_code == 200
    assert profile(games)["insights"] == []
    assert reflect(games, qid, "repeat", "coding").status_code == 409
    assert (
        action(
            games, qid, "run", "def calculate_average(grades):\n    return 0"
        ).status_code
        == 200
    )
    assert profile(games)["insights"] == []
    request_id = str(uuid4())
    first = reflect(games, qid, "repeat", "coding", request_id)
    assert first.status_code == 200
    assert reflect(games, qid, "unsure").status_code == 200
    assert reflect(games, qid, "repeat", "coding", request_id).json() == first.json()
    assert reflect(games, qid, "not_mine", "coding", request_id).status_code == 409
    assert profile(games)["insights"] == []
    assert games.get(f"/quests/{qid}", headers=headers()).json()["status"] == "active"
    assert games.post(f"/quests/{qid}/abandon", headers=headers()).status_code == 200
    assert profile(games)["history"][0]["reflection"]["response"] == "unsure"


def test_investigation_suggests_another_context(games):
    qid = start(games, "diagnosis")
    assert action(games, qid, "inspect", "logs").status_code == 200
    assert action(games, qid, "log", "syntax").status_code == 200
    assert reflect(games, qid, "repeat", "investigation").status_code == 200
    result = profile(games)
    assert result["insights"][0]["status"] == "hypothesis"
    assert result["next_step"]["title"] == "Почему всё стало лучше?"
    assert result["careers"] == []


def test_interest_requires_distinct_quests_and_mixed_responses(games):
    first = start(games, "diagnosis")
    assert action(games, first, "inspect", "logs").status_code == 200
    assert action(games, first, "log", "syntax").status_code == 200
    assert reflect(games, first, "repeat", "investigation").status_code == 200
    assert reflect(games, first, "repeat", "investigation").status_code == 200
    assert profile(games)["insights"][0]["status"] == "hypothesis"
    assert profile(games)["careers"] == []

    second = start(games, "data")
    assert action(games, second, "slice", "operations").status_code == 200
    assert action(games, second, "operation", "TEST-409").status_code == 200
    assert reflect(games, second, "repeat", "investigation").status_code == 200
    result = profile(games)
    insight = next(
        i for i in result["insights"] if i["activity_code"] == "investigation"
    )
    assert insight["status"] == "repeated"
    assert {e["quest_id"] for e in insight["evidence"]} == {first, second}
    assert result["careers"]

    assert reflect(games, second, "not_mine", "investigation").status_code == 200
    result = profile(games)
    insight = next(
        i for i in result["insights"] if i["activity_code"] == "investigation"
    )
    assert insight["status"] == "mixed"
    assert result["careers"] == []


def test_other_players_actions_do_not_authorize_reflection(games):
    qid = start(games, "code")
    assert (
        action(
            games, qid, "run", "def calculate_average(grades):\n    return 0"
        ).status_code
        == 200
    )
    quest = games.get(f"/quests/{qid}", headers=headers()).json()
    assert (
        games.post(
            f"/quests/{qid}/offer",
            headers=headers(2),
            json={"npc_id": quest["giver_npc_id"]},
        ).status_code
        == 200
    )
    assert games.post(f"/quests/{qid}/accept", headers=headers(2)).status_code == 200
    response = games.post(
        f"/quests/{qid}/reflection",
        headers=headers(2),
        json={
            "request_id": str(uuid4()),
            "response": "repeat",
            "activity_code": "coding",
        },
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("diagnosis", {"investigation", "coding", "verification"}),
        ("code", {"coding", "verification"}),
        ("responsive", {"interface", "verification"}),
        ("ux", {"interface", "users"}),
        ("interview", {"users", "requirements"}),
        ("data", {"investigation", "data", "verification"}),
    ],
)
def test_each_game_offers_observed_activities_for_reflection(games, kind, expected):
    qid = start(games, kind)
    initial = next(row for row in profile(games)["history"] if row["quest_id"] == qid)
    assert initial["activities"] == []
    assert profile(games)["insights"] == []

    solve(games, qid, kind)
    history = next(row for row in profile(games)["history"] if row["quest_id"] == qid)
    assert {row["code"] for row in history["activities"]} == expected
    assert profile(games)["insights"] == []
    for code in expected:
        response = reflect(games, qid, "repeat", code)
        assert response.status_code == 200
        assert response.json()["activity_code"] == code
        assert profile(games)["insights"][0]["status"] == "hypothesis"
    assert games.get(f"/quests/{qid}", headers=headers()).json()["status"] == "active"


@pytest.mark.parametrize(
    ("kind", "steps", "code"),
    [
        (
            "diagnosis",
            [("inspect", "logs", None), ("log", "syntax", None)],
            "investigation",
        ),
        (
            "code",
            [("run", "def calculate_average(grades):\n    return 0", None)],
            "coding",
        ),
        ("responsive", [("property", "100%", "width")], "interface"),
        ("ux", [("simulate", None, None)], "users"),
        ("interview", [("question", "who", None)], "users"),
        ("data", [("slice", "regions", None)], "data"),
    ],
)
def test_each_game_allows_reflection_before_success(games, kind, steps, code):
    qid = start(games, kind)
    for name, value, key in steps:
        result = action(games, qid, name, value, key)
        assert result.status_code == 200
        assert not result.json()["state"]["success"]
    history = next(row for row in profile(games)["history"] if row["quest_id"] == qid)
    assert code in {row["code"] for row in history["activities"]}
    assert reflect(games, qid, "repeat", code).status_code == 200
    assert profile(games)["insights"][0]["status"] == "hypothesis"
    assert games.get(f"/quests/{qid}", headers=headers()).json()["status"] == "active"


def test_completed_legacy_reaction_can_be_clarified_from_history(games):
    qid = start(games, "diagnosis")
    solve(games, qid, "diagnosis")
    for line in ("1", "2"):
        assert action(games, qid, "dialogue-line", line, "debrief").status_code == 200
    assert action(games, qid, "report").status_code == 200
    assert action(games, qid, "react", "interesting").status_code == 200

    before = profile(games)
    history = next(row for row in before["history"] if row["quest_id"] == qid)
    assert history["status"] == "completed"
    assert history["legacy_reaction"] == "interesting"
    assert history["reflection"] is None
    assert "investigation" in {row["code"] for row in history["activities"]}
    assert before["insights"] == []

    assert reflect(games, qid, "repeat", "investigation").status_code == 200
    restored = profile(games)
    history = next(row for row in restored["history"] if row["quest_id"] == qid)
    assert history["legacy_reaction"] == "interesting"
    assert history["reflection"]["activity_code"] == "investigation"
    assert restored["insights"][0]["status"] == "hypothesis"
    assert (
        games.get(f"/quests/{qid}", headers=headers()).json()["status"] == "completed"
    )


def test_reset_preserves_reflection_but_requires_new_actions_for_new_answer(games):
    qid = start(games, "code")
    assert (
        action(
            games, qid, "run", "def calculate_average(grades):\n    return 0"
        ).status_code
        == 200
    )
    saved = reflect(games, qid, "repeat", "coding").json()
    assert games.post(f"/quests/{qid}/abandon", headers=headers()).status_code == 200
    history = next(row for row in profile(games)["history"] if row["quest_id"] == qid)
    assert history["reflection"] == saved
    assert history["activities"] == []
    assert profile(games)["insights"][0]["status"] == "hypothesis"

    assert games.post(f"/quests/{qid}/accept", headers=headers()).status_code == 200
    assert reflect(games, qid, "repeat", "coding").status_code == 409
    for line in range(1, 7):
        assert action(games, qid, "intro-line", str(line)).status_code == 200
    assert action(games, qid, "intro-complete").status_code == 200
    assert action(games, qid, "open").status_code == 200
    assert (
        action(
            games, qid, "run", "def calculate_average(grades):\n    return 0"
        ).status_code
        == 200
    )
    assert reflect(games, qid, "not_mine", "coding").status_code == 200
    assert profile(games)["insights"] == []
