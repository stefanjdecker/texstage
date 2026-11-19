# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A student's input sent again where all count (texstage/activities/entries.py; the review of 2026-11-19, A2
and D5): one whose check could not be made is that entry again - after the refusals that are not about the
input, taking no place and filling no step -, and two inputs are one with spaces around a field."""
from __future__ import annotations

import pytest

from texstage.activities import entries as entries_module
from texstage.activities.entries import Entries, Rules, alike
from texstage.activities.phases import ONE, Refused
from texstage.activities.store import StepRow

T = {"fields": [":a", ":knows", ":b"]}


class Saved:
    """What the entries hand to the writer, in order."""

    def __init__(self):
        self.rows: list = []

    def __call__(self, *rows):
        self.rows.extend(rows)


def opened(activity: str = "a", **step) -> StepRow:
    return StepRow("g1", activity, ONE, **{"phase": "open", **step})


def refused(code: str, call, *args, **kwargs) -> None:
    with pytest.raises(Refused) as caught:
        call(*args, **kwargs)
    assert caught.value.code == code, str(caught.value)


def test_an_input_that_could_not_be_checked_is_that_entry_again(monkeypatch):
    saved, failed = Saved(), set()
    es, st, rules = Entries("g1", saved), opened(), Rules("fields", 1, 1000, "all", 3)

    def enter(eid: str, sent: dict = T, now: int = 20_000, **more):
        return es.enter(st, rules, "p1", eid, sent, now=now, unchecked=lambda e: e.id in failed, **more)
    e = enter("entry-0001", now=10_000).entry
    refused("too-many", enter, "entry-0002", now=11_000)       # checked, or on its way: as before (the limit first)
    failed.add(e.id)
    refused("too-fast", enter, "entry-0002", now=10_500)       # what is not about the input comes first
    refused("blocked", enter, "entry-0002", blocked=True)
    st.phase = "paused"
    refused("paused", enter, "entry-0002")
    st.phase = "open"
    got = enter("entry-0002", {"fields": [" :a", ":knows ", ":b"]}, now=11_000)
    assert got == (e, False, []) and saved.rows == [e] and es.counts(st) == {"entries": 1, "students": 1}
    assert es.get("a", ONE, "entry-0002") is None and es.used(st, rules, "p1") == 1      # no place, no row
    refused("too-fast", enter, "entry-0003", now=11_500)       # the gap counts from it
    monkeypatch.setattr(entries_module, "PER_STEP", 1)
    assert es.hide(e) and enter("entry-0003", now=12_000).entry is e         # hidden too; the step full: no matter
    saved.rows.clear()
    latest = Rules("fields", 3, 0, "latest", 3)                # where the latest counts, it is a new entry
    monkeypatch.setattr(entries_module, "PER_STEP", 10)
    q = es.enter(opened(activity="q"), latest, "p1", "entry-0004", T, now=1, unchecked=lambda e: True).entry
    again = es.enter(opened(activity="q"), latest, "p1", "entry-0005", T, now=2, unchecked=lambda e: True)
    assert again.new and again.replaced == [q] and saved.rows == [q, q, again.entry]


def test_two_inputs_are_one_with_spaces_around_a_field_and_kept_as_sent():
    es, st, rules = Entries("g1"), opened(), Rules("fields", 5, 0, "all", 2)
    e = es.enter(st, rules, "p1", "entry-0001", {"fields": ["\u00a0:Ada ", ":Bob\t"]}, now=1).entry
    refused("duplicate", es.enter, st, rules, "p1", "entry-0002", {"fields": [":Ada", "  :Bob"]}, now=2)
    assert e.input == {"fields": ["\u00a0:Ada ", ":Bob\t"]}
    assert es.enter(st, rules, "p1", "entry-0002", {"fields": [":Ada", ": Bob"]}, now=3).new    # (inside: another)
    assert es.enter(st, rules, "p2", "entry-0003", {"fields": [":Ada", ":Bob"]}, now=4).new     # another student's
    assert alike({"text": " SELECT 1 "}) == {"text": " SELECT 1 "} and alike({"choice": [1]}) == {"choice": [1]}
