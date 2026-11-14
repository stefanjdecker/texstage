# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's own kinds (docs/architecture/activity-framework-design.md, 7.2; the plan of F2, 4.8) - the
kinds every subject needs, found through the same entry points as any other (pyproject.toml), so that the
contract is used by its author every day: no seed, other inputs, other reductions, other views.

    choice    one or several of the options a deck gives (options=, select=one|many) - text, and $math$
              as the phones typeset it (option_text); counted per option (tally); right when the choice is
              the reference's - a reference names its option (\\reference{Lyon}), and with select=many
              the references together are the right choice
    number    a number; drawn as a histogram (groups); right within tolerance= of a reference, compared
              as the deck writes numbers, in decimals - the kind judges for itself
    text      a short answer, compared as the quiz compares text answers - case, accents and spacing do not
              matter (cleaning.norm_term, the quiz's scoring.normalize_text) - and what is not seen (a
              zero-width space) is no part of it; grouped by that form; right when it is a reference's

    \\begin{activity}[id=capital, kind=choice, options={Paris, Lyon, Nice}]
      \\prompt{Which is the capital of France?}
      \\reference{Paris}
    \\end{activity}

Their checks run in the pool too: no kind code runs in the server's event loop (the design's 2). Their
texts (texts/en.js, de.js) are their words for a status - a choice is chosen, it does not run."""
from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal

from texstage.activities.kind import SEVERAL, Built, Check, Entry, Kind, fixed
from texstage.activities.options import NUMBER, Choice as OneOf, InBody, Number as NumberOption, Unbuildable, Words, unescaped
from texstage.checks.cleaning import Unfit, norm_term

__all__ = ["Choice", "Number", "Text"]

OPTIONS_MAX = 26                            # a choice's options, at most - A to Z (the core's: entries.py)
OPTION_MAX = 100                            # an option's characters
TEXT_MAX = 100                              # a short answer's characters, as a quiz's text answer
NUMBER_MAX = 1e15                           # a number's size, at most (the core's: entries.py)
DIGITS = 15                                 # a number's significant digits: 0.1 + 0.2 is 0.3; a whole one is exact
WHOLE = re.compile(r"[+-]?[0-9]+")          # a whole number as a deck writes it: 42, -7
CONTROL_WORD = re.compile(r"(\\[A-Za-z]+) (?=[^A-Za-z]|$)")     # the space \tl_to_str puts after a control word
NAMED = re.compile(r"\\text(asciitilde|asciicircum|backslash)(?:\{\}|(?![A-Za-z]))")      # characters LaTeX names
CHARACTER = {"asciitilde": "~", "asciicircum": "^", "backslash": "\\"}
JOINERS = {chr(0x200C), chr(0x200D)}          # of an emoji's sequence, a Persian word: kept, though they are format


def option_text(text: str, verbatim: bool = False) -> str:
    """A choice's option or reference as the phones show it and the kind compares it - the same however LaTeX
    passed it on. An option comes through its key's value, unescaped once by the build ($\\sigma $ - a space
    after a control word -, \\& already &); a reference verbatim ($\\sigma$, R\\&D), unescaped here by the
    same rule (options.unescaped: a formula keeps its escapes, $\\{A, B\\}$). Then: spaces collapsed - line
    breaks too, so that no option has one (SEVERAL) -, the space after a control word gone where no letter
    follows, a tie (~) a space as LaTeX sets it, \\textasciitilde and the like their character."""
    text = CONTROL_WORD.sub(r"\1", " ".join((unescaped(text) if verbatim else text).split()))
    text = NAMED.sub(lambda m: CHARACTER[m.group(1)], text.replace("~", " "))
    return " ".join(text.split())


def plain(text: str) -> str:
    """A short answer as the kind keeps it: its spaces collapsed, line breaks too, and no control or format
    character left - a zero-width space, a soft hyphen, a reversal of the writing's direction -, which would
    make two answers that look alike two groups. The joiners stay, and so do characters newer than Python's
    tables (an emoji of this year)."""
    text = " ".join(text.split())
    kept = (c for c in text if c in JOINERS or unicodedata.category(c) not in ("Cc", "Cf", "Cs"))
    return " ".join("".join(kept).split())


def text_reference(text: str) -> str:
    """A short answer's reference as a student types it: \\& and the like as their characters (options.unescaped),
    a tilde as written - ~/bin is a path, not LaTeX's tie -, and what plain() keeps."""
    return plain(unescaped(text))


def _place(entry: Entry) -> tuple[int, ...]:
    if entry.choice is None:
        raise TypeError("a choice's entry is a choice")
    return entry.choice


class Choice(Kind):
    """One or several of the options a deck gives; counted per choice; right when it is the reference's."""
    NAME = "choice"
    INPUT = "choice"
    REDUCTION = "tally"
    OPTIONS = fixed(options=Words(OPTIONS_MAX, OPTION_MAX), select=OneOf("one", "many"), reference=InBody())
    LIMIT = 10                              # (a student may change their mind: the latest counts)

    def build(self, options, bodies) -> Built:
        given = [option_text(o) for o in options["options"]]
        if not 2 <= len(given) <= OPTIONS_MAX:
            raise Unbuildable(f"options= takes 2 to {OPTIONS_MAX} options - what the phones offer")
        if not all(given):
            raise Unbuildable("options= has an empty option")
        twice = next((o for i, o in enumerate(given) if o in given[:i]), None)
        if twice is not None:
            raise Unbuildable(f"options= names {twice} twice")
        select = options["select"]
        options["reference"]                                # (written in the body, not as a key)
        references = [option_text(r, verbatim=True) for r in bodies.get("references") or []]
        other = next((r for r in references if r not in given), None)
        if other is not None:
            raise Unbuildable(f"the reference {other} is none of the options ({', '.join(given)})")
        keys = {}
        if references and select == "many":                 # together, the right choice
            keys["reference"] = [SEVERAL.join(o for o in given if o in references)]
        elif references:                                    # each a right choice
            keys["reference"] = list(dict.fromkeys(references))
        return Built({"options": given, "select": select}, keys)

    def normalize(self, step, entry: Entry) -> Entry:
        places = sorted(set(_place(entry)))
        count = len(step.item.get("options") or ())
        if not places or not all(type(p) is int and 0 <= p < count for p in places):
            raise Unfit("choose one of the options", "choice")
        if len(places) > 1 and step.item.get("select", "one") != "many":
            raise Unfit("one option, not several", "choice")
        return Entry(choice=tuple(places))

    def reference(self, step, text: str) -> Entry:
        options = list(step.item.get("options") or ())
        return Entry(choice=tuple(sorted(options.index(o) for o in text.split(SEVERAL) if o in options)))

    def check(self, prepared, step, entry: Entry) -> Check:
        options = step.item.get("options") or ()
        places = _place(entry)
        if not places or not all(type(p) is int and 0 <= p < len(options) for p in places):
            raise TypeError("a choice of the step's options")
        return Check("ok", key=SEVERAL.join(options[p] for p in sorted(set(places))))


def canonical(number: float | int) -> float | int:
    """A number as the kind keeps it: a whole number exactly, as an int - 42.0 is 42, 2**40 stays 2**40 (a
    float is exact up to 2**53, beyond NUMBER_MAX) -, any other to DIGITS significant digits."""
    if isinstance(number, int) and not isinstance(number, bool):
        return number
    if number.is_integer():
        return int(number)
    rounded = float(f"{number:.{DIGITS}g}")
    return int(rounded) if rounded.is_integer() else rounded


def written(number: float | int) -> str:
    """A number as its key, the deck's reference and the archive write it, its digits in full and no
    exponent: 42, 41.5, -0.25, 0.00001."""
    return str(number) if isinstance(number, int) else format(Decimal(f"{number:.{DIGITS}g}"), "f")


def _read(text: str) -> float | int:
    """A number as a deck or written() writes it - a whole number exactly."""
    return int(text) if WHOLE.fullmatch(text) else float(text)


def _number(n) -> float | int:
    """An entry's number, which normalize has made a number - else TypeError."""
    if isinstance(n, bool) or not isinstance(n, (int, float)) or (isinstance(n, float) and not math.isfinite(n)):
        raise TypeError("a number's entry is a number")
    return n


class Number(Kind):
    """A number; drawn as a histogram; right within the tolerance of a reference - as the deck writes the
    numbers, in decimals: 0.1 + 0.2 is 0.3, and with no tolerance only the reference itself is right."""
    NAME = "number"
    INPUT = "number"
    REDUCTION = "groups"
    OPTIONS = fixed(tolerance=NumberOption(0, NUMBER_MAX), reference=InBody())
    LIMIT = 5

    def build(self, options, bodies) -> Built:
        tolerance = options["tolerance"]
        options["reference"]
        references = []
        for text in bodies.get("references") or []:
            t = text.strip()
            if not NUMBER.fullmatch(t):
                raise Unbuildable(f"the reference {t} is no number - 42, -0.5")
            if abs(_read(t)) > NUMBER_MAX:
                raise Unbuildable(f"the reference {t} is too large - at most 10^15")
            references.append(written(canonical(_read(t))))
        return Built({"tolerance": canonical(tolerance)} if tolerance else {},
                     {"reference": references} if references else {})

    def normalize(self, step, entry: Entry) -> Entry:
        if entry.number is None or isinstance(entry.number, bool) or not isinstance(entry.number, (int, float)):
            raise TypeError("a number's entry is a number")
        n = entry.number
        if isinstance(n, float) and not math.isfinite(n):
            raise Unfit("a number a phone can write", "number")
        if abs(n) > NUMBER_MAX:
            raise Unfit("at most 10^15", "too-large")
        return Entry(number=canonical(n))

    def reference(self, step, text: str) -> Entry:
        return Entry(number=canonical(_read(text)))

    def check(self, prepared, step, entry: Entry) -> Check:
        n = canonical(_number(entry.number))
        references = [Decimal(r) for r in step.keys.get("reference") or ()]
        verdict = None
        if references:                                       # the kind judges: within the tolerance of one
            given = Decimal(written(n))
            tolerance = Decimal(written(canonical(step.item.get("tolerance") or 0)))
            verdict = "correct" if any(abs(given - r) <= tolerance for r in references) else "incorrect"
        return Check("ok", key=written(n), verdict=verdict)


class Text(Kind):
    """A short answer, compared as the quiz compares text answers; right when it is a reference's."""
    NAME = "text"
    INPUT = "text"
    REDUCTION = "groups"
    OPTIONS = fixed(reference=InBody())
    LIMIT = 5

    def build(self, options, bodies) -> Built:
        options["reference"]
        references = [text_reference(r) for r in bodies.get("references") or []]      # (R\&D is R&D, as typed)
        bad = next((r for r in references if not r or len(r) > TEXT_MAX), None)
        if bad is not None:
            raise Unbuildable(f"a reference of 1 to {TEXT_MAX} characters, not {bad[:40]!r}")
        return Built({}, {"reference": references} if references else {})

    def normalize(self, step, entry: Entry) -> Entry:
        if entry.text is None:
            raise TypeError("a text's entry is a text")
        text = plain(entry.text)                             # as a quiz takes a text answer (scoring.py: _text),
        if not text:                                         # and nothing that is not seen
            raise Unfit("type something first", "text")
        if len(text) > TEXT_MAX:
            raise Unfit(f"at most {TEXT_MAX} characters", "too-long")
        return Entry(text=text)

    def check(self, prepared, step, entry: Entry) -> Check:
        if entry.text is None:
            raise TypeError("a text's entry is a text")
        return Check("ok", key=norm_term(entry.text) or entry.text)
