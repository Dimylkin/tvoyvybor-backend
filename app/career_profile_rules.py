"""Version 3 rules for independent questionnaire and practice observations."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

DIRECTIONS = {
    "backend": (
        "Backend",
        {"diagnosis": {"investigation", "coding"}, "code": {"coding"}},
    ),
    "frontend": ("Frontend", {"responsive": {"interface"}, "ux": {"interface"}}),
    "analytics": (
        "Аналитика",
        {"data": {"data", "investigation"}, "interview": {"requirements", "users"}},
    ),
}
CONTEXTS = {"backend": ("B",), "frontend": ("F",), "analytics": ("D", "R")}


def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def survey_contexts(result, interpretation_version=2):
    if not result:
        return {}
    contexts = {}
    for context in "BFDR":
        comparative = result["comparative"].get(context, {})
        positives = {
            x["question_id"] for x in comparative.get("evidence", []) if x["value"] > 0
        }
        positives.update(result["choices"].get(context, []))
        negatives = {
            x["question_id"] for x in comparative.get("evidence", []) if x["value"] < 0
        }
        neither = set(result["neither"].get(context, []))
        high = {
            qid
            for qid, item in result["absolute"].items()
            if context in item["signals"] and item["value"] >= 4
        }
        low = {
            qid
            for qid, item in result["absolute"].items()
            if context in item["signals"] and item["value"] <= 2
        }
        positive = len(positives) >= 2 or bool(positives and high - positives)
        weak = len(neither) >= 2 or bool(neither and low - neither)
        contradictory = (
            interpretation_version >= 3
            and positive
            and (bool(low) or len(negatives) >= 2)
        )
        label = (
            "mixed"
            if positive and (weak or contradictory)
            else "positive"
            if positive
            else "weak"
            if weak
            else "relative"
            if len(negatives) >= 2
            else "insufficient"
        )
        contexts[context] = {
            "label": label,
            "positive_questions": sorted(positives),
            "negative_questions": sorted(negatives),
            "neither_questions": sorted(neither),
            "absolute_questions": sorted(high | low),
        }
    return contexts


def practice(observations, attempted_kinds, survey=None):
    """Aggregate one latest confirmed observation per action with equal quest weight."""
    survey = survey or {}
    by_kind = defaultdict(list)
    for observation in observations:
        if type(observation["rating"]) is int and 1 <= observation["rating"] <= 5:
            by_kind[observation["kind"]].append(observation)
    directions = []
    for code, (title, kinds) in DIRECTIONS.items():
        groups = [by_kind[kind] for kind in kinds if by_kind[kind]]
        values = [
            rounded(sum(o["rating"] for o in group) / len(group)) for group in groups
        ]
        raw_values = [sum(o["rating"] for o in group) / len(group) for group in groups]
        score = rounded(sum(raw_values) / len(raw_values)) if raw_values else None
        qualified = (
            len(groups) == 2
            and sum(map(len, groups)) >= 3
            and all(
                any(o["code"] in required for o in by_kind[kind])
                for kind, required in kinds.items()
            )
        )
        all_values = [o["rating"] for group in groups for o in group]
        directions.append(
            {
                "code": code,
                "title": title,
                "score": score,
                "traits": [],
                "coverage": len(groups) / 2,
                "attempted": sum(kind in attempted_kinds for kind in kinds),
                "rated": len(groups),
                "action_count": len(all_values),
                "sufficient": qualified,
                "questionnaire": {
                    context: survey.get(context, {"label": "insufficient"})
                    for context in CONTEXTS[code]
                },
                "trials": [
                    {
                        "kind": kind,
                        "score": rounded(
                            sum(o["rating"] for o in by_kind[kind]) / len(by_kind[kind])
                        )
                        if by_kind[kind]
                        else None,
                        "observations": by_kind[kind],
                    }
                    for kind in kinds
                ],
                "uneven": bool(all_values and max(all_values) - min(all_values) >= 1.5)
                or bool(values and max(values) - min(values) >= 1.5),
            }
        )
    comparable = all(d["sufficient"] for d in directions)
    scores = [d["score"] for d in directions if d["score"] is not None]
    maximum = max(scores, default=None)
    leaders = (
        [
            d["code"]
            for d in directions
            if comparable
            and d["score"] is not None
            and d["score"] >= 3.5
            and rounded(maximum - d["score"]) <= 0.4
        ]
        if maximum is not None
        else []
    )
    conclusion = (
        "leaders"
        if leaders
        else "weak"
        if comparable and maximum is not None and maximum <= 2.5
        else "no_clear_direction"
        if comparable
        else "local"
        if scores
        else "survey"
        if any(v["label"] != "insufficient" for v in survey.values())
        else "empty"
    )
    return directions, leaders, conclusion
