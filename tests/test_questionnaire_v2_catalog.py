from collections import defaultdict

from app.questionnaire_catalog_v2 import QUESTIONS_V2
from app.questionnaire_interpretation_v2 import interpret


def test_catalogue_formats_order_and_context_coverage():
    assert [q["id"] for q in QUESTIONS_V2] == [f"V2Q{i:02}" for i in range(1, 25)]
    assert [q["format"] for q in QUESTIONS_V2] == ["bipolar"] * 14 + ["choice"] * 6 + [
        "scale"
    ] * 4
    coverage = defaultdict(set)
    for q in QUESTIONS_V2:
        options = q.get("alternatives", q.get("options", [q]))
        for option in options:
            for signal in option["signals"]:
                coverage[signal].add(q["id"])
    assert {key: len(coverage[key]) for key in "BFDR"} == {
        "B": 6,
        "F": 8,
        "D": 7,
        "R": 8,
    }


def test_relative_center_neither_and_choice_are_separate():
    result = interpret(
        {
            "V2Q02": {"status": "answered", "value": 0},
            "V2Q03": {"status": "neither", "value": None},
            "V2Q20": {"status": "answered", "value": ["menu", "test"]},
            "V2Q21": {"status": "answered", "value": 5},
        }
    )
    assert not result["comparative"]
    assert result["neither"]["D"] == ["V2Q03"]
    assert result["choices"]["F"] == ["V2Q20"]
    assert result["absolute"]["V2Q21"]["value"] == 5


def test_mirroring_alternatives_and_value_preserves_meaning():
    q = QUESTIONS_V2[1]
    mirrored = {**q, "alternatives": list(reversed(q["alternatives"]))}
    original = interpret({q["id"]: {"status": "answered", "value": -2}}, [q])
    reverse = interpret({q["id"]: {"status": "answered", "value": 2}}, [mirrored])
    assert original == reverse
