# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The live activity (texactivity) in the build (docs/live-activities-design.md, sections 5 and 6;
the registry: types.py).

    records   activity|id|input|engine|fields|suggest|tokens|limit|min|review|open|terms|seed
                      |reference|tex file|line
              activityref|id|query    activityseed|id|text      (texactivity.sty: texts hex-encoded,
              a verbatim one's lines ending in "\\obeyedline "; a list: hex items, each with a comma)
    box       a slide's live box: {type: activity, item, rects: {box}}
    entries   deck.json's items.activity - {id: {input, limit, fields, suggest?, min, review?, terms |
              engine, tokens, seed; open?, prompt?}}: the seed in the bundle as data/<hash>.ttl (.sql - the
              engine's file type, texstage/engines.py; engine=turtle takes only its prefixes), the
              prompt as the phones' picture (an extra page, quiz.files); keys.json's - {id:
              {reference: [queries, or Turtle texts]}}: the server gives them only to the presenter
              window that evaluates
    PowerPoint nothing: the slide picture shows the activity's static form, and the add-in stays the
              quiz's (docs/content-types-design.md, section 3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from texstage.build.bundle import content_name, public_rects
from texstage.build.tqz import Item, Tqz, _hex
from texstage.engines import ENGINES

NAME = "activity"
KINDS = {"activity"}
USES_ADDIN = False
INPUTS = ("tuple", "code")
TERMS = ("exact", "loose")                 # a tuple's terms: as written (RDF's IRIs), or as the word cloud groups words
LIMITS = {"tuple": 10, "code": 5}          # contributions per student, by default
LIMIT_MAX = 50
FIELDS = (2, 3)                            # the first and the last a node, a middle one the edge's label
WORD_MAX = 60                              # a field's label, a suggestion, a token
WORDS_MAX = 40                             # suggestions, tokens
SEED_MAX = 2 * 2**20                       # the presenter's browser loads it
QUERY_MAX = 2000                           # a reference: as long as a student's query may be
ESCAPED = re.compile(r"\\([{}#%&_$\\~^])")


class ActivityError(ValueError):
    """A deck's activities cannot be built (the message says why)."""


@dataclass
class Activity:
    id: str
    input: str
    engine: str
    fields: list[str]
    suggest: list[str]
    tokens: list[str]
    limit: str
    min: str
    review: bool
    open: str
    terms: str                 # "" when the deck does not say: exact
    seed: str                  # a file, as the deck names it
    reference_file: str
    file: str                  # the .tex file and line it is in
    line: int
    references: list[str] = field(default_factory=list)
    seed_text: str = ""


def _words(field_: str) -> list[str]:
    """A list of the record: its items, \\{ and the like as the characters they stand for."""
    return [ESCAPED.sub(r"\1", _hex(x)).strip() for x in field_.split(",") if x]


def _verbatim(text: str) -> str:
    """A verbatim text of the record (xparse's +v ends its lines with \\obeyedline)."""
    return "\n".join(line.rstrip() for line in text.replace("\\obeyedline ", "\n").split("\n")).strip("\n")


def read(tqz: Tqz) -> dict[str, Activity]:
    found: dict[str, Activity] = {}
    for f in tqz.records.get(NAME, []):
        found[f[0]] = Activity(f[0], f[1], f[2], _words(f[3]), _words(f[4]), _words(f[5]), f[6], f[7],
                               f[8] == "true", f[9] or "auto", f[10], _hex(f[11]), _hex(f[12]), _hex(f[13]),
                               int(f[14]))
    for f in tqz.records.get("activityref", []):
        found[f[0]].references.append(_verbatim(_hex(f[1])))
    for f in tqz.records.get("activityseed", []):
        found[f[0]].seed_text = _verbatim(_hex(f[1]))
    return found


def box(tqz: Tqz, item: Item) -> dict:
    return {"type": NAME, "item": item.id, "rects": public_rects(item.rects, {}, tqz.paper)}


def _number(a: Activity, key: str, value: str, default: int, top: int) -> int:
    if not value:
        return default
    if not value.isdigit() or not 1 <= int(value) <= top:
        raise ActivityError(f"activity {a.id}: {key}={value} - a number from 1 to {top}")
    return int(value)


def _words_ok(a: Activity, key: str, words: list[str]):
    if len(words) > WORDS_MAX or any(not w or len(w) > WORD_MAX for w in words):
        raise ActivityError(f"activity {a.id}: {key}= takes at most {WORDS_MAX} items of 1 to {WORD_MAX} characters")


def _text(a: Activity, folder: Path, name: str, what: str) -> str:
    path = folder / name
    if not path.is_file():
        raise ActivityError(f"activity {a.id}: the {what} {name} is not there (paths are the deck's)")
    return path.read_text(encoding="utf-8-sig")


def entries(tqz: Tqz, folder: Path, phone: dict, warnings: list[str]) -> tuple[dict, dict, dict[str, bytes]]:
    """deck.json's items.activity, keys.json's, and the files (the seeds). Paths are the deck's:
    relative to its folder. `phone`: the phones' pictures by item (quiz.files)."""
    items: dict[str, dict] = {}
    keys: dict[str, dict] = {}
    files: dict[str, bytes] = {}
    for a in read(tqz).values():
        if a.input not in INPUTS:
            raise ActivityError(f"activity {a.id}: input={a.input} - texstage takes {' or '.join(INPUTS)}")
        entry: dict = {"input": a.input, "limit": _number(a, "limit", a.limit, LIMITS[a.input], LIMIT_MAX)}
        if a.input == "tuple":
            if not FIELDS[0] <= len(a.fields) <= FIELDS[1]:
                raise ActivityError(f"activity {a.id}: {len(a.fields)} fields - an activity of input=tuple has "
                                    f"{FIELDS[0]} or {FIELDS[1]}: the first and the last a node, a middle one "
                                    f"the edge's label")
            _words_ok(a, "fields", a.fields)
            _words_ok(a, "suggest", a.suggest)
            entry["fields"] = a.fields
            if a.suggest:
                entry["suggest"] = a.suggest
            entry["min"] = _number(a, "min", a.min, 1, 1000)
            if a.review:
                entry["review"] = True
            if a.terms and a.terms not in TERMS:
                raise ActivityError(f"activity {a.id}: terms={a.terms} - {' or '.join(TERMS)}")
            entry["terms"] = a.terms or TERMS[0]
            unused = [k for k, v in (("tokens", a.tokens), ("seed", a.seed or a.seed_text),
                                     ("reference", a.reference_file or a.references)) if v]
        else:
            engine = ENGINES.get(a.engine)
            if engine is None:
                raise ActivityError(f"activity {a.id}: engine={a.engine} - texstage runs {', '.join(ENGINES)}")
            _words_ok(a, "tokens", a.tokens)
            entry["engine"] = a.engine
            entry["tokens"] = a.tokens + [t for t in engine["tokens"] if t not in a.tokens]
            if a.seed:
                if Path(a.seed).suffix.lower() not in engine["seed"]:
                    raise ActivityError(f"activity {a.id}: the seed {a.seed} - {a.engine} takes "
                                        f"{', '.join(engine['seed'])} files")
                seed = _text(a, folder, a.seed, "seed").encode("utf-8")
            elif a.seed_text:
                seed = (a.seed_text + "\n").encode("utf-8")
            else:
                raise ActivityError(f"activity {a.id}: an activity of engine={a.engine} needs its data - "
                                    f"seed=<file> or \\seed{{...}}")
            if len(seed) > SEED_MAX:
                raise ActivityError(f"activity {a.id}: the seed has {len(seed) // 1024} KB - at most "
                                    f"{SEED_MAX // 2**20} MB, which the presenter's browser loads")
            entry["seed"] = content_name("data", seed, next(iter(engine["seed"])))
            files[entry["seed"]] = seed
            references = list(a.references)
            if a.reference_file:
                references.append(_text(a, folder, a.reference_file, "reference").strip())
            for r in references:
                if not r or len(r) > QUERY_MAX:
                    raise ActivityError(f"activity {a.id}: a reference has 1 to {QUERY_MAX} characters")
            if references:
                keys[a.id] = {"reference": references}
            unused = [k for k, v in (("fields", a.fields != ["Subject", "Predicate", "Object"] and a.fields),
                                     ("suggest", a.suggest), ("min", a.min), ("review", a.review),
                                     ("terms", a.terms)) if v]
        if unused:
            warnings.append(f"activity {a.id}: {', '.join(unused)} - not for input={a.input}")
        if a.open == "manual":
            entry["open"] = "manual"
        prompt = phone.get(f"{NAME}:{a.id}", {}).get("prompt")
        if prompt is not None:
            entry["prompt"] = prompt
        items[a.id] = entry
    return items, keys, files


def check_slides(slides) -> None:
    """One activity per slide (texactivity.sty refuses two in a frame)."""
    for s in slides:
        found = [b["item"] for b in s.live if b["type"] == NAME]
        if len(found) > 1:
            raise ActivityError(f"page {s.page}: activities {', '.join(found)} on one slide - one per frame")
