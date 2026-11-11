# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The activity framework (docs/architecture/activity-framework-design.md; its plan for F2:
activity-framework-plan-f2.md): the core and the contract its kinds implement. So far, package 1 of
F2 - a provisional contract (kind.py) and what kinds of a text checked against a seed share (code.py),
behind which today's four kinds stand as classes (kinds/). Nothing of the server uses it yet: F1's
activity type (server/activity.py) runs the lectures until the core replaces it.

    from texstage.activities import Kind, Built, Prepared, Check, Entry, Step     # what a kind is written with
"""
from texstage.activities.kind import Built, Check, Entry, Kind, Prepared, Step, Unbuildable, Unfit

__all__ = ["Built", "Check", "Entry", "Kind", "Prepared", "Step", "Unbuildable", "Unfit"]
