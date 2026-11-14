# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The reductions of one game (docs/architecture/activity-framework-design.md, 6.2 and 10.2; the plan of
F2, 4.3): what a step's entries and their checks are reduced to, for the pictures (views.py).

    groups    the entries grouped by their check's key - without one, by its status -, counted by
              students, the largest first, each shown by the text that most of its entries have, in the
              form the kind's normalize gave it
    crowd     the fields as nodes and edges, from the checks' parts: today's crowd graph
              (server/activity.py), with the lecturer's merges, hidden and approved terms and minimum
    tally     the groups in the deck's order, a choice nobody made among them, each labelled with its
              choice's text (its key); a choice of several is a group of its own, its key the options'
              texts a line each (kind.py: SEVERAL) - and the picture counts each option too (options):
              how many chose it, alone or with others, which is what the class sees
    numbers   (of a step whose input is a number - groups as above) every number given, with its students
              and, where the window may know it, its verdict: what the windows draw a histogram of

Where a window may know the verdicts - the panel, the projector after the reveal - the picture says how
many students are right (right).

What a group is shown by is as clean as its kind's normalize makes a text: this module shows it as it
is. The design wants no name or joke in a comment to reach the class (5.1), and the kinds of a text take
its comments out (code.py: CodeKind.normalize); a check moved from F1 has the text as F1 cleaned it,
its comments with it.

What counts is an entry that is in, of the step's epoch, with a check. Kept in memory per step, as the
entries and their checks change: the groups by key with their students and their distinct texts, the
crowd's triples and terms - so that a picture goes through a step's groups and distinct texts, not
through its entries (the design's 10.2). touch() is told which entries changed - entered, replaced, taken
back, hidden, shown, checked - and looks for itself at what each is now; told twice, nothing is counted
twice. A reset gives the step a new epoch: nothing of the earlier one counts.

The references' results come from the pool (refer; package 6 hands them over) and are kept in memory - a
restarted server checks its references again. Unless a kind judges for itself, the core does (verdict;
the design's 6.3): correct when a check's key is one of the references', else incorrect. What a kind's
detail says of the reference - its comparison, under COMPARED - no projector has before the reveal.

A step's version goes up with everything a picture of it shows: the pictures are made once per version
(views.py).
"""
from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from texstage.activities.checks import Checks
from texstage.activities.entries import Entries, Rules
from texstage.activities.kind import COMPARED, REDUCTIONS, SEVERAL
from texstage.activities.store import MIN_MAX, CheckRow, EntryRow, StepRow, gid
from texstage.checks.cleaning import is_literal

__all__ = ["Mods", "Reduced", "Setup", "role"]

ROLES = ("node", "label")
NODES_SHOWN = 40                     # more labels than this do not fit apart in a slide's box (as F1's)
GROUPS_SHOWN = 8                     # the projector's groups
GROUPS_LISTED = 50                   # the panel's
TERMS_LISTED = 300                   # the panel's terms of a crowd graph
MESSAGES_LISTED = 5                  # what the checks of a group that is no result said, for the panel
PROJECTOR = ("live", "count", "hidden")
SOLUTION = ("show", "mark")


def role(i: int, n: int) -> str:
    """The role of the i-th of a triple's n terms: the first and the last a node, a middle one a label."""
    return "node" if i in (0, n - 1) else "label"


@dataclass(frozen=True)
class Setup:
    """What the core reads of a step's item, its kind and its keys for the entries, the reductions, the
    pictures and the moderation."""
    reduction: str = "groups"
    rules: Rules = Rules()
    min: int = 1                     # crowd: the students a triple needs to be shown, unless the lecturer says
    review: bool = False             # crowd: only what the lecturer approved is shown
    projector: str = "live"          # what the class sees while the step is open (the design's 5.3)
    solution: str = "show"           # what the reveal shows the class
    options: tuple[str, ...] = ()    # tally: the deck's choices, in its order
    references: tuple[str, ...] = ()     # the references' texts (keys.json): no picture has them before the reveal

    @classmethod
    def of(cls, item: dict, kind, keys: dict | None = None) -> Setup:
        """From the step's item (deck.json), its kind and its keys (keys.json). The item's `min` and
        `review` are a crowd graph's and its `options` a tally's: with another reduction these names are
        the kind's own, and the core reads none of them."""
        if kind.REDUCTION not in REDUCTIONS:
            raise ValueError(f"reduction: one of {', '.join(REDUCTIONS)}, not {kind.REDUCTION!r}")
        crowd, tally = kind.REDUCTION == "crowd", kind.REDUCTION == "tally"
        least = item.get("min", 1) if crowd else 1
        if isinstance(least, bool) or not isinstance(least, int) or not 1 <= least <= MIN_MAX:
            raise ValueError(f"min: 1 to {MIN_MAX}, not {least!r}")
        projector, solution = item.get("projector", "live"), item.get("solution", "show")
        if projector not in PROJECTOR:
            raise ValueError(f"projector: one of {', '.join(PROJECTOR)}, not {projector!r}")
        if solution not in SOLUTION:
            raise ValueError(f"solution: one of {', '.join(SOLUTION)}, not {solution!r}")
        options = (item.get("options") or ()) if tally else ()
        references = (keys or {}).get("reference") or ()
        if not isinstance(options, (list, tuple)) or not all(isinstance(o, str) for o in options):
            raise ValueError("options: texts")
        if not isinstance(references, (list, tuple)) or not all(isinstance(r, str) for r in references):
            raise ValueError("reference: texts")
        return cls(kind.REDUCTION, Rules.of(item, kind), least, crowd and item.get("review") is True, projector,
                   solution, tuple(options), tuple(references))


def _number(key: str | None) -> float | None:
    """A number kind's key - the number, as it writes it - as a number; None for one that is none."""
    try:
        n = float(key)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


@dataclass
class Mods:
    """What the lecturer's acts make of a step's picture (moderation.py): the crowd's merges - per role, a
    term into another -, the groups or terms that are hidden, the terms approved, the crowd's minimum
    (None: the deck's), the group whose detail is on the projector."""
    merges: dict[tuple[str, str], str] = field(default_factory=dict)
    hidden: set[str] = field(default_factory=set)
    approved: set[str] = field(default_factory=set)
    min: int | None = None
    shown: str | None = None
    shown_epoch: int = 0             # ... in this epoch of the step: a reset shows none


NONE = Mods()


@dataclass
class _Group:
    """The entries of a step that are in and share a key - or, where their checks are no result, a status.
    What a picture asks of it is kept by distinct text (norm), so that no picture goes through its
    entries."""
    status: str
    key: str | None
    players: Counter = field(default_factory=Counter)                     # student -> their entries in it
    members: dict[str, dict[str, int]] = field(default_factory=dict)      # norm -> {entry: when it came}
    firsts: dict[str, tuple[int, str]] = field(default_factory=dict)      # norm -> its first member: when, which
    checks: dict[str, CheckRow] = field(default_factory=dict)             # norm -> its check, of those ever in
    said: dict[str, str] = field(default_factory=dict)                    # norm -> its check's message, as one text
    verdict: str | None = None                                            # a result's: the kind's own, if it judges

    @property
    def id(self) -> str:
        return gid(self.status, self.key)

    def add(self, e: EntryRow) -> None:
        self.members.setdefault(e.norm, {})[e.id] = e.created
        at = (e.created, e.id)
        if e.norm not in self.firsts or at < self.firsts[e.norm]:
            self.firsts[e.norm] = at

    def remove(self, e: EntryRow) -> None:
        ids = self.members.get(e.norm)
        if ids is None or ids.pop(e.id, None) is None:
            return
        if not ids:
            del self.members[e.norm], self.firsts[e.norm]
        elif self.firsts[e.norm] == (e.created, e.id):                    # its first one left: who is it now
            self.firsts[e.norm] = min((at, eid) for eid, at in ids.items())

    def example(self) -> tuple[dict | None, str | None]:
        """What the group is shown by, and one entry of it: the normalized form that most of its entries
        have - among equally many the one that came first -, one with a form before one without (what
        normalize refused has none)."""
        best = None
        for norm, ids in self.members.items():
            rank = (self.checks[norm].form is None, -len(ids), self.firsts[norm])
            if best is None or rank < best[0]:
                best = (rank, norm)
        if best is None:
            return None, None
        return self.checks[best[1]].form, self.firsts[best[1]][1]

    def messages(self, most: int) -> list[dict]:
        """What the checks of its texts said, each message once, in the order its first entry came - the
        same whatever order the checks came in, and after a restart."""
        said: dict[str, tuple[tuple[int, str], str]] = {}
        for norm, first in self.firsts.items():
            key = self.said[norm]
            if key and (key not in said or first < said[key][0]):
                said[key] = (first, norm)
        return [self.checks[norm].message for _, norm in sorted(said.values())[:most]]


@dataclass
class _Step:
    """What one step's entries are reduced to, in one game."""
    epoch: int = 0
    version: int = 0
    where: dict[str, tuple] = field(default_factory=dict)                 # entry -> (state, check's state, check)
    states: Counter = field(default_factory=Counter)                      # the epoch's entries, by state
    groups: dict[tuple[str, str], _Group] = field(default_factory=dict)   # by (status, key or "")
    ids: dict[str, tuple[str, str]] = field(default_factory=dict)         # a group's id -> its (status, key)
    # crowd, from the checks' parts
    triples: dict[tuple[str, ...], Counter] = field(default_factory=dict)     # the terms' keys -> student -> entries
    terms: dict[tuple[str, str], Counter] = field(default_factory=dict)       # (role, key) -> student -> entries
    spelled: dict[tuple[str, str], Counter] = field(default_factory=dict)     # (role, key) -> text -> entries in
    first: dict[tuple[str, str, str], tuple[int, str]] = field(default_factory=dict)   # (role, key, text) -> the
    #                                                                       first entry that wrote it so: when, which
    refs: list[dict | None] = field(default_factory=list)                 # the references' results, in their order

    def turn(self, epoch: int) -> None:
        self.epoch = epoch
        self.version += 1
        self.where, self.states, self.groups, self.ids = {}, Counter(), {}, {}
        self.triples, self.terms, self.spelled, self.first = {}, {}, {}, {}


def _add(counter: Counter, key, n: int) -> None:
    counter[key] += n
    if counter[key] <= 0:
        del counter[key]


class Reduced:
    """One game's reductions, by step."""

    def __init__(self, session: str, entries: Entries, checks: Checks):
        self.session = session
        self.entries = entries
        self.checks = checks
        self.steps: dict[tuple[str, str], _Step] = {}

    def _of(self, st: StepRow) -> _Step:
        s = self.steps.setdefault((st.activity, st.step), _Step(st.epoch))
        if s.epoch != st.epoch:
            s.turn(st.epoch)
        return s

    # -------------------------------------------------------------- what changed
    def load(self, steps: Iterable[StepRow], entries: Iterable[EntryRow]) -> None:
        """After a restart, once the entries and the checks are loaded: every entry counted as it is."""
        by = {(st.activity, st.step): st for st in steps if st.session == self.session}
        for e in entries:
            st = by.get((e.activity, e.step))
            if st is not None and e.session == self.session:
                self.touch(st, e)

    def touch(self, st: StepRow, *entries: EntryRow) -> bool:
        """These entries of the step changed - their state, or their check: each is counted as it is now.
        Whether anything a picture shows changed. An entry of another step: ValueError, and none is
        counted."""
        s = self._of(st)
        for e in entries:
            if e.session != self.session or (e.activity, e.step) != (st.activity, st.step):
                raise ValueError(f"the entry {e.id} is not of the step {st.activity}/{st.step}")
        changed = False
        for e in entries:
            new = (e.state, self.checks.state(e), self.checks.of(e)) if e.epoch == s.epoch else None
            old = s.where.get(e.id)
            if old == new and (old is None or old[2] is new[2]):
                continue
            if old is not None:
                self._count(s, e, old, -1)
                del s.where[e.id]
            if new is not None:
                self._count(s, e, new, 1)
                s.where[e.id] = new
            changed = True
        if changed:
            s.version += 1
        return changed

    def _count(self, s: _Step, e: EntryRow, sig: tuple, n: int) -> None:
        state, _, check = sig
        _add(s.states, state, n)
        if check is None:
            return
        ok = check.status == "ok"
        key = (check.status, check.key or "") if ok else (check.status, "")
        g = s.groups.get(key)
        if g is None:                                     # known from now on, though its entries may all go
            g = s.groups[key] = _Group(check.status, check.key if ok else None)
            s.ids[g.id] = key
        parts = check.parts if ok and check.parts else ()
        for i, p in enumerate(parts):                     # a term is known once an entry has it, in any state;
            written = (role(i, len(parts)), p["key"], p["text"])          # its first writing is the earliest entry's,
            if written not in s.first or (e.created, e.id) < s.first[written]:     # whichever was checked first
                s.first[written] = (e.created, e.id)
        if n > 0:
            if e.norm not in g.checks:
                g.checks[e.norm] = check
                g.said[e.norm] = json.dumps(check.message, sort_keys=True) if check.message else ""
            if ok and g.verdict is None:                  # (one key, one result: its checks are judged alike)
                g.verdict = check.verdict
        if state != "in":
            return
        _add(g.players, e.player, n)
        if n > 0:
            g.add(e)
        else:
            g.remove(e)
        if parts:
            keys = tuple(p["key"] for p in parts)
            _add(s.triples.setdefault(keys, Counter()), e.player, n)
            if not s.triples[keys]:
                del s.triples[keys]
            for i, p in enumerate(parts):
                rk = (role(i, len(parts)), p["key"])
                _add(s.terms.setdefault(rk, Counter()), e.player, n)
                _add(s.spelled.setdefault(rk, Counter()), p["text"], n)
                if not s.terms[rk]:
                    del s.terms[rk], s.spelled[rk]

    def bump(self, activity: str, step: str) -> None:
        """Something else a picture shows changed - the phase, an act of the lecturer's, a reference."""
        self.steps.setdefault((activity, step), _Step()).version += 1

    def version(self, st: StepRow) -> int:
        return self._of(st).version

    # -------------------------------------------------------------- the references
    def refer(self, activity: str, step: str, outcomes: Iterable[dict | None]) -> None:
        """The references' results, in the deck's order, as the pool gave them - a check's outcome each,
        or None while it is not run."""
        s = self.steps.setdefault((activity, step), _Step())
        refs = [None if o is None else {k: o[k] for k in ("status", "key", "detail") if o.get(k) is not None}
                for o in outcomes]
        if refs != s.refs:
            s.refs = refs
            s.version += 1

    def _keys(self, s: _Step) -> set[str]:
        return {r["key"] for r in s.refs if r is not None and r.get("status") == "ok" and r.get("key")}

    def verdict(self, activity: str, step: str, check: CheckRow | None) -> str | None:
        """A check's verdict: the kind's own - else the core's: correct when its key is one of the
        references', else incorrect; None while there is nothing to judge by, and for a check that failed
        (internal: never graded)."""
        if check is None or check.status == "internal":
            return None
        if check.verdict is not None:
            return check.verdict
        s = self.steps.get((activity, step))
        keys = self._keys(s) if s is not None else set()
        if not keys:
            return None
        return "correct" if check.status == "ok" and check.key in keys else "incorrect"

    def references(self, st: StepRow, setup: Setup) -> list[dict | None]:
        """For the panel, per reference of the deck: its group, that it failed - or None, not run yet."""
        s = self._of(st)
        refs = (s.refs + [None] * len(setup.references))[:max(len(setup.references), len(s.refs))]
        return [None if r is None else {"group": gid("ok", r["key"])} if r.get("status") == "ok" and r.get("key")
                else {"failed": r.get("status") or "internal"} for r in refs]

    def solution(self, st: StepRow, setup: Setup) -> list[dict]:
        """What the reveal shows of the references (solution=show): each one's text, its group and its
        detail."""
        s = self._of(st)
        out = []
        for i, text in enumerate(setup.references):
            r = s.refs[i] if i < len(s.refs) else None
            one: dict = {"text": text}
            if r is not None and r.get("status") == "ok" and r.get("key"):
                one["group"] = gid("ok", r["key"])
                detail = self.checks.detail(st.activity, st.step, r["key"]) or r.get("detail")
                if detail is not None:
                    one["detail"] = detail
            out.append(one)
        return out

    # -------------------------------------------------------------- what the moderation and the pictures ask
    def group(self, st: StepRow, group, setup: Setup | None = None, counted: bool = False) -> bool:
        """Whether the step's epoch has - counted: has entries in - a group of this id. A tally's choice
        is one though nobody made it (setup: the step's)."""
        s = self._of(st)
        key = s.ids.get(group) if isinstance(group, str) else None
        if key is not None:
            return not counted or bool(s.groups[key].players)
        return (not counted and setup is not None and setup.reduction == "tally"
                and any(group == gid("ok", option) for option in setup.options))

    def term(self, st: StepRow, key, of: str | None = None) -> bool:
        """Whether an entry of the step's epoch has this term - of: in this role."""
        s = self._of(st)
        return isinstance(key, str) and any(k == key and (of is None or r == of) for r, k, _ in s.first)

    def nodes(self, st: StepRow) -> set[str]:
        """The terms that entries of the step's epoch have as a node."""
        return {k for r, k, _ in self._of(st).first if r == "node"}

    def hidden(self, st: StepRow) -> int:
        """The step's entries that the lecturer hid."""
        return self._of(st).states["hidden"]

    # -------------------------------------------------------------- the reductions
    def reduce(self, st: StepRow, setup: Setup, mods: Mods = NONE, window: str = "display",
               layout: dict | None = None) -> dict:
        """The step's entries reduced, for the projector (display: moderated; nothing of the reference
        before the reveal) or for the presenter window's panel (stage: with what is hidden, merged,
        waiting to be approved - and the references' groups at once)."""
        stage = window == "stage"
        if setup.reduction == "crowd":
            return self._crowd(self._of(st), setup, mods, stage, layout or {})
        return self._groups(st, setup, mods, stage)

    def _groups(self, st: StepRow, setup: Setup, mods: Mods, stage: bool) -> dict:
        s = self._of(st)
        marks = stage or st.phase == "revealed"
        keys = self._keys(s) if marks else set()

        def judged(g: _Group) -> str | None:
            """The group's verdict where the window may know it (marks): its kind's, else by the references'
            keys; None where there is none."""
            if not marks:
                return None
            if g.verdict is not None:
                return g.verdict
            if keys and g.status != "internal":
                return "correct" if g.status == "ok" and g.key in keys else "incorrect"
            return None

        def entry(g: _Group) -> dict:
            form, example = g.example()
            out = {"id": g.id, "status": g.status, "n": len(g.players), "example": form,
                   "reference": g.status == "ok" and g.key in keys}
            if tally and g.status == "ok":
                out["label"] = g.key                    # (a tally's key is its choice's text: no hash)
            verdict = judged(g)
            if verdict is not None:
                out["verdict"] = verdict
            if g.status == "ok":
                detail = self.checks.detail(st.activity, st.step, g.key)
                if detail is not None and not marks and COMPARED in detail:
                    detail = {k: v for k, v in detail.items() if k != COMPARED}      # nothing of the reference yet
                if detail is not None:
                    out["detail"] = detail
            if stage:
                out["hidden"] = g.id in mods.hidden
                if example is not None:
                    out["entry"] = example
                if g.status != "ok":
                    out["messages"] = g.messages(MESSAGES_LISTED)
            return out
        tally = setup.reduction == "tally"
        most = GROUPS_LISTED if stage else GROUPS_SHOWN
        found = [g for g in s.groups.values() if g.players
                 and (stage or (g.status != "internal" and g.id not in mods.hidden))]
        ranked = sorted(found, key=lambda g: (-len(g.players), g.status != "ok", g.key or g.status))
        if tally:                                         # the deck's choices in its order, one nobody made among
            at = {key: i for i, key in enumerate(setup.options)}          # them; then the largest of the others
            have = {g.key for g in found if g.status == "ok"}
            given = [g for g in found if g.status == "ok" and g.key in at] + \
                [_Group("ok", key) for key in setup.options
                 if key not in have and (stage or gid("ok", key) not in mods.hidden)]
            rest = [g for g in ranked if not (g.status == "ok" and g.key in at)]
            listed = sorted(given, key=lambda g: at[g.key]) + rest[:most]
            others = rest[most:]
        else:
            listed, others = ranked[:most], ranked[most:]
        out = {"kind": "tally" if tally else "groups", "groups": [entry(g) for g in listed],
               "others": sum(len(g.players) for g in others), "shown": None}
        if tally and setup.rules.many:                    # a choice of several: how many chose each option, alone
            counted: Counter = Counter()                  # or with others - the class's tally
            for g in found:
                if g.status == "ok" and g.key:
                    for option in set(g.key.split(SEVERAL)):
                        counted[option] += len(g.players)
            right = {option for k in keys for option in k.split(SEVERAL)}
            out["options"] = [{"label": o, "n": counted[o], "reference": o in right} for o in setup.options]
        if setup.rules.input == "number":                 # a histogram's: every number given, with its students
            numbers = []                                  # and, where the window may know it, its verdict
            for g in found:
                if g.status == "ok" and (n := _number(g.key)) is not None:
                    verdict = judged(g)
                    numbers.append([n, len(g.players), verdict] if verdict else [n, len(g.players)])
            out["numbers"] = sorted(numbers, key=lambda x: x[0])
        if any(judged(g) for g in found):                 # (marks: how many are right, of all the groups)
            out["right"] = sum(len(g.players) for g in found if judged(g) == "correct")
        key = s.ids.get(mods.shown) if mods.shown and mods.shown_epoch == s.epoch else None
        if key is not None and any(g is s.groups[key] for g in found):
            out["shown"] = entry(s.groups[key])
        return out

    def _crowd(self, s: _Step, setup: Setup, mods: Mods, stage: bool, layout: dict) -> dict:
        """Today's crowd graph (server/activity.py: _crowd): the triples with at least `min` students,
        without hidden terms - with review only approved ones -, the lecturer's merges applied, the
        NODES_SHOWN nodes with the most students. A term is written as most of the entries that count
        write it, among as many as the entry that came first wrote it."""
        least = mods.min if mods.min is not None else setup.min

        def root(r: str, k: str) -> str:
            seen = set()
            while (r, k) in mods.merges and k not in seen:
                seen.add(k)
                k = mods.merges[(r, k)]
            return k

        def label(r: str, k: str) -> str:
            counts = s.spelled.get((r, k))
            if counts:
                # (one entry may write a term two ways - :a for its subject, :A for its object: then by the text)
                return min(counts, key=lambda text: (-counts[text], s.first[(r, k, text)], text))
            known = [(at, text) for (r2, k2, text), at in s.first.items() if (r2, k2) == (r, k)]
            return min(known)[1] if known else k          # (nobody has it in any more; nobody ever had it)
        triples: dict[tuple, set] = {}
        for keys, who in s.triples.items():
            t = tuple(root(role(i, len(keys)), k) for i, k in enumerate(keys))
            triples.setdefault(t, set()).update(who)
        visible = {t: who for t, who in triples.items()
                   if len(who) >= least and not mods.hidden & set(t) and (not setup.review or set(t) <= mods.approved)}
        nodes: dict[str, set] = {}
        for t, who in visible.items():
            for k in (t[0], t[-1]):
                nodes.setdefault(k, set()).update(who)
        ranked = sorted(nodes, key=lambda k: (-len(nodes[k]), label("node", k)))
        top = set(ranked[:NODES_SHOWN])

        def node(k: str) -> dict:                         # a literal says so: the windows draw it as a box
            name = label("node", k)
            return {"id": k, "label": name, "n": len(nodes[k])} | ({"literal": True} if is_literal(name) else {})
        out = {"kind": "graph", "min": least, "review": setup.review,
               "nodes": [node(k) for k in ranked[:NODES_SHOWN]],
               "edges": [{"s": t[0], "o": t[-1], "p": t[1] if len(t) == 3 else None,
                          "label": label("label", t[1]) if len(t) == 3 else "", "n": len(who)}
                         for t, who in sorted(visible.items(), key=lambda e: (-len(e[1]), e[0]))
                         if t[0] in top and t[-1] in top],
               "more": max(0, len(ranked) - NODES_SHOWN),
               "at": {k: layout[k] for k in ranked[:NODES_SHOWN] if k in layout}}
        if stage:
            listed = sorted(s.terms, key=lambda rk: (-len(s.terms[rk]), rk))[:TERMS_LISTED]
            out["terms"] = [{"role": r, "key": k, "label": label(r, k), "n": len(s.terms[(r, k)]),
                             "hidden": k in mods.hidden, "approved": k in mods.approved,
                             "into": mods.merges.get((r, k))} for r, k in listed]
            out["hiddenTuples"] = s.states["hidden"]
            # the entries that are in and no triple - what the kind's normalize refused: in no graph, so said here
            out["invalid"] = sum(len(ids) for g in s.groups.values() if g.status != "ok" for ids in g.members.values())
        return out
