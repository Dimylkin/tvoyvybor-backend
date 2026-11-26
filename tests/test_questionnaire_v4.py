from uuid import uuid4

import pytest
from test_quest_api import client as client
from test_quest_api import headers

from app.career_profile_rules import practice, survey_contexts
from app.questionnaire_catalog_v4 import QUESTIONS_V4
from app.questionnaire_interpretation_v2 import interpret


def answered(value):
    return {"status": "answered", "value": value}


def signals(answers):
    return interpret(answers, QUESTIONS_V4)


def test_catalogue_is_stable_interleaved_and_semantically_correct():
    assert len(QUESTIONS_V4) == len({q["id"] for q in QUESTIONS_V4}) == 24
    by_id = {q["id"]: q for q in QUESTIONS_V4}
    assert set(by_id) == {f"V4Q{i:02}" for i in range(1, 25)}
    assert QUESTIONS_V4[0]["id"] == "V4Q01"
    assert all(
        QUESTIONS_V4[i]["format"] != QUESTIONS_V4[i + 1]["format"] for i in range(18)
    )
    assert by_id["V4Q07"]["alternatives"][0]["signals"] == ["independent"]
    assert by_id["V4Q07"]["alternatives"][1]["signals"] == ["collaboration"]
    assert "R" not in by_id["V4Q15"]["options"][3]["signals"]
    assert len(by_id["V4Q24"]["text"]) > 300


@pytest.mark.parametrize(
    ("responses", "context"),
    [
        ({"V4Q02": answered(-2), "V4Q09": answered(-2), "V4Q21": answered(5)}, "B"),
        ({"V4Q02": answered(2), "V4Q05": answered(-2), "V4Q22": answered(5)}, "F"),
        ({"V4Q03": answered(-2), "V4Q11": answered(2), "V4Q23": answered(5)}, "D"),
        ({"V4Q09": answered(2), "V4Q10": answered(-2), "V4Q24": answered(5)}, "R"),
    ],
)
def test_directional_interest_is_preliminary_and_independent(responses, context):
    contexts = survey_contexts(signals(responses))
    assert contexts[context]["label"] == "positive"
    directions, leaders, conclusion = practice([], set(), contexts)
    assert conclusion == "survey" and not leaders
    assert all(d["score"] is None for d in directions)
    if context == "R":
        assert contexts["D"]["label"] != "positive"


def test_work_approaches_and_testing_do_not_create_unrelated_directions():
    independent = signals({"V4Q06": answered(-2), "V4Q07": answered(-2)})
    collaborative = signals({"V4Q06": answered(2), "V4Q07": answered(2)})
    assert independent["comparative"]["independent"]["positive"] == 2
    assert collaborative["comparative"]["collaboration"]["positive"] == 2
    assert all(
        x["label"] == "insufficient" for x in survey_contexts(independent).values()
    )
    assert all(
        x["label"] == "insufficient" for x in survey_contexts(collaborative).values()
    )
    qa = signals({"V4Q04": answered(2), "V4Q16": answered(["option3"])})
    assert qa["comparative"]["testing"]["positive"] == 1
    assert qa["choices"]["testing"] == ["V4Q16"]
    assert qa["choices"]["software"] == ["V4Q16"]


def test_centre_and_skips_never_create_directional_scores():
    result = signals(
        {
            q["id"]: answered(0)
            if q["format"] == "bipolar"
            else {"status": "skipped", "value": None}
            for q in QUESTIONS_V4
        }
    )
    assert result == {"comparative": {}, "neither": {}, "choices": {}, "absolute": {}}
    assert all(x["label"] == "insufficient" for x in survey_contexts(result).values())


def test_low_absolute_rating_and_positive_preferences_are_mixed_in_v4():
    result = signals(
        {"V4Q02": answered(-2), "V4Q09": answered(-2), "V4Q21": answered(1)}
    )
    assert survey_contexts(result, 3)["B"]["label"] == "mixed"
    assert survey_contexts(result, 2)["B"]["label"] == "positive"


def test_api_latest_version_and_old_client_protection(client):
    latest = client.get("/questionnaire/capabilities", headers=headers()).json()[
        "latest_catalog_version"
    ]
    assert latest == 4
    result = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": str(uuid4()), "catalog_version": latest},
    )
    assert result.status_code == 201
    assert result.json()["current_question_id"] == "V4Q01"
    assert result.json()["interpretation_version"] == 3
    assert (
        client.get("/questionnaire/state?version=3", headers=headers()).status_code
        == 409
    )
    assert (
        client.get("/questionnaire/catalog?version=3", headers=headers()).json()[
            "questions"
        ][0]["id"]
        == "V3Q01"
    )


def test_completed_v4_is_interpreted_and_retake_keeps_latest_result(client):
    def request():
        return str(uuid4())

    attempt = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": request(), "catalog_version": 4},
    ).json()
    base = f"/questionnaire/attempts/{attempt['id']}"
    for revision, question in enumerate(QUESTIONS_V4):
        qid = question["id"]
        response = (
            answered(-2)
            if qid in ("V4Q02", "V4Q09")
            else answered(5)
            if qid == "V4Q21"
            else {"status": "skipped"}
        )
        saved = client.put(
            base + "/progress",
            headers=headers(),
            json={
                "request_id": request(),
                "expected_revision": revision,
                "current_question_id": qid,
                "answer": {"question_id": qid, "answer": response},
            },
        )
        assert saved.status_code == 200
    assert (
        client.post(
            base + "/complete",
            headers=headers(),
            json={"request_id": request(), "expected_revision": 24},
        ).status_code
        == 200
    )
    result = client.get(base + "/results", headers=headers()).json()
    assert (
        result["catalog_version"] == 4 and result["summary"]["B"]["label"] == "positive"
    )
    profile = client.get("/activity-profile", headers=headers()).json()[
        "career_profile"
    ]
    assert profile["survey_contexts"]["B"]["label"] == "positive"
    assert (
        next(d for d in profile["directions"] if d["code"] == "backend")["score"]
        is None
    )
    assert any(
        card["code"] == "backend" and card["basis"] == "questionnaire"
        for card in profile["careers"]
    )
    retake = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": request(), "retake": True, "catalog_version": 4},
    )
    assert retake.status_code == 201 and retake.json()["current_question_id"] == "V4Q01"
    assert (
        client.get(
            "/questionnaire/state?version=4&history=true", headers=headers()
        ).json()["last_completed"]["id"]
        == attempt["id"]
    )


def test_qa_evidence_can_produce_an_adjacent_recommendation(client):
    attempt = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": str(uuid4()), "catalog_version": 4},
    ).json()
    base = f"/questionnaire/attempts/{attempt['id']}"
    for revision, question in enumerate(QUESTIONS_V4):
        qid = question["id"]
        value = (
            answered(2)
            if qid == "V4Q04"
            else answered(["option3"])
            if qid == "V4Q16"
            else {"status": "skipped"}
        )
        response = client.put(
            base + "/progress",
            headers=headers(),
            json={
                "request_id": str(uuid4()),
                "expected_revision": revision,
                "current_question_id": qid,
                "answer": {"question_id": qid, "answer": value},
            },
        )
        assert response.status_code == 200
    assert (
        client.post(
            base + "/complete",
            headers=headers(),
            json={"request_id": str(uuid4()), "expected_revision": 24},
        ).status_code
        == 200
    )
    profile = client.get("/activity-profile", headers=headers()).json()[
        "career_profile"
    ]
    qa = next(card for card in profile["careers"] if card["code"] == "qa")
    assert qa["represented"] is False and qa["score"] is None
    assert set(qa["source_ids"]) == {"q:V4Q04", "q:V4Q16"}
    assert profile["leaders"] == []
