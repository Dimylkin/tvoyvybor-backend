from uuid import uuid4

from test_minigames import games as games
from test_quest_api import client as client
from test_quest_api import headers

from app.database import get_session
from app.main import app
from app.quest_gameplay import initial_state
from app.quest_models import PlayerQuest, PlayerQuestObjective, QuestEvent, now


def test_one_active_professional_quest_per_mentor(games):
    quests = games.get("/quests", headers=headers()).json()
    backend = [q for q in quests if q["giver_npc_id"] == "boris"]
    frontend = next(q for q in quests if q["giver_npc_id"] == "frontina")
    for q in [*backend, frontend]:
        assert (
            games.post(
                f"/quests/{q['id']}/offer",
                headers=headers(),
                json={"npc_id": q["giver_npc_id"]},
            ).status_code
            == 200
        )
    first, second = backend
    assert (
        games.post(f"/quests/{first['id']}/accept", headers=headers()).status_code
        == 200
    )
    assert (
        games.post(f"/quests/{first['id']}/accept", headers=headers()).status_code
        == 200
    )
    conflict = games.post(f"/quests/{second['id']}/accept", headers=headers())
    assert conflict.status_code == 409
    assert first["title"] in conflict.json()["detail"]
    assert (
        games.post(f"/quests/{frontend['id']}/accept", headers=headers()).status_code
        == 200
    )
    assert (
        games.get(f"/quests/{first['id']}", headers=headers()).json()["status"]
        == "active"
    )


def test_legacy_two_active_quests_remain_accessible_and_keep_progress(games):
    quests = games.get("/quests", headers=headers()).json()
    backend = [q for q in quests if q["giver_npc_id"] == "boris"]
    generator = app.dependency_overrides[get_session]()
    session = next(generator)
    saved = {}
    for index, quest in enumerate(backend):
        player = PlayerQuest(
            user_id=1, quest_id=quest["id"], status="active", accepted_at=now()
        )
        session.add(player)
        session.flush()
        session.add(
            PlayerQuestObjective(
                player_quest_id=player.id,
                objective_id=quest["objectives"][0]["id"],
                current_count=1,
                completed_at=now(),
            )
        )
        state = {
            **initial_state(),
            "stage": "mini-game",
            "seen": ["services"],
            "attempts": index + 2,
            "code": f"draft {index}",
            "hints": index,
        }
        saved[quest["id"]] = state
        session.add(
            QuestEvent(
                user_id=1,
                request_id=str(uuid4()),
                event_type="minigame_action",
                target_key=f"quest:{quest['id']}",
                payload={"action": "legacy-save", "payload": {}},
                result={"state": state, "awards": []},
            )
        )
    session.commit()
    generator.close()

    for quest in backend:
        # Retrying an old acceptance must not choose a winner or abandon its sibling.
        accepted = games.post(f"/quests/{quest['id']}/accept", headers=headers())
        assert accepted.status_code == 200
        assert accepted.json()["gameplay"]["state"] == saved[quest["id"]]
        tracked = games.put(
            "/quests/tracked", headers=headers(), json={"quest_id": quest["id"]}
        )
        assert tracked.status_code == 200
        fresh = games.get("/quests", headers=headers()).json()
        for original in backend:
            current = next(q for q in fresh if q["id"] == original["id"])
            assert current["status"] == "active"
            assert current["gameplay"]["state"] == saved[current["id"]]
            assert current["objectives"][0]["completed"]
            assert current["tracked"] == (current["id"] == quest["id"])
