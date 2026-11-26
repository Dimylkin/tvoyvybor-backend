from copy import deepcopy
from uuid import uuid4

from test_quest_api import client as client
from test_quest_api import headers

from app.questionnaire_catalog_v2 import QUESTIONS_V2
from app.questionnaire_catalog_v3 import QUESTIONS_V3
from app.questionnaire_interpretation_v2 import interpret


def test_v3_keeps_semantic_mapping_but_has_new_contextual_questions():
    assert len(QUESTIONS_V3) == len(QUESTIONS_V2) == 24
    for old, new in zip(QUESTIONS_V2, QUESTIONS_V3, strict=True):
        assert new["id"] == old["id"].replace("V2", "V3")
        assert new["format"] == old["format"]
        assert len(new["text"]) > 60 and "?" in new["text"]
        for key in ("signals", "max_choices"):
            assert new.get(key) == old.get(key)
        for key in ("alternatives", "options"):
            assert [(x["id"], x["signals"]) for x in new.get(key, [])] == [
                (x["id"], x["signals"]) for x in old.get(key, [])
            ]
    original = deepcopy(QUESTIONS_V2)
    assert QUESTIONS_V2 == original


def test_v3_interpretation_matches_v2_for_equivalent_answers():
    answers = {
        "V2Q02": {"status": "answered", "value": -2},
        "V2Q15": {"status": "answered", "value": ["screen"]},
        "V2Q21": {"status": "answered", "value": 5},
    }
    v3 = {key.replace("V2", "V3"): value for key, value in answers.items()}
    old = interpret(answers, QUESTIONS_V2)
    new = interpret(v3, QUESTIONS_V3)
    assert old["comparative"]["B"]["mean"] == new["comparative"]["B"]["mean"]
    assert old["choices"]["F"] == ["V2Q15"] and new["choices"]["F"] == ["V3Q15"]
    assert old["absolute"]["V2Q21"]["value"] == new["absolute"]["V3Q21"]["value"]


def test_v3_rejects_removed_answers_and_preserves_old_drafts(client):
    attempt = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": str(uuid4()), "catalog_version": 3},
    ).json()
    assert attempt["current_question_id"] == "V3Q01"
    assert (
        client.get("/questionnaire/state?version=2", headers=headers()).status_code
        == 409
    )
    url = f"/questionnaire/attempts/{attempt['id']}/progress"

    def send(answer):
        return client.put(
            url,
            headers=headers(),
            json={
                "request_id": str(uuid4()),
                "expected_revision": 0,
                "current_question_id": "V3Q02",
                "answer": {"question_id": "V3Q01", "answer": answer},
            },
        )

    assert send({"status": "neither", "value": None}).status_code == 422
    assert send({"status": "unsure", "value": None}).status_code == 422
    assert (
        send({"status": "answered", "value": 0}).json()["answers"]["V3Q01"]["value"]
        == 0
    )
