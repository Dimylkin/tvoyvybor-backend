"""Interpret v2 answers without converting relative preferences into ratings."""

from collections import defaultdict

from app.questionnaire_catalog_v2 import QUESTIONS_V2


def interpret(answers, questions=QUESTIONS_V2):
    comparative = defaultdict(list)
    neither = defaultdict(list)
    choices = defaultdict(list)
    absolute = {}
    for question in questions:
        answer = answers.get(question["id"])
        if not answer:
            continue
        status = answer["status"]
        if question["format"] == "bipolar":
            left, right = question["alternatives"]
            left_signals, right_signals = set(left["signals"]), set(right["signals"])
            if status == "neither":
                for signal in left_signals | right_signals:
                    neither[signal].append(question["id"])
            elif status == "answered" and answer["value"]:
                value = answer["value"] / 2
                for signal in left_signals - right_signals:
                    comparative[signal].append(
                        {"question_id": question["id"], "value": -value}
                    )
                for signal in right_signals - left_signals:
                    comparative[signal].append(
                        {"question_id": question["id"], "value": value}
                    )
        elif status == "answered" and question["format"] == "choice":
            selected = set(answer["value"])
            traits = {
                signal
                for option in question["options"]
                if option["id"] in selected
                for signal in option["signals"]
            }
            for signal in traits:
                choices[signal].append(question["id"])
        elif status == "answered" and question["format"] == "scale":
            absolute[question["id"]] = {
                "value": answer["value"],
                "signals": question["signals"],
            }
    return {
        "comparative": {
            key: {
                "mean": sum(x["value"] for x in values) / len(values),
                "positive": sum(x["value"] > 0 for x in values),
                "negative": sum(x["value"] < 0 for x in values),
                "evidence": values,
            }
            for key, values in comparative.items()
        },
        "neither": dict(neither),
        "choices": dict(choices),
        "absolute": absolute,
    }
