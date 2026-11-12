# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A base for kinds of one shape (the plan of F2, 4.2) - sql-query, sparql-query, turtle-graph: a
student's text, checked against a seed with one of F1's engines (texstage.checks: load, evaluate, and
for SQL image), grouped by the key of its result's canonical form, shown with a summary and compared
with the first reference's rows. It is no part of the contract (kind.py) but a helper beside it: a kind
of another shape - triples - does without, and a kind of this shape may.

A kind of this shape names its engine's module and what the engines' table (texstage/engines.py) says
of it: the files a seed may be, the tokens its bar always offers, what it calls a student's text. Its
messages are the engines' texts by their codes (checks/texts.py; web/i18n: engines), and `engine` for
what an engine says in its own words - SQLite's, Oxigraph's."""
from __future__ import annotations

import importlib
import time

from texstage.activities.kind import (
    ARGUMENT_MAX,
    COMPARED,
    FROM_F1,
    Built,
    Check,
    Entry,
    Kind,
    Message,
    Prepared,
    Step,
    Unbuildable,
    fixed,
)
from texstage.activities.options import File, Options, Words
from texstage.checks import cleaning, common, texts

SEED_MAX = 2 * 2**20                       # as the build has it: the presenter's browser loaded it
QUERY_MAX = 2000                           # a reference: as long as a student's text may be


def said(*codes: str):
    """A kind's MESSAGES from the engines' catalog: each code with what its text is made with, and
    `engine`, the engine's own words."""
    return fixed(engine=("text",), **{code: texts.arguments(code) for code in codes})


def words(message: Message | None, language: str | None = None) -> str | None:
    """A message in words, as F1's checks worded it on the server - for the tests, the kit and a window
    that cannot say codes yet; the phones say them themselves (the design's 7.4)."""
    if message is None:
        return None
    if message.code == "engine":
        return message.args["text"]
    return texts.ENGINES[texts.language(language)][message.code].format(**message.args)


class CodeKind(Kind):
    INPUT = "code"
    REDUCTION = "groups"
    OPTIONS = fixed(tokens=Words(), seed=File(), reference=File())
    MESSAGES = said()
    LIMIT = 5
    ENGINE = ""                            # the deck's engine= (the item's "engine", until kinds are named)
    MODULE = ""                            # F1's check: load(seed, ...), evaluate(state, text, language, budget_s=)
    SEED: dict[str, str] = {}              # a seed's file types, each with its media type; the first is the bundle's
    TOKENS: list[str] = []                 # what the phone's bar offers beside the deck's
    TEXT = "a query"                       # a student's text, in a refusal's words

    def __init__(self):
        """A kind is made once, and its engine is imported then: a kind whose engine's library is not
        installed cannot be made, and the registry lists it so - not as one that can be used."""
        if self.MODULE:
            importlib.import_module(self.MODULE)

    @property
    def engine(self):
        return importlib.import_module(self.MODULE)

    # -------------------------------------------------------------- the build
    def build(self, options: Options, bodies: dict) -> Built:
        from texstage.build.bundle import content_name     # the build's, not a worker's
        tokens = options["tokens"]
        item = {"engine": self.ENGINE, "tokens": tokens + [t for t in self.TOKENS if t not in tokens]}
        file = options["seed"]
        if file is not None:
            if file.suffix not in self.SEED:
                raise Unbuildable(f"the seed {file.name} - {self.ENGINE} takes {', '.join(self.SEED)} files")
            seed = file.text().encode("utf-8")
        elif bodies.get("seed"):
            seed = (bodies["seed"] + "\n").encode("utf-8")
        else:
            raise Unbuildable(f"an activity of engine={self.ENGINE} needs its data - seed=<file> or \\seed{{...}}")
        if len(seed) > SEED_MAX:
            raise Unbuildable(f"the seed has {len(seed) // 1024} KB - at most {SEED_MAX // 2**20} MB, which the "
                              f"presenter's browser loads")
        item["seed"] = content_name("data", seed, next(iter(self.SEED)))
        references = list(bodies.get("references") or [])
        if options["reference"] is not None:
            references.append(options["reference"].text().strip())
        for r in references:
            if not r or len(r) > QUERY_MAX:
                raise Unbuildable(f"a reference has 1 to {QUERY_MAX} characters")
        return Built(item, {"reference": references} if references else {}, {item["seed"]: seed})

    # -------------------------------------------------------------- a worker
    def seed(self, item: dict, files: dict[str, bytes]) -> str:
        """The seed's text as F1's server reads it from the bundle: UTF-8 - a byte order mark stays -, its
        line ends \\n. A seed that is not in the bundle, or not UTF-8, says so (F1's server called both
        "not in the bundle")."""
        data = files.get(item.get("seed"))
        if data is None:
            raise ValueError(f"the seed {item.get('seed')}: not in the bundle")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"the seed {item.get('seed')}: not UTF-8") from None
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def prepare(self, item: dict, keys: dict, files: dict[str, bytes], limits: dict | None = None,
                copy: bytes | None = None) -> Prepared:
        return Prepared(self.engine.load(self.seed(item, files)))

    def normalize(self, step: Step, entry: Entry) -> Entry:
        return Entry(text=cleaning.clean_code(entry.text, self.TEXT))

    def _message(self, error) -> Message | None:
        """An engine's error as a message: a text of the catalog by its code, anything else as the engine's
        own words - cut to what a message's argument may be."""
        if error is None:
            return None
        if isinstance(error, texts.Said) and error.code in self.MESSAGES:
            return Message(error.code, {k: v[:ARGUMENT_MAX] if isinstance(v, str) else v for k, v in error.args.items()})
        return Message("engine", {"text": str(error)[:ARGUMENT_MAX]})

    def check(self, prepared: Prepared, step: Step, entry: Entry) -> Check:
        """As a worker of F1's pool checks a text (server/worker.py: _evaluate, _outcome): whatever the
        engine raises is this text's error; the key's computing counts against the budget. An entry
        without a text is not the student's error but the core's: TypeError."""
        if not isinstance(entry.text, str):
            raise TypeError(f"{self.NAME} checks a text, not {entry!r}")
        end = None if step.budget_s is None else time.thread_time() + step.budget_s
        try:
            with texts.coded():                       # the engines' words with their codes
                result = self.engine.evaluate(prepared.state, common.well_formed(entry.text), step.language,
                                              budget_s=step.budget_s)
        except MemoryError:
            return Check("error", message=self._message("out of memory"), memory=True)
        except Exception as e:  # noqa: BLE001 - the engine's failure is the text's error, not the worker's
            return Check("error", message=self._message(str(e).split("\n")[0] or type(e).__name__))
        check = Check(FROM_F1.get(result["status"], result["status"]), message=self._message(result.get("error")),
                      memory=bool(result.get("memory")))
        if result.get("at"):
            check.at = tuple(result["at"])
        if result["status"] != "ok":
            return check
        check.key = common.key(result["canonical"], end)
        if check.key is None:
            return Check("timeout")
        check.canonical, check.rows = result["canonical"], result["rows"]
        check.detail = result["summary"]
        if prepared.rows is not None:
            check.detail[COMPARED] = common.compare(result["rows"], prepared.rows)
        return check
