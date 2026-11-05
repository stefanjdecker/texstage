# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Experimental API 1: JSON values cross the worker boundary, never host objects.

Factories return PluginV1. Hooks receive JSON dictionaries and return these value
types (or their JSON equivalents). State hooks must be deterministic and must not
perform I/O; timestamps and authenticated identities are supplied by the host.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol

API_VERSION = 1
SURFACES = ("presenter-overlay", "presenter-controls", "projector-overlay", "participant-input")
ROLES = ("presenter", "projector", "participant")


@dataclass(frozen=True)
class PreparedItem:
    public: dict = field(default_factory=dict)
    private: dict = field(default_factory=dict)
    assets: dict = field(default_factory=dict)
    evaluations: dict = field(default_factory=dict)
    diagnostics: list = field(default_factory=list)


@dataclass(frozen=True)
class Evaluate:
    binding: str
    correlation_id: str
    text: str
    kind: str = field(default="evaluate", init=False)


@dataclass(frozen=True)
class CancelEvaluation:
    correlation_id: str
    kind: str = field(default="cancel-evaluation", init=False)


@dataclass(frozen=True)
class Transition:
    state: Any
    effects: list = field(default_factory=list)


class StateHook(Protocol):
    def initial_state(self, item: dict, ctx: dict) -> Any: ...
    def transition(self, state: Any, event: dict, ctx: dict) -> Transition: ...
    def view(self, state: Any, audience: dict, ctx: dict) -> Any: ...


@dataclass(frozen=True)
class PluginV1:
    build_hooks: Mapping[str, Any] = field(default_factory=dict)
    state_hooks: Mapping[str, StateHook] = field(default_factory=dict)


def json_value(value):
    """Convert SDK value types without exposing their Python representation."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
