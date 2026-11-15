from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class GameplayView:
    kind: str
    state: dict[str, Any]


@dataclass(frozen=True)
class ObjectiveView:
    id: int
    title: str
    description: str
    objective_type: str
    required_count: int
    current_count: int
    completed: bool
    is_required: bool


@dataclass(frozen=True)
class QuestView:
    id: int
    slug: str
    title: str
    description: str
    category: str
    location_slug: str
    giver_npc_id: str
    status: Literal["locked", "available", "active", "abandoned", "completed"]
    accepted_at: datetime | None
    completed_at: datetime | None
    tracked: bool
    objectives: list[ObjectiveView]
    gameplay: GameplayView | None


@dataclass(frozen=True)
class TerminalResult:
    log: str
    port: int


@dataclass(frozen=True)
class ObjectiveChangeResult:
    quest_id: int
    objective_id: int
    objective_completed: bool
    quest_completed: bool


@dataclass(frozen=True)
class InteractionResult:
    accepted: bool
    changes: list[ObjectiveChangeResult]


@dataclass(frozen=True)
class AwardResult:
    slug: str
    title: str
    description: str


@dataclass(frozen=True)
class GameActionResult:
    state: dict[str, Any]
    awards: list[AwardResult]
