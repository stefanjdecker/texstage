# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""F0's checks: SQL with Python's sqlite3, SPARQL and Turtle with pyoxigraph (activity-framework-plan.md,
3.3) - today's statuses, keys and summaries (LA section 8.3), close to the browser's but not byte for byte:
that is F1's work (plan, 4.3). A worker of the pool (pool.py) runs them, one text at a time.

    state = prepare(engine, seed_text, references)    # once per worker and activity
    result = check(engine, state, text, budget_s)     # {status, key, error?, rows?}

Statuses as today: ok, syntax, error, timeout, refused (server/activity.py:75).
"""
from __future__ import annotations

import re
import sqlite3
import time

ROWS_MAX = 100_000                  # more is an error (LA 8.8)
TRIPLES_MAX = 10_000                # a Turtle text (LA 8.9)
NESTING_MAX = 500                   # braces or parentheses deep: a syntax error, before any parser sees it
ERROR_MAX = 300
HEAP_ALLOWANCE = 256 * 2**20        # what one SQL text may take beyond its seed (plan 4.4; F0 sets it)


def key(canonical: str) -> str:
    """64-bit FNV-1a over UTF-8, as web/engines/common.js:39-46."""
    h = 0xCBF29CE484222325
    for byte in canonical.encode("utf-8"):
        h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def nesting(text: str) -> int:
    """How deep braces, brackets and parentheses nest, strings and comments not skipped (a bound)."""
    depth = deepest = 0
    for c in text:
        if c in "({[":
            depth += 1
            deepest = max(deepest, depth)
        elif c in ")}]" and depth:
            depth -= 1
    return deepest


class Budget:
    """A check's CPU time: the thread's own (time.thread_time), so that only this text counts."""

    def __init__(self, seconds: float):
        self.seconds, self.start = seconds, time.thread_time()

    def used(self) -> float:
        return time.thread_time() - self.start

    def over(self) -> bool:
        return self.used() > self.seconds


def _cut(e: BaseException) -> str:
    return str(e).splitlines()[0][:ERROR_MAX] if str(e) else type(e).__name__


# ------------------------------------------------------------------ SQL
LEADING = re.compile(r"^(?:\s+|--[^\n]*\n?|/\*.*?\*/)*", re.S)
QUERY = re.compile(r"(select|values|with)\b", re.I)
DENIED = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}


HEAP_BASE = 32 * 2**20              # SQLite's own caches beside the seeds
_SEEDS = {"bytes": 0}               # the pages of every seed this worker holds: the cap is per process


def _sql_prepare(seed: str, references: list[str]) -> dict:
    con = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    con.executescript(seed)
    _SEEDS["bytes"] += con.execute("PRAGMA page_count").fetchone()[0] * con.execute("PRAGMA page_size").fetchone()[0]
    limit = _SEEDS["bytes"] + HEAP_BASE + HEAP_ALLOWANCE
    con.execute(f"PRAGMA hard_heap_limit = {limit}")      # before the authorizer refuses PRAGMA (AF 11)
    con.execute("PRAGMA temp_store = MEMORY")              # else a large sort spills to temporary files,
    con.execute("PRAGMA query_only = ON")                  # past the cap (F0's review)
    con.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in DENIED else sqlite3.SQLITE_OK)
    state = {"con": con, "heap_limit": limit}
    state["refs"] = [_sql_check(state, r, 10.0).get("key") for r in references]
    return state


def _sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool | int):
        return f"n:{int(v)}"
    if isinstance(v, float):
        return f"n:{int(v)}" if v.is_integer() else f"n:{float(f'{v:.15g}')!r}"
    if isinstance(v, bytes):
        return "x:" + v.hex()
    return "t:" + repr(v)


def _sql_check(state: dict, text: str, budget_s: float) -> dict:
    con: sqlite3.Connection = state["con"]
    body = text[LEADING.match(text).end():]
    if not body.strip():
        return {"status": "syntax", "key": "syntax", "error": "no statement"}
    if not QUERY.match(body):
        return {"status": "refused", "key": "refused", "error": "only one query: SELECT, VALUES or WITH"}
    budget = Budget(budget_s)
    con.set_progress_handler(lambda: 1 if budget.over() else 0, 10_000)
    try:
        cur = con.execute(text)
        rows = cur.fetchmany(ROWS_MAX + 1)
        if len(rows) > ROWS_MAX:
            return {"status": "error", "key": "error", "error": f"more than {ROWS_MAX} rows"}
        ncols = len(cur.description or ())
    except sqlite3.ProgrammingError as e:                 # two statements: Python's own refusal
        return {"status": "refused", "key": "refused", "error": _cut(e)}
    except sqlite3.OperationalError as e:
        msg = _cut(e)
        if msg == "interrupted":
            return {"status": "timeout", "key": "timeout", "cpu_s": budget.used()}
        if any(w in msg for w in ("syntax error", "incomplete input", "unrecognized token")):
            return {"status": "syntax", "key": "syntax", "error": msg}
        if "readonly" in msg or "not authorized" in msg:
            return {"status": "refused", "key": "refused", "error": msg}
        return {"status": "error", "key": "error", "error": msg, "memory": "out of memory" in msg}
    except MemoryError:                                   # SQLITE_NOMEM, as Python's sqlite3 raises it
        return {"status": "error", "key": "error", "error": "out of memory", "memory": True}
    except sqlite3.Error as e:
        return {"status": "error", "key": "error", "error": _cut(e)}
    finally:
        con.set_progress_handler(None, 0)
    canonical = f"select\n{ncols}\n" + "\n".join(sorted("\t".join(map(_sql_value, r)) for r in rows))
    return {"status": "ok", "key": key(canonical), "rows": len(rows), "cpu_s": budget.used()}


# ------------------------------------------------------------------ SPARQL and Turtle
PREFIX_LINE = re.compile(r"^\s*@?prefix\s+([\w.-]*):\s*<([^>]*)>\s*\.?\s*$", re.I | re.M)
BASE_LINE = re.compile(r"^\s*@?base\s+<([^>]*)>\s*\.?\s*$", re.I | re.M)
ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})")
# SPARQL's tokens, as far as a refusal of SERVICE needs them (SPARQL 1.1, section 19.8): strings, IRIs and
# comments skipped; variables and prefixed names whole - ?service, :service, ex:Service and the prefix
# service: are names, not the keyword; then words
TOKENS = re.compile(r"""'''.*?'''|\"\"\".*?\"\"\"|'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|<[^<>"{}|^`\\\s]*>|#[^\n]*"""
                    r"""|[?$][\w·̀-ͯ‿-⁀]+"""
                    r"""|(?:[^\W\d_][\w.\-·]*)?:[\w.\-:%\\]*"""
                    r"""|[^\W\d_]\w*""", re.S)
WORD = re.compile(r"[^\W\d_]\w*")
QUOTES = str.maketrans({c: '"' for c in "“”„‟«»"} | {c: "'" for c in "‘’‚‛"})


def decoded(text: str) -> str:
    """The text with SPARQL's codepoint escapes decoded, as the grammar says they are before parsing."""
    return ESCAPE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)), text)


def names_service(text: str) -> bool:
    """Whether the keyword SERVICE is in the query - a word of its own, not a part of a string, an IRI, a
    comment, a variable or a prefixed name - as written, or with its escapes decoded."""
    for t in (text, decoded(text)):
        for m in TOKENS.finditer(t):
            token = m.group(0)
            if WORD.fullmatch(token) and token.upper() == "SERVICE":
                return True
    return False


def _term(t) -> str:
    import pyoxigraph as ox
    if t is None:
        return "-"
    if isinstance(t, ox.NamedNode):
        return f"<{t.value}>"
    if isinstance(t, ox.BlankNode):
        return "_:"
    if isinstance(t, ox.Literal):
        if t.language:
            return f"{t.value!r}@{t.language.lower()}"
        return f"{t.value!r}^^<{t.datatype.value}>"
    return str(t)


def _rdf_prepare(seed: str, references: list[str]) -> dict:
    import pyoxigraph as ox
    store = ox.Store()
    store.load(seed, format=ox.RdfFormat.TURTLE)
    base = BASE_LINE.search(seed)
    state = {"store": store, "prefixes": PREFIX_LINE.findall(seed), "base": base.group(1) if base else None}
    state["refs"] = [_sparql_check(state, r, 10.0).get("key") for r in references]
    return state


def _completed(state: dict, text: str, turtle: bool) -> str:
    """The seed's prologue in front of the text, but for what the text declares itself (LA 8.6, 8.9)."""
    lines = []
    if state["base"] and not re.search(r"^\s*@?base\b", text, re.I | re.M):
        lines.append(f"@base <{state['base']}> ." if turtle else f"BASE <{state['base']}>")
    for name, iri in state["prefixes"]:
        if not re.search(rf"^\s*@?prefix\s+{re.escape(name)}:", text, re.I | re.M):
            lines.append(f"@prefix {name}: <{iri}> ." if turtle else f"PREFIX {name}: <{iri}>")
    return "\n".join(lines + [text])


def _sparql_check(state: dict, text: str, budget_s: float) -> dict:
    import pyoxigraph as ox
    if nesting(text) > NESTING_MAX:
        return {"status": "syntax", "key": "syntax", "error": "nested too deeply"}
    if names_service(text):
        return {"status": "refused", "key": "refused", "error": "SERVICE is not supported"}
    budget = Budget(budget_s)
    try:
        result = state["store"].query(_completed(state, text, False))
        if isinstance(result, ox.QueryBoolean):
            canonical = f"ask\n{'true' if bool(result) else 'false'}"
            n = 1
        elif isinstance(result, ox.QueryTriples):
            triples = []
            for t in result:
                triples.append(" ".join(map(_term, (t.subject, t.predicate, t.object))))
                if len(triples) % 200 == 0 and budget.over():
                    return {"status": "timeout", "key": "timeout", "cpu_s": budget.used()}
                if len(triples) > ROWS_MAX:
                    return {"status": "error", "key": "error", "error": f"more than {ROWS_MAX} triples"}
            canonical, n = "graph\n" + "\n".join(sorted(triples)), len(triples)
        else:
            variables = result.variables
            rows = []
            for sol in result:
                rows.append("\t".join(_term(sol[v]) for v in variables))
                if len(rows) % 200 == 0 and budget.over():
                    return {"status": "timeout", "key": "timeout", "cpu_s": budget.used()}
                if len(rows) > ROWS_MAX:
                    return {"status": "error", "key": "error", "error": f"more than {ROWS_MAX} rows"}
            canonical, n = f"select\n{len(variables)}\n" + "\n".join(sorted(rows)), len(rows)
    except SyntaxError as e:
        return {"status": "syntax", "key": "syntax", "error": _cut(e)}
    except Exception as e:  # noqa: BLE001 - the engine's failure is the student's error
        return {"status": "error", "key": "error", "error": _cut(e)}
    return {"status": "ok", "key": key(canonical), "rows": n, "cpu_s": budget.used()}


def _turtle_prepare(seed: str, references: list[str]) -> dict:
    base = BASE_LINE.search(seed)
    state = {"prefixes": PREFIX_LINE.findall(seed), "base": base.group(1) if base else None}
    state["refs"] = [_turtle_check(state, r, 10.0).get("key") for r in references]
    return state


def _turtle_check(state: dict, text: str, budget_s: float) -> dict:
    import pyoxigraph as ox
    if nesting(text) > NESTING_MAX:
        return {"status": "syntax", "key": "syntax", "error": "nested too deeply"}
    budget = Budget(budget_s)
    try:
        triples = set()
        for t in ox.parse(_completed(state, text.translate(QUOTES), True), format=ox.RdfFormat.TURTLE):
            triples.add(" ".join(map(_term, (t.subject, t.predicate, t.object))))
            if len(triples) > TRIPLES_MAX:
                return {"status": "error", "key": "error", "error": f"more than {TRIPLES_MAX} triples"}
            if len(triples) % 200 == 0 and budget.over():
                return {"status": "timeout", "key": "timeout", "cpu_s": budget.used()}
    except SyntaxError as e:
        return {"status": "syntax", "key": "syntax", "error": _cut(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "key": "error", "error": _cut(e)}
    if not triples:
        return {"status": "syntax", "key": "syntax", "error": "no triples"}
    return {"status": "ok", "key": key("graph\n" + "\n".join(sorted(triples))), "rows": len(triples),
            "cpu_s": budget.used()}


# ------------------------------------------------------------------ the engines
ENGINES = {
    "sql": (_sql_prepare, _sql_check),
    "sparql": (_rdf_prepare, _sparql_check),
    "turtle": (_turtle_prepare, _turtle_check),
}


def prepare(engine: str, seed: str, references: list[str] | None = None) -> dict:
    return ENGINES[engine][0](seed, references or [])


def check(engine: str, state: dict, text: str, budget_s: float = 2.0) -> dict:
    return ENGINES[engine][1](state, text, budget_s)
