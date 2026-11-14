# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The live activity (texactivity) in the build (docs/architecture/activity-framework-design.md, sections 8
and 9; the plan of F2, 4.4; the registry of the build's types: types.py). The build asks the activity's
kind (texstage/activities: kind.py, registry.py): its build checks the kind's keys and gives the public
item, the private keys and the files; the references are checked by a worker of the pool, as the server
checks them - one that does not run stops the build, rather than showing in the panel during the lecture.

    records   activity|id=|kind=|input=|engine=|limit=|counts=|gap=|time=|budget=|feedback=|projector=
                      |solution=|open=|seed=|reference=|file=|line=      (texactivity.sty: the core's keys)
              activityoption|id=|key=|value=|items=     (a key of the kind's: as written, and as a list)
              activityref|id=|text=    activityseed|id=|text=
              Every field names itself; a text is hex-encoded, a list's items each, with a comma after it; a
              verbatim text's lines end in CR or "\\obeyedline ".
    box       a slide's live box: {type: activity, item, phase, rects: {box}} - phase: what the page is of
              the activity, open or revealed (\\reveal<n>)
    entries   deck.json's items.activity - {id: {kind, input?, limit, <the kind's item>, counts?, gap?, time?,
              budget?, feedback?, projector?, solution?, open?, prompt?}}: input is F1's name of the kind's
              input (tuple, code), for F1's type, which a server runs unless it is told otherwise; the core's
              keys but limit only where the deck gives them; the prompt as the phones' picture (an extra page,
              quiz.files). keys.json's - {id: {<the kind's keys: reference>, referenceKeys}}: the references'
              keys as the build's checks gave them, which the server compares with its own. The kind's files
              go into the bundle (a seed: data/<hash>.<its type>). deck.json's kinds - {name: {package,
              version, api}}: a server that lacks one refuses the deck (server/activities.py: refuses).
    aliases   the keys of before kinds were named (the design's 17): input=tuple is kind=triples,
              input=code, engine=sparql is kind=sparql-query - sql: sql-query, turtle: turtle-graph
    PowerPoint nothing: the slide picture shows the activity's static form, and the add-in stays the
              quiz's (docs/content-types-design.md, section 3)
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from texstage.activities import kit, registry
from texstage.activities.code import words
from texstage.activities.kind import Message
from texstage.activities.options import Choice, Flag, Int, Options, Unbuildable, Words
from texstage.activities.phases import MARKS, TIME_MAX_MS
from texstage.activities.play import FEEDBACK
from texstage.activities.reduce import PROJECTOR, SOLUTION
from texstage.build.bundle import language_tag, public_rects
from texstage.build.tqz import Item, Tqz, _hex
from texstage.engines import ENGINES

NAME = "activity"
KINDS = {"activity"}
USES_ADDIN = False
LIMIT_MAX = 50                             # a student's entries, at most (activities/kind.py)
GAP_MAX_S = 3600                           # seconds between two entries, at most (activities/entries.py)
TIME_MAX_S = TIME_MAX_MS // 1000           # a step's time, at most (activities/phases.py)
ESCAPED = re.compile(r"\\([{}#%&_$\\~^])")
ALIASES = {("tuple", ""): "triples", ("code", "sparql"): "sparql-query", ("code", "sql"): "sql-query",
           ("code", "turtle"): "turtle-graph"}           # the keys of before kinds were named (the design's 17)
F1_INPUT = {kind: input for (input, _), kind in ALIASES.items()}   # F1's input of a kind, for F1's type
PACKAGES = {"triples": "texstage-kinds-rdf", "sparql-query": "texstage-kinds-rdf", "turtle-graph": "texstage-kinds-rdf",
            "sql-query": "texstage-kinds-sql"}             # where texstage's first kinds are (kinds/ of its source)
CORE = ("kind", "input", "engine", "limit", "counts", "gap", "time", "budget", "feedback", "projector", "solution",
        "open", "seed", "reference")                      # the core's keys as the record names them
HEXED = {"kind", "engine", "limit", "gap", "time", "budget", "seed", "reference"}
GIVEN_ONLY = ("counts", "gap", "time", "budget", "feedback", "projector", "solution")    # in the item where given
ITEM = {"kind", "input", "limit", "open", "prompt", *GIVEN_ONLY}     # the core's in an item: no kind's build gives them
REFERENCE_BUDGET_S = 10.0                  # a reference's check, as the pool gives it (server/pool.py)
SEED_BACKSTOP_S = 60.0                     # a seed's loading at build - the server's pool gives it 120 s


class ActivityError(ValueError):
    """A deck's activities cannot be built (the message says why)."""


@dataclass
class Activity:
    """An activity as its records give it: the core's keys as the deck wrote them ("" where it gave none),
    the kind's keys in the deck's order - each as written and as a list -, the body's references and seed."""
    id: str
    core: dict[str, str]
    options: dict[str, tuple[str, list[str]]] = field(default_factory=dict)
    file: str = ""                             # the .tex file and line it is in
    line: int = 0
    references: list[str] = field(default_factory=list)
    seed_text: str = ""


@dataclass
class Activities:
    """What the build makes of a deck's activities: deck.json's items and kinds, keys.json's items, the
    files for the bundle, and how much a phone loads of the kinds' own files, compressed."""
    items: dict[str, dict] = field(default_factory=dict)
    keys: dict[str, dict] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    kinds: dict[str, dict] = field(default_factory=dict)
    phone_bytes: int = 0
    references: int = 0                        # the references checked


def _items(value: str) -> list[str]:
    """A list of the record: its items, \\{ and the like as the characters they stand for."""
    return [ESCAPED.sub(r"\1", _hex(x)).strip() for x in value.split(",") if x]


def _verbatim(text: str) -> str:
    """Normalize verbatim line breaks emitted by different LaTeX versions."""
    text = text.replace("\\obeyedline ", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def _named(record: list[str], name: str) -> dict[str, str]:
    """A record whose fields name themselves: {name: value}. One without names is an older texactivity.sty's."""
    out = {}
    for f in record:
        key, eq, value = f.partition("=")
        if not eq:
            raise ActivityError(f"the deck's {name} records have fields without names - it loads an older "
                                f"texactivity.sty than this builder: update the lecture's tools/ (git submodule "
                                f"update --remote tools), or build with the texstage of the lecture's tools/")
        out[key] = value
    return out


def read(tqz: Tqz) -> dict[str, Activity]:
    found: dict[str, Activity] = {}
    for f in tqz.records.get(NAME, []):
        r = _named(f, NAME)
        core = {k: _hex(r.get(k, "")) if k in HEXED else r.get(k, "") for k in CORE}
        line = r.get("line", "")
        found[r["id"]] = Activity(r["id"], core, file=_hex(r.get("file", "")), line=int(line) if line.isdigit() else 0)
    for kind in ("activityoption", "activityref", "activityseed"):
        for f in tqz.records.get(kind, []):
            r = _named(f, kind)
            a = found.get(r.get("id", ""))
            if a is None:
                raise ActivityError(f"a {kind} record of the activity {r.get('id')!r}, which has none of its own")
            if kind == "activityoption":
                a.options[_hex(r.get("key", ""))] = (ESCAPED.sub(r"\1", _hex(r.get("value", ""))).strip(),
                                                     _items(r.get("items", "")))
            elif kind == "activityref":
                a.references.append(_verbatim(_hex(r.get("text", ""))))
            else:
                a.seed_text = _verbatim(_hex(r.get("text", "")))
    return found


def box(tqz: Tqz, item: Item) -> dict:
    return {"type": NAME, "item": item.id, "phase": item.phase if item.phase in MARKS else "open",
            "rects": public_rects(item.rects, {}, tqz.paper)}


# ------------------------------------------------------------------ an activity's kind and keys
def kind_name(a: Activity) -> tuple[str, str]:
    """The activity's kind - the one it names, or the one of its input and engine (the aliases) - and how a
    warning names it: as the deck does."""
    kind, input, engine = a.core["kind"], a.core["input"], a.core["engine"]
    if kind and not engine:                     # the old keys beside a kind: they may only say what it is
        if input and F1_INPUT.get(kind) != input:
            raise ActivityError(f"activity {a.id}: kind={kind} and input={input} name two kinds - give one of them")
        return kind, f"kind={kind}"
    input = input or ("code" if engine else "tuple")
    alias = ALIASES.get((input, engine))
    if alias is None:
        if input == "tuple":
            raise ActivityError(f"activity {a.id}: input=tuple takes no engine (that is for input=code)")
        if not engine:
            raise ActivityError(f"activity {a.id}: input=code needs an engine (engine=sparql, engine=sql or "
                                f"engine=turtle) - or a kind")
        raise ActivityError(f"activity {a.id}: engine={engine} - texstage runs {', '.join(ENGINES)}")
    if not kind:
        return alias, f"input={input}"
    if kind != alias:
        wrote = ", ".join(f"{k}={a.core[k]}" for k in ("input", "engine") if a.core[k])
        raise ActivityError(f"activity {a.id}: kind={kind} and {wrote} name two kinds - give one of them")
    return kind, f"kind={kind}"


def kind_of(a: Activity, name: str):
    try:
        return registry.kind(name)
    except registry.Missing as e:
        package = PACKAGES.get(name)
        more = f" - install {package} (in texstage's source: pip install -e kinds/{package})" if package else ""
        raise ActivityError(f"activity {a.id}: kind={name} - {e}{more}") from None


def _option(kind, key: str):
    """A key's option: the kind's own - or, for a key the kind does not take, the option of an installed kind
    that takes it, so that the warning says what F1's said: a list given empty or as F1's preset of fields, a
    flag given off, is no key given (the review of package 7: fields= on a query ended the build). And
    whether it is the kind's own."""
    if key in kind.OPTIONS:
        return kind.OPTIONS[key], True
    for _, other in sorted(registry.kinds().items()):
        if key in other.OPTIONS:
            return other.OPTIONS[key], False
    return None, False


def _given(kind, a: Activity) -> dict:
    """The kind's keys as its options read them (activities/options.py): a list where it takes one, else the
    text as written - a key written without a value is on (review) -, and the files beside the deck that
    texactivity.sty reads too, seed= and reference= ("" where the deck names none: a seed in the body is
    told in this order too). In the deck's order, the files last."""
    given: dict = {}
    for key, (value, items) in a.options.items():
        option, own = _option(kind, key)
        if isinstance(option, Words):
            given[key] = items
        elif value == "" and (option is None or isinstance(option, Flag)):
            given[key] = True                  # a key written without a value: on
        elif isinstance(option, Flag) and not own and value in ("true", "false"):
            given[key] = value == "true"       # another kind's flag: off is not given
        else:
            given[key] = value
    for key in ("seed", "reference"):
        given[key] = a.core[key]
    return given


def _read(a: Activity, option, key: str, value: str):
    try:
        return option.read(key, value, None)
    except Unbuildable as e:
        raise ActivityError(f"activity {a.id}: {e}") from None


def _gap(a: Activity, value: str) -> int | float:
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", value) or float(value) > GAP_MAX_S:
        raise ActivityError(f"activity {a.id}: gap={value} - seconds from 0 to {GAP_MAX_S}")
    seconds = float(value)
    return int(seconds) if seconds.is_integer() else seconds


def core_keys(a: Activity, kind) -> dict:
    """The core's keys of the activity, read and checked: limit always - the kind's where the deck gives
    none -, the others only where the deck gives them; open, where it is manual."""
    k = a.core
    out: dict = {"limit": _read(a, Int(LIMIT_MAX, kind.LIMIT), "limit", k["limit"])}
    if k["counts"]:
        out["counts"] = _read(a, Choice("latest", "all"), "counts", k["counts"])
    if k["gap"]:
        out["gap"] = _gap(a, k["gap"])
    if k["time"]:
        out["time"] = _read(a, Int(TIME_MAX_S), "time", k["time"])
    if k["budget"]:
        out["budget"] = _read(a, Int(max(1, round(kind.BUDGET_S * 1000))), "budget", k["budget"])
    for key, values in (("feedback", FEEDBACK), ("projector", PROJECTOR), ("solution", SOLUTION)):
        if k[key]:
            out[key] = _read(a, Choice(*values), key, k[key])
    if _read(a, Choice("auto", "manual"), "open", k["open"]) == "manual":
        out["open"] = "manual"
    return out


# ------------------------------------------------------------------ the references, as the server checks them
class Checker:
    """The references of a deck's activities checked as the server checks them: by a worker of the pool,
    the kind's prepare and check under the pool's budget and watchdog - not in the build's own process,
    where a query that runs away would hold the build up for ever. One pool for the deck, made when the
    first activity asks."""

    def __init__(self, seed_backstop_s: float = SEED_BACKSTOP_S):
        self.pool = None
        self.seed_backstop = seed_backstop_s

    def __call__(self, act: str, kind: str, item: dict, keys: dict, files: dict[str, bytes],
                 language: str | None) -> list[dict]:
        """The outcomes of the references, in their order - or the seed's error (ValueError). A seed whose
        loading runs away ends the process that loads it, and once more a fresh one (the pool's backstop):
        the outcomes are waited for a little longer than that."""
        from texstage.server import worker
        from texstage.server.pool import Pool
        if self.pool is None:
            self.pool = Pool(workers=1, spare=0, reference_budget_s=REFERENCE_BUDGET_S,
                             prepare_backstop_s=self.seed_backstop).start()
        references = list(keys.get("reference") or [])
        fut = self.pool.prepare(act, worker.KIND + kind, {"item": item, "keys": keys, "files": files}, references, language)
        wait = 2 * self.seed_backstop + 2 * REFERENCE_BUDGET_S * (len(references) + 1) + 30
        started = time.monotonic()
        try:
            return fut.result(timeout=wait)
        except ValueError as e:
            if time.monotonic() - started >= self.seed_backstop:
                raise ValueError(f"it takes longer than the {self.seed_backstop:g} s a seed has at build - {e}") from None
            raise
        except TimeoutError:
            raise TimeoutError(f"they were not checked within {wait:.0f} s - a seed or a reference that runs "
                               f"away?") from None

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()


def _said(outcome: dict, language: str | None) -> str:
    """What a reference's check said, in words (the engines' texts; a kind's own code as it is)."""
    m = outcome.get("message")
    if isinstance(m, dict) and isinstance(m.get("code"), str):
        try:
            return words(Message(m["code"], dict(m.get("args") or {})), language)
        except (KeyError, IndexError, ValueError):
            return f"{outcome.get('status')}: {m['code']} {m.get('args') or ''}".strip()
    if outcome.get("error"):
        return str(outcome["error"])
    return {"timeout": f"it runs longer than the {REFERENCE_BUDGET_S:g} s a reference has",
            "internal": "its check failed - the kind's fault, or the pool's"}.get(outcome.get("status"),
                                                                                  str(outcome.get("status")))


def _run(a: Activity, act: str, name: str, item: dict, keys: dict, files: dict[str, bytes], language: str | None,
         checker) -> list[dict]:
    try:
        outcomes = checker(act, name, item, keys, files, language)
    except ValueError as e:                     # the seed's error
        said = str(e).splitlines()[0] if str(e) else repr(e)       # (a conversion would quote the whole: it did)
        raise ActivityError(f"activity {a.id}: the seed does not load - {said}") from None
    except Exception as e:  # noqa: BLE001 - the pool did not start, or did not answer
        broken = getattr(getattr(checker, "pool", None), "broken", None)
        hint = (' - a program that runs the build itself needs if __name__ == "__main__": the pool\'s processes '
                'import it' if broken else "")
        raise ActivityError(f"activity {a.id}: its references could not be checked - {type(e).__name__}: {e}{hint}") from None
    for i, o in enumerate(outcomes, 1):
        if not isinstance(o, dict) or o.get("status") != "ok":
            said = _said(o, language) if isinstance(o, dict) else repr(o)
            raise ActivityError(f"activity {a.id}: reference {i} does not run - {said}")
    return outcomes


def _referenced(a: Activity, name: str, item: dict, keys: dict, files: dict[str, bytes], language: str | None,
                checker) -> list[str | None]:
    """The references' keys, as the server's checks give them: the seed run twice, each time anew, and a
    key kept where both runs give it - a seed with random() gives another one each time, and its key would
    make the bundle another with every build and the server say another result (the review of package 7);
    such a reference has none (None). A reference that does not run - or a seed that does not load - stops
    the build."""
    first = _run(a, f"build/{a.id}", name, item, keys, files, language, checker)
    again = _run(a, f"build/{a.id}/again", name, item, keys, files, language, checker) if first else []
    return [o.get("key") if o.get("key") == p.get("key") else None for o, p in zip(first, again)]


# ------------------------------------------------------------------ deck.json's, keys.json's, the bundle's
def entries(tqz: Tqz, folder: Path, phone: dict, warnings: list[str],
            checker: Callable[..., list[dict]] | None = None) -> Activities:
    """The deck's activities as the bundle has them (the module's text). Paths are the deck's: relative to
    its folder. `phone`: the phones' pictures by item (quiz.files); `checker`: what checks the references -
    by default a pool of one worker (Checker), closed at the end."""
    out = Activities()
    language = language_tag(tqz.language)
    own = checker is None
    checker = Checker() if own else checker
    marks: dict[str, set[str]] = {}             # what the pages are of each activity: open, revealed
    for page in tqz.pages.values():
        for i in page.items:
            if i.kind == NAME:
                marks.setdefault(i.id, set()).add(i.phase)

    def files(name: str, what: str) -> str:
        path = folder / name
        if not path.is_file():
            raise Unbuildable(f"the {what} {name} is not there (paths are the deck's)")
        return path.read_text(encoding="utf-8-sig")

    try:
        for a in read(tqz).values():
            name, how = kind_name(a)
            kind = kind_of(a, name)
            core = core_keys(a, kind)
            split = next((key for key in a.options if key.isascii() and key.isdigit()), None)
            if split is not None:                       # tolerance=0,5: the keys tolerance=0 and 5
                raise ActivityError(f"activity {a.id}: a key {split} - a number with a decimal comma? A deck "
                                    f"writes a point: tolerance=0.5")
            options = Options(kind.OPTIONS, _given(kind, a), files)
            bodies = {"seed": a.seed_text, "references": a.references}
            try:
                built = kind.build(options, bodies)
            except Unbuildable as e:
                raise ActivityError(f"activity {a.id}: {e}") from None
            except Exception as e:  # noqa: BLE001 - the contract: a build refuses with Unbuildable, and raises nothing else
                raise ActivityError(f"activity {a.id}: the kind {name}'s build failed - {type(e).__name__}: {e} "
                                    f"(its fault, not the deck's)") from None
            ours = sorted(ITEM & set(built.item))
            if ours:
                raise ActivityError(f"activity {a.id}: the kind {name}'s build gives {', '.join(ours)} - the core's "
                                    f"keys, which no kind's item has (its fault, not the deck's)")
            item: dict = {"kind": name, **({"input": F1_INPUT[name]} if name in F1_INPUT else {}), "limit": core["limit"]}
            item |= built.item
            item |= {k: core[k] for k in (*GIVEN_ONLY, "open") if k in core}
            prompt = phone.get(f"{NAME}:{a.id}", {}).get("prompt")
            if prompt is not None:
                item["prompt"] = prompt
            keys = dict(built.keys)
            if keys.get("reference") or built.files:          # a seed to load, references to run
                checked = _referenced(a, name, item, keys, built.files, language, checker)
                if checked:
                    keys["referenceKeys"] = checked
                out.references += len(checked)
            extra = options.unused(bodies)
            if extra:
                warnings.append(f"activity {a.id}: {', '.join(extra)} - not for {how}")
            if marks.get(a.id) == {"revealed"} and core.get("open") != "manual":
                warnings.append(f"activity {a.id}: no slide opens it - its \\reveal<n> reveals it from the first one on")
            out.items[a.id] = item
            if keys:
                out.keys[a.id] = keys
            out.files |= built.files
            out.kinds.setdefault(name, kind)
    finally:
        if own:
            checker.close()
    found = {f.name: f for f in registry.found()}
    used = sorted(out.kinds)
    out.phone_bytes = kit.phone_bytes(*(out.kinds[n] for n in used))           # (a file of two kinds: once)
    out.kinds = {n: {"package": found[n].package, "version": found[n].version, "api": found[n].api} for n in used}
    return out


def check_slides(slides) -> None:
    """One activity per slide (texactivity.sty refuses two in a frame)."""
    for s in slides:
        found = [b["item"] for b in s.live if b["type"] == NAME]
        if len(found) > 1:
            raise ActivityError(f"page {s.page}: activities {', '.join(found)} on one slide - one per frame")
