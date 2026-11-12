# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What the checks share (docs/architecture/activity-framework-plan.md, 4.3) - as the browser's engines
had it in web/engines/common.js, byte for byte, so that the server's keys are the browser's: the key of
a result's canonical form, a summary that fits into a message, a value cut for it. And the parts of
JavaScript the canonical forms were written in: its numbers as `String` writes them, its strings as
`JSON.stringify` does, its sort - by UTF-16 code units -, its lengths in UTF-16 code units.

    key(canonical)        64-bit FNV-1a of the canonical form's UTF-8, 16 hex digits
    bounded(summary)      the summary with fewer rows until its JSON has at most 11,000 characters
    cut(text)             a value as a summary shows it: at most CELL characters
    compare(rows, ref)    a result's rows against the reference's: in both, missing, more

And a check's budget of CPU time, which an engine's stream is read under (deadline, collected).
"""
from __future__ import annotations

import collections
import decimal
import math
import re
import time

ROWS = 20                       # rows in a summary
CELL = 120                      # characters of a value in it
SUMMARY_MAX = 11000             # characters of its JSON (JSON.stringify's length)
NESTING_MAX = 500               # brackets deep: beyond, a SPARQL or Turtle text is a syntax error (F0, Q3)
_BRACKETS = re.compile(r"[(){}\[\]]")
JS_SPACE = "[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"   # JavaScript's \s


# ------------------------------------------------------------------ JavaScript's strings
def well_formed(s: str) -> str:
    """The string as TextEncoder reads a JavaScript string: a surrogate pair as its character, a lone
    surrogate as U+FFFD - as a text went into the browser's Oxigraph, and as no engine here takes one."""
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def nesting(text: str) -> int:
    """How deep the text's parentheses, braces and brackets nest - in strings and comments too: a bound.
    pyoxigraph's parsers recurse, and 800 groups end a process with the default stack (F0, Q3); a worker
    checks on a thread with a large one, and the checks refuse more than NESTING_MAX before any parser."""
    depth = deepest = 0
    for m in _BRACKETS.finditer(text):
        if m.group() in "({[":
            depth += 1
            deepest = max(deepest, depth)
        elif depth:
            depth -= 1
    return deepest


# ------------------------------------------------------------------ comments
# An IRI as SPARQL and Turtle write one: no space, none of <>"{}|^`\ - but \u and \U escapes.
IRI = re.compile(r"""<(?:[^\x00-\x20<>"{}|^`\\]|\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8})*>""")
MARKS = re.compile(r"""[#\\'"<\n\r]""")


def hash_comments(text: str, less_than: bool = False) -> list[tuple[int, int]]:
    """Where a SPARQL or Turtle text's comments are - each from its # to its line's end, as (start, end) -,
    for a kind's normalize, which takes them out. A # is none in a string, in an IRI - <http://x#y> -
    and behind a backslash (ex:a\\#b).

    Only what is a comment however the text is read counts, so that a text without them is checked as
    the text with them. less_than (SPARQL): a < may be the comparison and not an IRI's start, which only
    the parser knows - Oxigraph reads FILTER(?a<?b#c> as a comparison and a comment -, so the text is
    read both ways at once, and a # is a comment where every reading says so: in `?s <http://x#y> ?o # c`
    the last one. A reading ends where no text can go on - a line's end in a short string -; where none
    is left, the rest is left as it is."""
    if "#" not in text:
        return []
    states = {("code", 0)}                  # the readings: (code, # - a comment -, a string's quotes; read from)
    sure, start = [], None
    for mark in MARKS.finditer(text):       # between these characters no reading changes
        i, c = mark.start(), mark.group()
        after, comment = set(), True
        for mode, since in states:
            if i < since:                                   # inside what this reading took whole
                after.add((mode, since))
                comment = False
            elif mode == "#":
                if c in "\n\r":
                    after.add(("code", 0))
                    comment = False
                else:
                    after.add(("#", 0))
            elif mode == "code":
                if c == "#":
                    after.add(("#", 0))
                    continue
                comment = False
                if c == "\\":
                    after.add(("code", i + 2))
                elif c in "'\"":
                    after.add((c * 3, i + 3) if text.startswith(c * 3, i) else (c, 0))
                elif c == "<" and (m := IRI.match(text, i)):
                    after.add(("code", m.end()))
                    if less_than:
                        after.add(("code", 0))
                else:
                    after.add(("code", 0))
            else:                                           # a string, short or long
                comment = False
                if c == "\\":
                    after.add((mode, i + 2))
                elif text.startswith(mode, i):
                    after.add(("code", i + len(mode)))
                elif c not in "\n\r" or len(mode) == 3:
                    after.add((mode, 0))
        if comment and start is None:
            start = i
        elif not comment and start is not None:
            sure.append((start, i))
            start = None
        if not after:
            return sure
        states = {(mode, since if since > i + 1 else 0) for mode, since in after}
    if start is not None:
        sure.append((start, len(text)))
    return sure


def deadline(budget_s: float | None) -> float | None:
    """When a check's budget ends, in its thread's CPU time (time.thread_time) - None, no budget."""
    return None if budget_s is None else time.thread_time() + budget_s


def collected(items, end: float | None) -> list | None:
    """An engine's stream - solutions, triples - read whole, or None once the check's CPU time passed its
    end first: read between items, every 16 of them, as F0 stopped SPARQL (Q2). What gives no item until
    it is done - an ORDER BY, a COUNT - the pool's watchdog stops, by ending the worker."""
    if end is None:
        return list(items)
    out = []
    for x in items:
        out.append(x)
        if not len(out) & 15 and time.thread_time() > end:
            return None
    return out


def mapped(items, f, end: float | None) -> list | None:
    """f of each item - a solution, a triple, written as a row -, or None once the check's CPU time passed
    its end: the check's Python work counts against its budget too."""
    out = []
    for x in items:
        out.append(f(x))
        if end is not None and not len(out) & 255 and time.thread_time() > end:
            return None
    return out


def message(e: BaseException) -> str:
    """An exception's message, its first line - a SyntaxError's without the " (line n)" Python adds to it."""
    text = e.msg if isinstance(e, SyntaxError) and e.msg is not None else e
    return str(text).split("\n")[0]


# Written with chr(): a raw astral or surrogate character in the source is easily lost. Regular expressions,
# not loops over characters, so that a value of many megabytes takes milliseconds, not seconds (package 3's
# review: a check's Python work counts against its budget).
_ASTRAL = re.compile(f"[{chr(0x10000)}-{chr(0x10FFFF)}]")
_JSON_ESCAPE = re.compile(f'[\\x00-\\x1f"\\\\{chr(0xD800)}-{chr(0xDFFF)}]')


def _astral(s: str) -> bool:
    """Whether a character beyond U+FFFF is in it - at once for ASCII, which Python knows without looking."""
    return not s.isascii() and _ASTRAL.search(s) is not None


def utf16_len(s: str) -> int:
    """A string's length as JavaScript counts it: in UTF-16 code units."""
    return len(s) if s.isascii() else len(s) + len(_ASTRAL.findall(s))


def js_sorted(items) -> list[str]:
    """Sorted as JavaScript's Array.prototype.sort sorts strings: by UTF-16 code units - which is Python's
    own order of code points unless a character beyond U+FFFF is among them."""
    items = list(items)
    if any(_astral(s) for s in items):
        return sorted(items, key=lambda s: s.encode("utf-16-be", "surrogatepass"))
    return sorted(items)


def cut(s: str) -> str:
    """At most CELL characters, the last of a longer one an ellipsis (common.js: cut) - counted and cut in
    UTF-16 code units, so that an emoji may be cut in half, as JavaScript cuts it."""
    if len(s) <= CELL and utf16_len(s) <= CELL:
        return s
    units = s[:CELL].encode("utf-16-le", "surrogatepass")[: (CELL - 1) * 2]   # CELL characters: CELL units or more
    return units.decode("utf-16-le", "surrogatepass") + "…"


_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _json_escaped(m: re.Match) -> str:
    c = m.group()
    return _ESCAPES.get(c) or f"\\u{ord(c):04x}"


def js_quote(s: str) -> str:
    """A string as JSON.stringify writes it: quotes and backslashes escaped, the control characters, and
    a lone surrogate (ES2019's well-formed JSON.stringify); everything else as it is."""
    return '"' + _JSON_ESCAPE.sub(_json_escaped, s) + '"'


def js_stringify(v) -> str:
    """JSON.stringify of a summary: objects, arrays, strings, integers, booleans, null - no spaces."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return js_number(float(v)) if abs(v) > 2**53 else str(v)
    if isinstance(v, float):
        return js_number(v) if math.isfinite(v) else "null"
    if isinstance(v, str):
        return js_quote(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(js_stringify(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{js_quote(k)}:{js_stringify(x)}" for k, x in v.items()) + "}"
    raise TypeError(f"not in a summary: {type(v).__name__}")


# ------------------------------------------------------------------ JavaScript's numbers
_CONTEXT = decimal.Context(prec=60, Emax=999_999, Emin=-999_999)


def js_number(x: float) -> str:
    """A number as JavaScript's String(x) writes it (ECMAScript Number::toString): the shortest digits that
    give x back - as Python's repr -, then 1e+21 and 1e-7 written with an exponent, 100 and 0.000001 not."""
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    d = decimal.Decimal(repr(abs(x))).as_tuple()
    digits = "".join(map(str, d.digits))
    stripped = digits.rstrip("0") or "0"
    k = len(stripped)
    n = d.exponent + (len(digits) - k) + k          # x = 0.stripped * 10**n
    if k <= n <= 21:
        body = stripped + "0" * (n - k)
    elif 0 < n <= 21:
        body = stripped[:n] + "." + stripped[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + stripped
    else:
        e = n - 1
        mantissa = stripped if k == 1 else stripped[0] + "." + stripped[1:]
        body = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


def js_precision(x: float, digits: int) -> float:
    """Number(x.toPrecision(digits)): x rounded to that many significant digits - a tie away from zero,
    as toPrecision rounds -, read back as a number."""
    if x == 0 or not math.isfinite(x):
        return x
    d = decimal.Decimal(x)                          # exactly x
    q = decimal.Decimal(1).scaleb(d.adjusted() - digits + 1, _CONTEXT)
    return float(d.quantize(q, rounding=decimal.ROUND_HALF_UP, context=_CONTEXT))


def js_digits(x: float, digits: int) -> str:
    """An engine's number: an integer, Infinity or NaN as String writes it, any other number to that many
    significant digits (sql.js's `number`, web/engines/sql.js)."""
    if not math.isfinite(x) or x.is_integer():
        return js_number(x)
    return js_number(js_precision(x, digits))


# ------------------------------------------------------------------ what the browser's common.js did
def key(canonical: str, end: float | None = None) -> str | None:
    """The result's key: 64-bit FNV-1a over the canonical form's UTF-8 - a lone surrogate as U+FFFD, as
    TextEncoder writes it. With end, a check's budget (deadline): None once it passes - FNV-1a goes byte
    by byte, about 9 MB a second in Python, and a large result's key counts against its check's budget."""
    try:
        data = canonical.encode("utf-8")
    except UnicodeEncodeError:
        data = well_formed(canonical).encode("utf-8")
    h, view = 0xCBF29CE484222325, memoryview(data)
    for start in range(0, len(view), 1 << 18):          # a quarter MB: some 30 ms between looks at the clock
        if end is not None and time.thread_time() > end:
            return None
        for byte in view[start:start + (1 << 18)]:
            h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def bounded(summary: dict) -> dict:
    """The summary with fewer rows until its JSON has at most SUMMARY_MAX characters."""
    while summary.get("rows") and utf16_len(js_stringify(summary)) > SUMMARY_MAX:
        summary["rows"] = summary["rows"][:-1]
    return summary


def compare(rows: list[str], reference: list[str]) -> dict:
    """A result's rows - a bag - against the reference's: how many are in both, how many of the
    reference's are missing, how many more there are (common.js: compare) - the summary's diff, which
    the presenter window's evaluator added to every result after the first reference's."""
    counts = collections.Counter(reference)
    common = 0
    for r in rows:
        if counts[r]:
            common += 1
            counts[r] -= 1
    return {"common": common, "missing": len(reference) - common, "extra": len(rows) - common}
