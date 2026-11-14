# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pictures of one game (docs/architecture/activity-framework-design.md, 5.3, 10.1 and 13; the plan
of F2, 4.3): what the projector and the panel draw of a step - its entries reduced (reduce.py), counted,
moderated (moderation.py).

A picture is made once per version and window, not once per window that asks. Two windows ask:

    display   the projector, and the box on the slide: moderated - without what the lecturer hid, what
              could not be checked, and before the reveal the references. What the class sees while the
              step is open is the deck's (projector=): live - the picture grows; count - how many sent,
              and the picture once the step is closed; hidden - nothing until the reveal.
    stage     the presenter window's panel: with what is hidden, merged or waiting to be approved, the
              references' groups at once, the counts, and the lecturer's last acts.

At the reveal, with solution=show, both get the references' texts and results; with solution=mark only
the groups that match are marked. No picture names a student.

The windows are told a step's version when it changes, at most four times a second (told), and fetch the
picture then. The version goes up with what the reductions count, with the step's phase and epoch, and
with the checks' counts - a check that fails for the server's reasons changes no entry, and the panel's
counts all the same. A crowd graph's positions come from the window that lays it out
(layout: AF 13) and are part of the picture; they are not stored.
"""
from __future__ import annotations

from collections import Counter

from texstage.activities.checks import Checks
from texstage.activities.entries import Entries
from texstage.activities.moderation import Moderation
from texstage.activities.phases import Refused
from texstage.activities.kind import KEY_MAX
from texstage.activities.reduce import NODES_SHOWN, Reduced, Setup
from texstage.activities.store import StepRow

__all__ = ["Pictures", "WINDOWS"]

WINDOWS = ("display", "stage")
EVERY_MS = 250                       # the windows are told a new version at most this often (the design's 15.1)
KEPT = 8                             # a step's pictures that are kept
RUNS = ("ready", "open", "paused")   # the phases in which projector=count shows the counts alone


class Pictures:
    """One game's pictures, by step."""

    def __init__(self, session: str, entries: Entries, checks: Checks, reduced: Reduced, moderation: Moderation):
        self.session = session
        self.entries = entries
        self.checks = checks
        self.reduced = reduced
        self.moderation = moderation
        self.seen: dict[tuple[str, str], tuple] = {}                  # a step's phase, epoch and checks' counts,
        #                                                               as last looked at
        self.at: dict[tuple[str, str], dict[str, list[float]]] = {}   # a crowd graph's positions
        self.laid: Counter = Counter()                                # ... and how often they changed
        self.last: dict[tuple[str, str], tuple[tuple[int, int], int]] = {}    # what the windows were told, and when
        self.cache: dict[tuple[str, str], dict[tuple, dict]] = {}

    # -------------------------------------------------------------- versions
    def moved(self, *rows: StepRow) -> None:
        """Steps that a move changed (phases.py gives them): one whose phase or epoch is another has a
        new version. (Who asks for a version or a picture looks too: a move that was not told is seen
        then.)"""
        for st in rows:
            self._look(st)

    def _look(self, st: StepRow) -> tuple[str, str]:
        key = (st.activity, st.step)
        now = (st.phase, st.epoch, tuple(sorted(self.checks.counts(st).items())))
        if self.seen.get(key, now) != now:
            self.reduced.bump(*key)
        self.seen[key] = now
        return key

    def version(self, st: StepRow) -> tuple[int, int]:
        """The step's version, and its layout's: a window that has another fetches the picture."""
        key = self._look(st)
        return self.reduced.version(st), self.laid[key]

    def told(self, st: StepRow, now: int) -> dict | None:
        """What the windows are to be told now - {version, layout} -, or None: they know it, or were told
        less than a quarter of a second ago. The server asks with every tick."""
        key = self._look(st)
        version = self.version(st)
        last = self.last.get(key)
        if last is not None and (last[0] == version or 0 <= now - last[1] < EVERY_MS):
            return None
        self.last[key] = (version, now)
        return {"version": version[0], "layout": version[1]}

    def layout(self, st: StepRow, setup: Setup, at) -> bool:
        """A crowd graph's positions from the window that lays it out - per node its place in the box,
        both from 0 to 1 - for every window. Kept of what is sent: the places of terms that entries of
        the step have as a node. Whether they changed. Refused: a step that is no crowd graph
        (reduction), what is no table of places or one of more than four times the nodes a box shows."""
        if setup.reduction != "crowd":
            raise Refused("only a crowd graph is laid out", "reduction")
        if not isinstance(at, dict) or len(at) > 4 * NODES_SHOWN:
            raise Refused("at: {term: [x, y]}")
        nodes = self.reduced.nodes(st)
        found = {}
        for term, p in at.items():
            if (isinstance(term, str) and len(term) <= KEY_MAX and term in nodes and isinstance(p, list) and len(p) == 2
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in p)):
                found[term] = [round(p[0], 4), round(p[1], 4)]
        key = (st.activity, st.step)
        if self.at.get(key, {}) == found:
            return False
        self.at[key] = found
        self.laid[key] += 1
        return True

    # -------------------------------------------------------------- the picture
    def picture(self, st: StepRow, setup: Setup, window: str = "display") -> dict:
        """The step's picture for a window. It is the same object for everyone who asks until the version
        changes: nobody changes it."""
        window = "stage" if window == "stage" else "display"
        key = self._look(st)
        version, layout = self.version(st)
        kept = self.cache.setdefault(key, {})
        which = (window, version, layout, st.phase, st.epoch, setup)
        if which not in kept:
            if len(kept) >= KEPT:
                kept.clear()
            kept[which] = self._made(st, setup, window, version, layout)
        return kept[which]

    def _made(self, st: StepRow, setup: Setup, window: str, version: int, layout: int) -> dict:
        revealed = st.phase == "revealed"
        out: dict = {"activity": st.activity, "step": st.step, "epoch": st.epoch, "phase": st.phase,
                     "version": version, "layout": layout, "reduction": setup.reduction, "revealed": revealed}
        counts = self.entries.counts(st)
        if window == "display":
            if setup.projector == "hidden" and not revealed:
                return out | {"held": "hidden"}
            if setup.projector == "count" and st.phase in RUNS:
                return out | {"held": "count"} | counts
        checks = self.checks.counts(st)
        out |= counts | {"waiting": checks["waiting"]}
        out["checked"] = max(0, counts["entries"] - checks["waiting"] - checks["unchecked"])
        mods = self.moderation.of(st.activity, st.step)
        if window == "stage":
            out |= {"unchecked": checks["unchecked"], "forms": checks["forms"], "full": checks["full"],
                    "hidden": self.reduced.hidden(st), "references": self.reduced.references(st, setup),
                    "acts": self.moderation.acts(st.activity, st.step, st.epoch)}
        out |= self.reduced.reduce(st, setup, mods, window, self.at.get((st.activity, st.step)))
        if revealed and setup.solution == "show" and setup.references:
            out["solution"] = self.reduced.solution(st, setup)
        return out
