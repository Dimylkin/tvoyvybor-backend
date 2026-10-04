"""Server-side validation strategies for published task kinds."""

from collections.abc import Mapping
from typing import Protocol


class UnsupportedTaskKindError(ValueError):
    pass


class InvalidTaskConfigError(ValueError):
    pass


class TaskStrategy(Protocol):
    def validate(self, answer: str, config: Mapping[str, object]) -> bool: ...


class ChoiceTaskStrategy:
    """Compare one selected option to the configured correct option."""

    def validate(self, answer: str, config: Mapping[str, object]) -> bool:
        correct = config.get("correct")
        if not isinstance(correct, str) or not correct:
            raise InvalidTaskConfigError(
                "Choice task requires a non-empty correct option"
            )
        return answer == correct


def strategy_for(kind: str) -> TaskStrategy:
    """Create a validator for one supported task kind."""
    if kind == "choice":
        return ChoiceTaskStrategy()
    raise UnsupportedTaskKindError(f"Unsupported task kind: {kind}")
