# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The activity framework (docs/architecture/activity-framework-design.md; its plan for F2:
activity-framework-plan-f2.md): the core and the contract its kinds implement. So far, packages 1 to
5 of F2 - the contract, API 0 (kind.py, options.py), what kinds of a text checked against a seed share
(code.py), the registry of the installed kinds (registry.py) and the kit that checks one (kit.py); today's
four kinds are classes of the contract (kinds/); and the core: a game's steps and their phases
(phases.py), its entries (entries.py), their checks (checks.py), what they are reduced to - groups, the
crowd graph, a tally (reduce.py) -, the pictures the windows draw (views.py), the lecturer's acts and
their undo (moderation.py), and the storage - the tables, the writer that commits every 50 ms, what a
restart reads back, the move of F1's rows (store.py). Nothing of the server uses the core yet: F1's
activity type (server/activity.py) runs the lectures until the core replaces it.

    from texstage.activities import Kind, Built, Prepared, Check, Entry, Step, Message, fixed    # what a kind is written with
    from texstage.activities.options import File, Words, Int, Flag, Choice                    # ... and its options' types
"""
from texstage.activities.kind import (
    Built,
    Check,
    Entry,
    Kind,
    Message,
    Prepared,
    Step,
    Unbuildable,
    Unfit,
    fixed,
)

__all__ = ["Built", "Check", "Entry", "Kind", "Message", "Prepared", "Step", "Unbuildable", "Unfit", "fixed"]
