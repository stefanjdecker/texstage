# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Experimental API 1: JSON values cross the worker boundary, never host objects.

Factories return PluginV1. Hooks receive JSON dictionaries and return these value
types (or their JSON equivalents). State hooks must be deterministic and must not
perform I/O; timestamps and authenticated identities are supplied by the host.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol
import hashlib
import json

API_VERSION = 1
SURFACES = ("presenter-overlay", "presenter-controls", "projector-overlay", "participant-input")
ROLES = ("presenter", "projector", "participant")


def evaluation_correlation(actor: str, request_id: str, slot: str) -> str:
    """Stable job correlation for one authenticated command's named effect.

    Receipts scope request IDs by actor; job correlations scope them by item and
    epoch. Including actor and slot prevents two participants or two effects
    from accidentally sharing a logical job. Reuse the original request on retry.
    """
    if any(not isinstance(x, str) or not x or len(x) > 256 for x in (actor, request_id, slot)):
        raise ValueError("correlation components must be nonempty bounded strings")
    raw = json.dumps([actor, request_id, slot], ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class PreparedItem:
    public: dict = field(default_factory=dict)
    private: dict = field(default_factory=dict)
    assets: dict = field(default_factory=dict)
    evaluations: dict = field(default_factory=dict)
    diagnostics: list = field(default_factory=list)


@dataclass(frozen=True)
class PreparedAuthoring:
    """One source's live data and trusted static TeX, prepared before compilation."""
    prepared: PreparedItem
    fragments: dict
    format: int = 1


def latex_escape(text: str) -> str:
    """Escape plain exercise text for a TeX fragment (not a path or TeX program)."""
    if not isinstance(text, str):
        raise TypeError("LaTeX text must be a string")
    escapes = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
               "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
               "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(c, c) for c in text)


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
class PutRecord:
    """Replace one bounded, private item record atomically with the transition."""
    key: str
    value: Any
    kind: str = field(default="put-record", init=False)


@dataclass(frozen=True)
class SaveActor:
    """Replace the authenticated event actor's record in the host transaction."""
    value: Any
    summary: dict
    kind: str = field(default="save-actor", init=False)


@dataclass(frozen=True)
class SetCredit:
    """Replace this event actor's credit (0–1000), or clear it with None."""
    credit: int | None
    kind: str = field(default="set-credit", init=False)


@dataclass(frozen=True)
class SetPointsOpen:
    """Open/resume or pause quiz-v1 scoring time using the host clock."""
    open: bool
    kind: str = field(default="points-open", init=False)


@dataclass(frozen=True)
class PublishPoints:
    """Presenter-only publication of this activity's current and late credits."""
    kind: str = field(default="publish-points", init=False)


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
    authoring_hooks: Mapping[str, Any] = field(default_factory=dict)


def json_value(value):
    """Convert SDK value types without exposing their Python representation."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
