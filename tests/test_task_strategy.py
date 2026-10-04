import pytest

from app.task_strategy import (
    InvalidTaskConfigError,
    UnsupportedTaskKindError,
    strategy_for,
)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("GET", True), ("POST", False), ("get", False), ("", False)],
)
def test_choice_strategy_checks_exact_answer(answer: str, expected: bool) -> None:
    strategy = strategy_for("choice")
    assert strategy.validate(answer, {"correct": "GET"}) is expected


@pytest.mark.parametrize("config", [{}, {"correct": ""}, {"correct": 5}])
def test_choice_strategy_rejects_invalid_config(config: dict) -> None:
    with pytest.raises(InvalidTaskConfigError):
        strategy_for("choice").validate("GET", config)


def test_factory_rejects_unsupported_kind() -> None:
    with pytest.raises(UnsupportedTaskKindError):
        strategy_for("debug")
