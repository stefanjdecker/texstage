# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The activity framework (docs/architecture/activity-framework-design.md; its plan for F2:
activity-framework-plan-f2.md): the core and the contract its kinds implement. So far, packages 1 and
2 of F2 - the contract, API 0 (kind.py, options.py), what kinds of a text checked against a seed share
(code.py), the registry of the installed kinds (registry.py) and the kit that checks one (kit.py); today's
four kinds are classes of the contract (kinds/). Nothing of the server uses it yet: F1's
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
