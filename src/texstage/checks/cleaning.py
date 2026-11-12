# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a phone sent, made fit to check: a tuple's terms and a query's text as the activity type cleaned
them when it took them (server/activity.py until F2) - here, without the server, so that the kinds'
`normalize` is the same cleaning (docs/architecture/activity-framework-plan-f2.md, 4.2 and 4.7; the
design's section 17). Unfit says why an entry is refused, and the code the phone gets."""
from __future__ import annotations

import re
import unicodedata

TERM_MAX = 60                       # a term of a tuple
TEXT_MAX = 2000                     # a query

# the quotes a phone's keyboard makes of " and ' (iOS's smart punctuation: “Kant”, „Kant“, ‘Kant’)
DOUBLE_QUOTES, SINGLE_QUOTES = "“”„‟«»", "‘’‚‛"
LITERAL = re.compile("[\"'" + DOUBLE_QUOTES + SINGLE_QUOTES + r"].*|[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?|true|false", re.S)


class Unfit(ValueError):
    """An entry that is not checked: the message for people, `code` for the phone (game.py's codes)."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def _composed(characters) -> str:
    """The characters kept, composed (NFC) - after the control characters are out, not before: composed
    first, a letter and its accent with a soft hyphen between them stayed two characters and became one
    when the text was cleaned again, so that cleaning a clean text changed it (F2's package 1, its review)."""
    return unicodedata.normalize("NFC", "".join(characters))


def norm_term(text: str) -> str:
    """A term's key - as scoring.normalize_text groups open answers: case, accents and spacing do
    not matter (imported there it would make a cycle: scoring -> bundles -> types -> the activity)."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def term_key(text: str, item: dict) -> str:
    """A cleaned term's key in an activity: the term as written (terms=exact - also a deck built
    before the key), or its word-cloud key (terms=loose)."""
    return norm_term(text) if item.get("terms") == "loose" else text


def clean_term(text) -> str:
    """A term as the phone sent it, control characters out and spaces collapsed - and a string a
    phone's keyboard quoted typographically in the quotes Turtle writes: “Kant” and „Kant“ are
    "Kant", one literal whichever keyboard typed it (an apostrophe inside stays as it is)."""
    if not isinstance(text, str):
        raise Unfit("a field is text")
    text = " ".join(_composed(c for c in text if not unicodedata.category(c).startswith("C")).split())
    if text and text[0] in DOUBLE_QUOTES:
        text = "".join('"' if c in DOUBLE_QUOTES else c for c in text)
    elif text and text[0] in SINGLE_QUOTES:
        text = "".join("'" if c in SINGLE_QUOTES else c for c in text)
    if not 1 <= len(text) <= TERM_MAX or not norm_term(text):
        raise Unfit(f"every field has 1 to {TERM_MAX} characters", "field")
    return text


def is_literal(term: str) -> bool:
    """Whether a term is written as a literal, as Turtle writes one: a quoted string - with its
    language or datatype: "Kant"@de, "42"^^xsd:integer -, a number, true or false. Any other term
    names a resource: an IRI, a prefixed name, a blank node. (The crowd graph draws a literal as
    the slides do, as a box.)"""
    return bool(LITERAL.fullmatch(term))


def clean_code(text, what: str = "a query", top: bool = False) -> str:
    """A query (what: as the engine calls a student's text - texstage/engines.py) as typed: its
    lines (tabs and newlines kept, other control characters not), without spaces at their ends and
    blank lines around them. top: the blank lines in front stay - where an engine's error names a
    line, it is the line the student sees."""
    if not isinstance(text, str):
        raise Unfit(f"{what} is text")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _composed(c for c in text if c in "\n\t" or not unicodedata.category(c).startswith("C"))
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = text.rstrip("\n") if top else text.strip("\n")
    if not text.strip() or len(text) > TEXT_MAX:
        raise Unfit(f"{what} has 1 to {TEXT_MAX} characters", "text")
    return text


GONE = "\0"                         # where a comment was: no cleaned text has one
GAP = re.compile(f"(?:{GONE}[ \t]*)+")


def _gap(m: re.Match) -> str:
    """What stands where comments were, in a line: a space where they parted two words - SELECT/**/1 -,
    none behind a space or at the line's start (one at its end goes with the line's other spaces)."""
    before = m.string[m.start() - 1:m.start()]
    return " " if before and before not in " \t" else ""


def uncommented(text: str, comments, what: str = "a query", lines: bool = False) -> str:
    """A cleaned text (clean_code) without its comments - comments: where they are, (start, end) in their
    order, as the engine's own reading finds them. A group is shown by such a text, and a vote puts it on
    every phone: no name and no joke in a comment gets there (the design's 5.1). What is left is checked
    as the text with its comments is: a comment between two words leaves a space.

    lines: every line stays, one that was a comment as an empty one - and of a comment over several
    lines their ends -, so that an error's line and column are the student's own. Without: a line that
    held nothing but comments goes. A text of nothing but comments is refused."""
    if comments:
        parts, at = [], 0
        for start, end in comments:
            parts += [text[at:start], "\n" * text.count("\n", start, end) if lines else GONE]
            at = end
        marked = "".join(parts) + text[at:]
        if lines:
            kept = [line.rstrip() for line in marked.split("\n")]
        else:
            kept = [GAP.sub(_gap, line).rstrip() if GONE in line else line for line in marked.split("\n")]
            kept = [line for line, was in zip(kept, marked.split("\n")) if line or GONE not in was]
        text = "\n".join(kept)
        text = text.rstrip("\n") if lines else text.strip("\n")
        if not text.strip():
            raise Unfit(f"{what} is more than its comments", "text")
    return text
