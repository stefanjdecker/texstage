# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The SQL check (web/engines/sql.js in Python; docs/live-activities-design.md, section 8.8): SQLite - Python's
sqlite3 - over the activity's seed, a script of CREATE TABLE and INSERT statements.

A text is one statement - SELECT, VALUES or WITH ... SELECT -; anything else is refused, and the database
is read-only besides (PRAGMA query_only): no query changes what the next one sees. The same result, the
same canonical form, as sql.js wrote it: the rows as a bag - their order does not count, repeated rows do
-, the columns in the order the query gives them, their names not; a number by its value, as JavaScript
read it from SQLite (7 and 7.0 alike, an integer beyond 2**53 rounded as a double, a fraction to 15
significant digits), a text as sql.js read it (up to a NUL, an ill-formed byte as U+FFFD: _text), NULL, a
blob by its bytes.

    state = load(seed, heap_allowance=None, image=None)
    data = image(state, most)                       # the database as the seed left it, or None
    result = evaluate(state, text, language, budget_s=None)

In the pool, one process runs the seed and every other loads a copy of the database that run left (image,
load's image) - else a seed with random(), randomblob() or the time gives each process data of its own,
and one query a result of its own on each (2026-11-10). A copy is the database alone: the seed's PRAGMA
statements, which hold for their connection only, run again over it - on the first process too, which
checks on a copy as well. A seed that made TEMP objects or attached a database has no copy: every
process runs it.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
import warnings

from texstage.checks.common import JS_SPACE, ROWS, bounded, cut, deadline, js_digits, js_quote, js_sorted
from texstage.checks.texts import Words

MAX_ROWS = 100_000                     # more is an error, not a result: a join condition forgotten
HEAP_BASE = 32 * 2**20                 # SQLite's own caches beside the seeds, under its cap (F0, Q6)
# SQLite's tokenizer (tokenize.c): a run of spaces starts with one of five and goes on with \v too; a byte order
# mark is a space; a comment ends at its first */ or with the text - but "/*" at the very end is a slash.
# Possessive (*+): a run within a repetition would otherwise be split every possible way when what follows
# does not match - 26 spaces in front of a query took 6.6 s -; each separator's first character decides it,
# so giving nothing back changes no result.
SPACE = "[ \t\n\f\r][ \t\n\v\f\r]*+|\ufeff"
COMMENT = r"--[^\n]*+|/\*(?:(?!\*/).)*+\*/|/\*(?:(?!\*/).)++\Z"
QUERY = re.compile(r"(?:select|values|with)\b", re.I | re.A)
LEADING = re.compile(rf"(?:{JS_SPACE}++|--[^\n]*+(?:\n|\Z)|/\*.*?(?:\*/|\Z))*+", re.S)   # sql.js's LEADING
SEPARATORS = re.compile(rf"(?:{SPACE}|{COMMENT}|;)*+", re.S)                    # what SQLite finds no statement
EXPLAIN = re.compile(rf"(?:{SPACE}|{COMMENT})*+explain\b", re.S | re.I | re.A)


def _text(raw: bytes) -> str:
    """A text value as sql.js read it: sqlite3_column_text as a C string - up to its first NUL -, decoded
    by the browser's TextDecoder: an ill-formed sequence as U+FFFD, a leading byte order mark dropped."""
    s = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    return s[1:] if s.startswith("\ufeff") else s


_HEAP: list = []                        # [(sqlite3_hard_heap_limit64, sqlite3_memory_used) or None], once found


def _heap():
    """SQLite's sqlite3_hard_heap_limit64 and sqlite3_memory_used through ctypes, in the library Python's
    sqlite3 runs on - checked: a cap set through it is the one PRAGMA hard_heap_limit reads -, or None."""
    if not _HEAP:
        _HEAP.append(_find_heap())
    return _HEAP[0]


def _find_heap():
    import ctypes
    import ctypes.util
    try:
        import _sqlite3
        module = getattr(_sqlite3, "__file__", None)
    except ImportError:
        module = None
    paths = []
    if module:                          # Windows: sqlite3.dll beside _sqlite3.pyd; elsewhere the module itself,
        paths.append(os.path.join(os.path.dirname(module), "sqlite3.dll") if sys.platform == "win32"
                     else module)        # whose symbols are found in the library it links to
    found = ctypes.util.find_library("sqlite3")
    if found:
        paths.append(found)
    probe = sqlite3.connect(":memory:")
    try:
        for path in paths:
            try:
                lib = ctypes.CDLL(path)
                limit, used = lib.sqlite3_hard_heap_limit64, lib.sqlite3_memory_used
            except (OSError, AttributeError):
                continue
            limit.restype, limit.argtypes = ctypes.c_int64, [ctypes.c_int64]
            used.restype, used.argtypes = ctypes.c_int64, []
            before = limit(-1)
            limit(2**62)
            same = probe.execute("PRAGMA hard_heap_limit").fetchone()[0] == 2**62
            limit(before)
            if same:
                return limit, used
    finally:
        probe.close()
    return None


def load(seed: str, heap_allowance: int | None = None, image: bytes | None = None) -> dict:
    """The seed run into a database of its own, read-only from then on - or, given image, the database
    another run of the seed left (image()), the seed's PRAGMA statements run again over it. Its temporary
    storage is in memory, as sql.js's was - else a large sort spills to files, past the heap's cap (F0) -,
    set before the seed runs and once more after it, for a seed that set another: SQLite drops every TEMP
    object as the setting changes, and set only after the seed it dropped the seed's (2026-11-10).

    heap_allowance, in a worker of the pool: SQLite's cap on its heap, which holds for all of a process's
    connections - at what SQLite holds once the seed is in, every other seed of the process with it,
    HEAP_BASE for its own caches, and the allowance for a text. It is set through SQLite's own function
    (_heap), which raises it as well; while a seed loads there is none - the pool's watchdog and job
    object hold that. Where ctypes cannot reach the SQLite Python runs on, PRAGMA hard_heap_limit, which
    only lowers it: the first seed sets it, and later ones take from the allowance (the second review: a
    smaller seed after a larger one set it below what the larger one held, and no text ran)."""
    heap = _heap() if heap_allowance else None
    if heap is not None:
        heap[0](0)                                      # none while the seed loads
    try:
        con = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        con.text_factory = _text
        con.execute("PRAGMA temp_store = MEMORY")
        size = None
        try:
            if image is None:
                con.executescript(seed)
                size = _copyable(con)
            else:
                con.deserialize(image)
                con.execute("SELECT count(*) FROM sqlite_master").fetchone()      # a database it is
                pragmas = _pragmas(seed)
                if pragmas:
                    con.executescript("".join(s if s.endswith(";") else s + "\n;" for s in pragmas))
        except (sqlite3.Error, MemoryError) as e:
            con.close()
            what = "the seed" if image is None else "the copy of its database"
            raise ValueError(f"{what}: {'out of memory' if isinstance(e, MemoryError) else e}") from None
        con.execute("PRAGMA temp_store = MEMORY")
        if heap_allowance and heap is None:
            row = con.execute("PRAGMA hard_heap_limit").fetchone()
            if row is not None and not row[0]:
                pages = con.execute("PRAGMA page_count").fetchone()[0] * con.execute("PRAGMA page_size").fetchone()[0]
                con.execute(f"PRAGMA hard_heap_limit = {pages + HEAP_BASE + int(heap_allowance)}")
        con.execute("PRAGMA query_only = ON")
        con.set_authorizer(_compiling)
    finally:
        if heap is not None:
            limit, used = heap
            limit(used() + HEAP_BASE + int(heap_allowance))
    return {"con": con, "size": size}


def _copyable(con: sqlite3.Connection) -> int | None:
    """The database's size in bytes, when a copy of it is all the seed made - nothing in TEMP, no database
    attached, which a copy of the main database would lack -, else None."""
    if not hasattr(con, "serialize"):                   # Python's sqlite3 without SQLite's serialize API
        return None
    if con.execute("SELECT count(*) FROM temp.sqlite_master").fetchone()[0]:
        return None
    if any(row[1] not in ("main", "temp") for row in con.execute("PRAGMA database_list")):
        return None
    return con.execute("PRAGMA page_count").fetchone()[0] * con.execute("PRAGMA page_size").fetchone()[0]


def image(state: dict, most: int) -> bytes | None:
    """The database as the seed left it, for another process to load in the seed's place (load) - or None:
    the seed made more than the database (_copyable), the database is larger than most bytes, or it cannot
    be copied. The copy takes as much again while it is made: SQLite's cap is lifted meanwhile, and the
    authorizer steps aside - SQLite reads PRAGMA page_count as it copies, which _compiling makes nothing."""
    size = state.get("size")
    if size is None or size > most:
        return None
    con: sqlite3.Connection = state["con"]
    heap = _HEAP[0] if _HEAP else None
    before = heap[0](-1) if heap is not None else None  # a negative cap reads it
    if heap is not None:
        heap[0](0)
    con.set_authorizer(None)
    try:
        return con.serialize()
    except (sqlite3.Error, MemoryError):
        return None
    finally:
        con.set_authorizer(_compiling)
        if heap is not None:
            heap[0](before)


def _idchar(c: str) -> bool:
    """A character SQLite allows in a name (tokenize.c, IdChar): a letter, a digit, _, $, any non-ASCII."""
    return c.isascii() and (c.isalnum() or c in "_$") or not c.isascii()


def _lex(text: str):
    """SQLite's tokens as far as the check needs them (tokenize.c): each word - a name, a keyword, a
    number -, each semicolon and each comment, as (kind, start, end). Strings, quoted names and
    parameters are skipped whole - $a(x;y) is one parameter -, and a byte order mark where a token starts
    is a space. A comment is -- to its line's end, or /* to the first */ or the text's end - but "/*" as
    the text's last two characters is a slash and a star. web/engines/sql.js reads a text alike
    (namesPragma)."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "$@:#":                                # a parameter, with SQLite's (TCL's) a(...) and a::b
            j, letters = i + 1, 0
            while j < n:
                if _idchar(text[j]):
                    j, letters = j + 1, letters + 1
                elif text[j] == "(" and letters:
                    j += 1
                    while j < n and text[j] not in " \t\n\v\f\r)":
                        j += 1
                    j += j < n and text[j] == ")"
                    break
                elif text.startswith("::", j):
                    j += 2
                else:
                    break
            i = j
        elif c == "\ufeff":
            i += 1
        elif _idchar(c):                               # a name, a keyword, a number: one word
            j = i + 1
            while j < n and _idchar(text[j]):
                j += 1
            yield "word", i, j
            i = j
        elif c in "'\"`":
            j = i + 1
            while True:
                j = text.find(c, j)
                if j == -1 or j + 1 >= n or text[j + 1] != c:
                    break
                j += 2                                 # a doubled quote inside
            i = n if j == -1 else j + 1
        elif c == "[":
            j = text.find("]", i + 1)
            i = n if j == -1 else j + 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            yield "comment", i, j
            i = j
        elif text.startswith("/*", i) and i + 2 < n:
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            yield "comment", i, j
            i = j
        elif c == ";":
            yield ";", i, i + 1
            i += 1
        else:
            i += 1


def statements(text: str) -> list[str]:
    """The text's statements, as SQLite reads them one after another: split at a semicolon outside a
    string, a quoted name, a comment and a parameter (_lex) - and outside a trigger's body
    (sqlite3.complete_statement) -, without the empty ones."""
    out, start = [], 0
    for kind, _, end in _lex(text):
        if kind == ";" and sqlite3.complete_statement(text[start:end]):
            out.append(text[start:end])
            start = end
    if start < len(text):
        out.append(text[start:])
    return [s for s in out if SEPARATORS.fullmatch(s) is None]


def names_pragma(text: str) -> bool:
    """Whether the keyword PRAGMA is in the text - a word of SQLite's own (_lex), in any case. SQLite
    carries out many pragmas as it compiles them, so such a text is refused before anything is compiled,
    by this check and by the browser's alike (web/engines/sql.js: namesPragma)."""
    return any(kind == "word" and text[i:j].isascii() and text[i:j].lower() == "pragma"
               for kind, i, j in _lex(text))


def comments(text: str) -> list[tuple[int, int]]:
    """Where the text's comments are, as SQLite reads it (_lex) - for the kind's normalize, which takes
    them out."""
    return [(i, j) for kind, i, j in _lex(text) if kind == "comment"]


def _first_word(statement: str) -> str:
    """A statement's first word (_lex), in lower case - "" for none."""
    for kind, i, j in _lex(statement):
        if kind != "comment":
            return statement[i:j].lower() if kind == "word" and statement[i:j].isascii() else ""
    return ""


PRAGMA_ANYWHERE = re.compile("pragma", re.I | re.A)


def _pragmas(seed: str) -> list[str]:
    """The seed's PRAGMA statements, in their order - split only where the word is in the seed at all:
    the split is Python's, 0.13 s a megabyte, where SQLite runs a seed of INSERTs in a fifth of that."""
    if PRAGMA_ANYWHERE.search(seed) is None:
        return []
    return [s for s in statements(seed) if _first_word(s) == "pragma"]


# ------------------------------------------------------------------ values
def _term(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return f"n:{js_digits(float(v), 15)}"     # sql.js read every number as a double
    if isinstance(v, bytes):
        return f"x:{v.hex()}"
    return f"t:{js_quote(str(v))}"


def _show(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return js_digits(float(v), 12)
    if isinstance(v, bytes):
        return cut(f"x'{v[:64].hex()}" + ("'" if len(v) <= 64 else ""))    # what is cut away is never written
    return cut(str(v))


class _Nulls(dict):
    """Every named parameter's value: NULL."""

    def __missing__(self, key):
        return None


_BINDINGS = re.compile(r"Incorrect number of bindings supplied\. The current statement uses (\d+)")
_NUMBERED = re.compile(r"Binding \d+ \('\?\d*'\) is a named parameter")      # ?2: Python 3.12.3's mistake
MIXED = "parameters with and without names in one statement"


def _execute(con: sqlite3.Connection, sql: str) -> sqlite3.Cursor:
    """con.execute(sql) with every parameter NULL, as sql.js ran a statement with its parameters unbound -
    which Python's sqlite3 refuses: named ones (:x, @x, $x, ?1) get a mapping, nameless ones (? and ?2 among
    them) a list, and both in one statement are an error, as Python 3.14 has them (3.12 and 3.13 warned)."""
    try:
        return con.execute(sql)
    except sqlite3.ProgrammingError as e:
        m = _BINDINGS.match(str(e))
        if not m:
            raise
        n = int(m.group(1))
    try:
        return con.execute(sql, _Nulls())
    except sqlite3.ProgrammingError:
        pass
    numbered = False
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        try:
            return con.execute(sql, [None] * n)
        except DeprecationWarning as e:                 # a named one among them - or ?2, which Python 3.12.3
            numbered = bool(_NUMBERED.match(str(e)))    # took for one (3.12.4 and 3.14 do not)
        except sqlite3.ProgrammingError:
            pass
    if numbered:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return con.execute(sql, [None] * n)
    raise sqlite3.ProgrammingError(MIXED)


_ATTACHING = (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH)


def _compiling(action, *args):
    """The authorizer while a text's statements are compiled, and at rest: a PRAGMA, an ATTACH or a DETACH
    compiles to nothing. SQLite carries out many pragmas as it compiles them - PRAGMA query_only = OFF
    among them, behind EXPLAIN too -, which would open the database to the texts after this one; sql.js,
    which compiled each statement to count them, let a text do just that until 2026-11-09. A text with
    the keyword PRAGMA is refused before it is compiled (names_pragma); this is the second guard."""
    return sqlite3.SQLITE_IGNORE if action == sqlite3.SQLITE_PRAGMA or action in _ATTACHING else sqlite3.SQLITE_OK


def _running(action, *args):
    """The authorizer while the one query runs: no ATTACH, no DETACH. A pragma's table-valued function -
    pragma_table_info('t') - reads as it did in sql.js: SQLite has them only for pragmas without effects."""
    return sqlite3.SQLITE_DENY if action in _ATTACHING else sqlite3.SQLITE_OK


# ------------------------------------------------------------------ evaluation
class _Capped(Exception):
    """SQLite ran into its heap's cap: the text's at once - SQLite counts alike in every process, so a
    fresh one comes to the same (the second review: the pool ended two workers for each such text)."""


def _step(cur: sqlite3.Cursor):
    """The next row, or None - SQLite's work: out of memory there, it is its cap."""
    try:
        return next(cur, None)
    except MemoryError:
        raise _Capped from None


def _failure(e: BaseException, W: Words) -> dict:
    if isinstance(e, MemoryError):                      # Python's memory, the job object's: the pool tries the
        return {"status": "error", "error": "out of memory", "memory": True}   # text once more, on a fresh process
    text = str(e).split("\n")[0]
    if "readonly database" in text:
        return {"status": "refused", "error": W.changesData}
    if re.search(r"syntax error|incomplete input|unrecognized token", text):
        return {"status": "syntax", "error": text}
    return {"status": "error", "error": text}


def evaluate(state: dict, text: str, language: str | None = None, budget_s: float | None = None) -> dict:
    con: sqlite3.Connection = state["con"]
    W = Words(language)
    text = text.split("\0", 1)[0]                       # sql.js gave SQLite the text as a C string
    if names_pragma(text):                              # before anything is compiled (_compiling)
        return {"status": "refused", "error": W.queriesOnly}
    found = statements(text)
    for s in found:                     # each compiled, none run (sql.js's iterateStatements) - behind EXPLAIN
        try:                            # and a comment, not a space, which would take a \v in front of s along
            _execute(con, s if EXPLAIN.match(s) else "EXPLAIN/**/" + s).fetchall()
        except MemoryError:
            return {"status": "error", "error": W.tooMuchMemory}       # SQLite's cap, as it compiles
        except sqlite3.Error as e:
            return _failure(e, W)
    if not found:
        return {"status": "syntax", "error": W.noStatement}
    if len(found) > 1:
        return {"status": "refused", "error": W.oneStatement}
    if not QUERY.match(LEADING.sub("", text, count=1)):
        return {"status": "refused", "error": W.queriesOnly}
    end = deadline(budget_s)                            # SQLite's work, and Python's with its rows
    if end is not None:
        con.set_progress_handler(lambda: 1 if time.thread_time() > end else 0, 10_000)
    con.set_authorizer(_running)
    cur = None
    try:
        try:
            cur = _execute(con, found[0])               # SQLite runs it to its first row
        except MemoryError:
            raise _Capped from None
        columns = [_text(d[0].encode("utf-8")) for d in cur.description or ()]
        rows, shown = [], []
        while (values := _step(cur)) is not None:
            if len(rows) == MAX_ROWS:
                return {"status": "error", "error": f"more than {MAX_ROWS} rows"}
            rows.append("\t".join(map(_term, values)))
            if len(shown) < ROWS:
                shown.append([_show(v) for v in values])
            if end is not None and not len(rows) & 63 and time.thread_time() > end:
                return {"status": "timeout"}
    except _Capped:
        return {"status": "error", "error": W.tooMuchMemory}
    except sqlite3.OperationalError as e:
        if end is not None and str(e) == "interrupted":
            return {"status": "timeout"}
        return _failure(e, W)
    except (sqlite3.Error, MemoryError) as e:
        return _failure(e, W)
    finally:
        if cur is not None:
            cur.close()                                 # a query stopped early lets go of its memory now
        con.set_authorizer(_compiling)
        if end is not None:
            con.set_progress_handler(None, 0)
    if end is not None and time.thread_time() > end:
        return {"status": "timeout"}
    rows = js_sorted(rows)
    if end is not None and time.thread_time() > end:
        return {"status": "timeout"}
    return {"status": "ok", "canonical": f"select\n{len(columns)}\n" + "\n".join(rows), "rows": rows,
            "summary": bounded({"kind": "select", "columns": [cut(c) for c in columns], "count": len(rows),
                                "rows": shown})}
