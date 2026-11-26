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
        json={"request_id": request_id(), "retake": True, "catalog_version": 2},
    )
    assert retake.status_code == 201
    state = client.get(
        "/questionnaire/state?version=2&history=true", headers=headers()
    ).json()
    assert state["current"]["id"] == retake.json()["id"]
    assert state["current"]["catalog_version"] == 2
    assert state["last_completed"]["id"] == attempt_id
    assert state["history"][0]["catalog_version"] == 1
    assert client.get(
        f"/questionnaire/attempts/{attempt_id}/results", headers=headers()
    ).json()["interests"] == {"code": 5}


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


def test_v2_attempt_validation_replay_and_legacy_client(client):
    catalogue = client.get("/questionnaire/catalog?version=2", headers=headers()).json()
    assert len(catalogue["questions"]) == 24
    assert "signals" not in catalogue["questions"][0]["alternatives"][0]
    attempt = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": request_id(), "catalog_version": 2},
    ).json()
    assert attempt["current_question_id"] == "V2Q01"
    assert client.get("/questionnaire/state", headers=headers()).status_code == 409
    assert (
        client.get("/questionnaire/state?version=2", headers=headers()).status_code
        == 200
    )
    url = f"/questionnaire/attempts/{attempt['id']}/progress"
    payload = {
        "request_id": request_id(),
        "expected_revision": 0,
        "current_question_id": "V2Q02",
        "answer": {
            "question_id": "V2Q01",
            "answer": {"status": "answered", "value": 0},
        },
    }
    saved = client.put(url, headers=headers(), json=payload)
    assert saved.status_code == 200
    assert client.put(url, headers=headers(), json=payload).json() == saved.json()
    invalid = {
        **payload,
        "request_id": request_id(),
        "expected_revision": 1,
        "answer": {
            "question_id": "V2Q02",
            "answer": {"status": "answered", "value": True},
        },
    }
    assert client.put(url, headers=headers(), json=invalid).status_code == 422
    assert client.put(url, headers=headers(2), json=invalid).status_code == 404
    assert (
        client.get("/questionnaire/catalog?version=4", headers=headers()).status_code
        == 404
    )


def test_v2_complete_history_and_survey_profile(client):
    attempt = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": request_id(), "catalog_version": 2},
    ).json()
    base = f"/questionnaire/attempts/{attempt['id']}"
    for i in range(1, 25):
        qid = f"V2Q{i:02}"
        answer = (
            {"status": "answered", "value": -2}
            if i == 2
            else (
                {"status": "answered", "value": 5} if i == 21 else {"status": "skipped"}
            )
        )
        response = client.put(
            base + "/progress",
            headers=headers(),
            json={
                "request_id": request_id(),
                "expected_revision": i - 1,
                "current_question_id": qid,
                "answer": {"question_id": qid, "answer": answer},
            },
        )
        assert response.status_code == 200, response.text
    assert (
        client.post(
            base + "/complete",
            headers=headers(),
            json={"request_id": request_id(), "expected_revision": 24},
        ).status_code
        == 200
    )
    result = client.get(base + "/results", headers=headers()).json()
    assert result["structured_results"]["absolute"]["V2Q21"]["value"] == 5
    assert result["structured_results"]["comparative"]["B"]["positive"] == 1
    state = client.get(
        "/questionnaire/state?version=2&history=true", headers=headers()
    ).json()
    assert state["history"][0]["id"] == attempt["id"]
    profile = client.get("/activity-profile", headers=headers()).json()[
        "career_profile"
    ]
    assert profile["survey_contexts"]["B"]["label"] == "positive"
    assert profile["leaders"] == []
    assert profile["directions"][0]["score"] is None


def test_v2_answer_formats_validate_against_attempt_catalogue(client):
    attempt = client.post(
        "/questionnaire/attempts",
        headers=headers(),
        json={"request_id": request_id(), "catalog_version": 2},
    ).json()
    url = f"/questionnaire/attempts/{attempt['id']}/progress"

    def send(qid, answer, revision=0):
        return client.put(
            url,
            headers=headers(),
            json={
                "request_id": request_id(),
                "expected_revision": revision,
                "current_question_id": qid,
                "answer": {"question_id": qid, "answer": answer},
            },
        )

    assert send("V2Q01", {"status": "answered", "value": 3}).status_code == 422
    assert send("V2Q15", {"status": "neither", "value": None}).status_code == 422
    assert (
        send("V2Q15", {"status": "answered", "value": ["screen", "screen"]}).status_code
        == 422
    )
    assert (
        send(
            "V2Q16", {"status": "answered", "value": ["create", "test", "organize"]}
        ).status_code
        == 422
    )
    assert send("V2Q21", {"status": "answered", "value": 0}).status_code == 422
    assert send("Q01", {"status": "answered", "value": 3}).status_code == 422
    assert send("V2Q01", {"status": "neither", "value": None}).status_code == 200
    assert (
        send("V2Q15", {"status": "answered", "value": ["screen"]}, 1).status_code == 200
    )
    assert (
        send(
            "V2Q16", {"status": "answered", "value": ["create", "test"]}, 2
        ).status_code
        == 200
    )
    assert send("V2Q21", {"status": "answered", "value": 5}, 3).status_code == 200
