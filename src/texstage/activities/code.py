# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What three of today's four kinds share (F2's plan, 4.2) - sql-query, sparql-query, turtle-graph: a
student's text, checked against a seed with one of F1's engines (texstage.checks: load, evaluate, and
for SQL image), grouped by the key of its result's canonical form, shown with a summary and compared
with the first reference's rows. Provisional, as the contract is (kind.py): whether such a base is the
contract's, a helper beside it, or each package's own is package 2's to say.

A kind of this shape names its engine's module and what the engines' table (texstage/engines.py) says
of it: the files a seed may be, the tokens its bar always offers, what it calls a student's text."""
from __future__ import annotations

import importlib
import time
from pathlib import Path
from types import MappingProxyType

from texstage.activities.kind import FROM_F1, Built, Check, Entry, Kind, Prepared, Step, Unbuildable, words
from texstage.checks import cleaning, common

SEED_MAX = 2 * 2**20                       # as the build has it: the presenter's browser loaded it
QUERY_MAX = 2000                           # a reference: as long as a student's text may be


class CodeKind(Kind):
    INPUT = "code"
    REDUCTION = "groups"
    OPTIONS = MappingProxyType({"seed": "file", "tokens": "words", "reference": "file"})
    LIMIT = 5
    ENGINE = ""                            # the deck's engine= (the item's "engine", until kinds are named)
    MODULE = ""                            # F1's check: load(seed, ...), evaluate(state, text, language, budget_s=)
    SEED: dict[str, str] = {}              # a seed's file types, each with its media type; the first is the bundle's
    TOKENS: list[str] = []                 # what the phone's bar offers beside the deck's
    TEXT = "a query"                       # a student's text, in a refusal's words

    @property
    def engine(self):
        return importlib.import_module(self.MODULE)

    # -------------------------------------------------------------- the build
    def build(self, options: dict, bodies: dict, files) -> Built:
        from texstage.build.bundle import content_name     # the build's, not a worker's
        tokens = words("tokens", list(options.get("tokens") or []))
        item = {"engine": self.ENGINE, "tokens": tokens + [t for t in self.TOKENS if t not in tokens]}
        name = options.get("seed")
        if name:
            if Path(name).suffix.lower() not in self.SEED:
                raise Unbuildable(f"the seed {name} - {self.ENGINE} takes {', '.join(self.SEED)} files")
            seed = files(name, "seed").encode("utf-8")
        elif bodies.get("seed"):
            seed = (bodies["seed"] + "\n").encode("utf-8")
        else:
            raise Unbuildable(f"an activity of engine={self.ENGINE} needs its data - seed=<file> or \\seed{{...}}")
        if len(seed) > SEED_MAX:
            raise Unbuildable(f"the seed has {len(seed) // 1024} KB - at most {SEED_MAX // 2**20} MB, which the "
                              f"presenter's browser loads")
        item["seed"] = content_name("data", seed, next(iter(self.SEED)))
        references = list(bodies.get("references") or [])
        if options.get("reference"):
            references.append(files(options["reference"], "reference").strip())
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

    def check(self, prepared: Prepared, step: Step, entry: Entry) -> Check:
        """As a worker of F1's pool checks a text (server/worker.py: _evaluate, _outcome): whatever the
        engine raises is this text's error; the key's computing counts against the budget. An entry
        without a text is not the student's error but the core's: TypeError."""
        if not isinstance(entry.text, str):
            raise TypeError(f"{self.NAME} checks a text, not {entry!r}")
        end = None if step.budget_s is None else time.thread_time() + step.budget_s
        try:
            result = self.engine.evaluate(prepared.state, common.well_formed(entry.text), step.language,
                                          budget_s=step.budget_s)
        except MemoryError:
            return Check("error", message="out of memory", memory=True)
        except Exception as e:  # noqa: BLE001 - the engine's failure is the text's error, not the worker's
            return Check("error", message=str(e).split("\n")[0] or type(e).__name__)
        check = Check(FROM_F1.get(result["status"], result["status"]), message=result.get("error"),
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
            check.detail["diff"] = common.compare(result["rows"], prepared.rows)
        return check
