from uuid import uuid4

from test_quest_api import client as client
from test_quest_api import headers


def request_id():
    return str(uuid4())


def test_questionnaire_resume_conflicts_and_retake(client):
    assert client.get("/questionnaire/state").status_code == 401
    catalog = client.get("/questionnaire/catalog", headers=headers()).json()
    questions = catalog["questions"]
    assert len(questions) == len({q["id"] for q in questions}) == 24
    start = client.post(
        "/questionnaire/attempts", headers=headers(), json={"request_id": request_id()}
    )
    assert start.status_code == 201
    attempt = start.json()
    attempt_id = attempt["id"]
    assert (
        client.get(
            f"/questionnaire/attempts/{attempt_id}/results", headers=headers(2)
        ).status_code
        == 404
    )
    url = f"/questionnaire/attempts/{attempt_id}/progress"
    key = request_id()
    payload = {
        "request_id": key,
        "expected_revision": 0,
        "current_question_id": "Q02",
        "answer": {"question_id": "Q01", "answer": {"status": "answered", "value": 5}},
    }
    saved = client.put(url, headers=headers(), json=payload)
    assert saved.status_code == 200
    assert client.put(url, headers=headers(), json=payload).json() == saved.json()
    assert (
        client.put(
            url, headers=headers(), json={**payload, "current_question_id": "Q03"}
        ).status_code
        == 409
    )
    assert (
        client.put(
            url, headers=headers(), json={**payload, "request_id": request_id()}
        ).status_code
        == 409
    )
    state = client.get("/questionnaire/state", headers=headers()).json()
    assert state["current"]["current_question_id"] == "Q02"
    assert state["current"]["answers"]["Q01"]["value"] == 5
    for i in range(2, 25):
        qid = f"Q{i:02}"
        result = client.put(
            url,
            headers=headers(),
            json={
                "request_id": request_id(),
                "expected_revision": i - 1,
                "current_question_id": qid,
                "answer": {"question_id": qid, "answer": {"status": "skipped"}},
            },
        )
        assert result.status_code == 200, result.text
    completed = client.post(
        f"/questionnaire/attempts/{attempt_id}/complete",
        headers=headers(),
        json={"request_id": request_id(), "expected_revision": 24},
    )
    assert completed.status_code == 200
    result = client.get(
        f"/questionnaire/attempts/{attempt_id}/results", headers=headers()
    ).json()
    assert result["interests"] == {"code": 5}
    assert (
        client.post(
            "/questionnaire/attempts",
            headers=headers(),
            json={"request_id": request_id()},
        ).status_code
        == 409
    )
    retake = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": request_id(), "retake": True},
    )
    assert retake.status_code == 201
    state = client.get("/questionnaire/state", headers=headers()).json()
    assert state["current"]["id"] == retake.json()["id"]
    assert state["last_completed"]["id"] == attempt_id


def test_invalid_and_incomplete_answers(client):
    attempt = client.post(
        "/questionnaire/attempts", headers=headers(), json={"request_id": request_id()}
    ).json()
    url = f"/questionnaire/attempts/{attempt['id']}"
    assert (
        client.post(
            url + "/complete",
            headers=headers(),
            json={"request_id": request_id(), "expected_revision": 0},
        ).status_code
        == 409
    )
    invalid = {
        "request_id": request_id(),
        "expected_revision": 0,
        "current_question_id": "Q01",
        "answer": {"question_id": "Q01", "answer": {"status": "answered", "value": 6}},
    }
    assert (
        client.put(url + "/progress", headers=headers(), json=invalid).status_code
        == 422
    )
    invalid["answer"] = {
        "question_id": "Q23",
        "answer": {"status": "answered", "value": ["edge", "edge"]},
    }
    assert (
        client.put(url + "/progress", headers=headers(), json=invalid).status_code
        == 422
    )


def test_reordered_choice_retry_is_same_operation(client):
    attempt = client.post(
        "/questionnaire/attempts", headers=headers(), json={"request_id": request_id()}
    ).json()
    url = f"/questionnaire/attempts/{attempt['id']}/progress"
    data = {
        "request_id": request_id(),
        "expected_revision": 0,
        "current_question_id": "Q24",
        "answer": {
            "question_id": "Q23",
            "answer": {"status": "answered", "value": ["edge", "notes"]},
        },
    }
    first = client.put(url, headers=headers(), json=data)
    data["answer"]["answer"]["value"].reverse()
    second = client.put(url, headers=headers(), json=data)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
