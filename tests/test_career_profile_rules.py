from app.career_profile_rules import practice


def observations(scores):
    kinds = (("diagnosis", "code"), ("responsive", "ux"), ("data", "interview"))
    actions = (
        ("investigation", "coding"),
        ("interface", "interface"),
        ("data", "requirements"),
    )
    result = []
    for score, pair, action in zip(scores, kinds, actions, strict=True):
        for kind, code in zip(pair, action, strict=True):
            for i in range(2 if kind == pair[0] else 1):
                result.append(
                    {
                        "kind": kind,
                        "code": code if i == 0 else "verification",
                        "rating": score,
                    }
                )
    return result


def test_all_three_directions_can_lead_and_no_cross_context_leak():
    directions, leaders, conclusion = practice(observations([5, 5, 5]), set())
    assert leaders == ["backend", "frontend", "analytics"]
    assert conclusion == "leaders"
    assert [d["score"] for d in directions] == [5, 5, 5]
    directions, leaders, conclusion = practice(
        [{"kind": "code", "code": "coding", "rating": 5}], {"code"}
    )
    assert [d["score"] for d in directions] == [5, None, None]
    assert leaders == [] and conclusion == "local"


def test_low_and_close_scores_use_displayed_rounding():
    _, leaders, conclusion = practice(observations([2, 2, 2]), set())
    assert not leaders and conclusion == "weak"
    _, leaders, _ = practice(observations([4, 4, 4]), set())
    assert len(leaders) == 3


def test_one_direction_leads_without_using_other_directions_actions():
    directions, leaders, _ = practice(observations([5, 2, 2]), set())
    assert [d["score"] for d in directions] == [5, 2, 2]
    assert leaders == ["backend"]
    directions, leaders, _ = practice(observations([2, 5, 2]), set())
    assert [d["score"] for d in directions] == [2, 5, 2]
    assert leaders == ["frontend"]


def test_coverage_needs_three_values_and_main_actions():
    items = [
        {"kind": "diagnosis", "code": "investigation", "rating": 5},
        {"kind": "code", "code": "coding", "rating": 5},
    ]
    directions, _, conclusion = practice(items, {"diagnosis", "code"})
    assert directions[0]["rated"] == 2
    assert not directions[0]["sufficient"]
    assert conclusion == "local"


def test_inclusive_leader_thresholds_use_rounded_display_values():
    items = observations([4, 4, 3])
    items = [item for item in items if item["kind"] not in ("diagnosis", "code")]
    items += [
        {"kind": "diagnosis", "code": "investigation", "rating": 5},
        {"kind": "diagnosis", "code": "coding", "rating": 4},
        {"kind": "diagnosis", "code": "verification", "rating": 4},
        {"kind": "code", "code": "coding", "rating": 5},
        {"kind": "code", "code": "verification", "rating": 4},
    ]
    directions, leaders, _ = practice(items, set())
    assert directions[0]["score"] == 4.4
    assert leaders == ["backend", "frontend"]


def test_trials_have_equal_weight_and_analytics_keeps_branches():
    items = [
        {"kind": "data", "code": "data", "rating": 5},
        {"kind": "data", "code": "verification", "rating": 5},
        {"kind": "interview", "code": "requirements", "rating": 2},
    ]
    directions, _, _ = practice(items, {"data", "interview"})
    analytics = directions[2]
    assert analytics["score"] == 3.5
    assert [t["score"] for t in analytics["trials"]] == [5, 2]
    assert analytics["sufficient"] and analytics["uneven"]
