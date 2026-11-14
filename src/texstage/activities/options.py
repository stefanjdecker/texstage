# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A kind's options: the keys of a deck's activity environment that are the kind's own, each with a type
that reads what the deck gave and says what is wrong with it (the contract: kind.py; the plan of F2,
4.2). One schema for an activity and, from F3, its steps.

    OPTIONS = fixed(seed=File(".sql"), tokens=Words(), min=Int(1000), review=Flag(), terms=Choice("exact", "loose"))

    Words(most, longest)     a list of short texts - labels, suggestions, tokens
    Int(top, default)        a number from 1 to top
    Number(low, high, default)   a number from low to high - 0.5, -2
    Flag()                   true or false
    InBody()                 written in the body (\\reference{...}), not as a key - which is refused
    Choice(a, b, ...)        one of some words; the first when the deck does not say
    File(".sql", ...)        a file of the deck's folder, by its name: read when the kind asks for its text

The build hands a kind its options as Options: a key is read and checked when the kind asks for it, so
that the kind says in which order a deck's faults are told - the order today's build tells them in. The
refusals' words are today's (build/activity.py), which the decks' authors know."""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ["CORE", "PRESETS", "Choice", "File", "Flag", "InBody", "Int", "Named", "Number", "Option", "Options",
           "Unbuildable", "Words"]

WORD_MAX = 60                               # a field's label, a suggestion, a token
WORDS_MAX = 40                              # suggestions, tokens
CORE = ("id", "input", "engine", "kind", "limit", "counts", "gap", "time", "budget", "feedback", "projector",
        "solution", "open", "width", "height")             # the keys that are the core's (texactivity.sty): no kind takes them
PRESETS = {"fields": ["Subject", "Predicate", "Object"]}      # what a key is when a deck does not give it - the
#                                             kind's default, which texactivity.sty wrote before package 7 of F2: given so,
#                                             not counted as given


class Unbuildable(ValueError):
    """A deck's activity cannot be built: why, without the activity's name - the core says which."""


class Option:
    """An option's type. read(key, given, files) gives the value a kind works with, or Unbuildable."""

    def read(self, key: str, given, files):
        raise NotImplementedError


class Words(Option):
    def __init__(self, most: int = WORDS_MAX, longest: int = WORD_MAX):
        self.most, self.longest = most, longest

    def read(self, key: str, given, files) -> list[str]:
        items = list(given) if isinstance(given, (list, tuple)) else None if given else []
        if items is None or len(items) > self.most or any(not isinstance(w, str) or not w or len(w) > self.longest for w in items):
            raise Unbuildable(f"{key}= takes at most {self.most} items of 1 to {self.longest} characters")
        return items


class Int(Option):
    """A number from 1 to top, in ASCII's digits (isdigit alone takes a superscript 2, which int does not,
    and an Arabic 3, which it does)."""

    def __init__(self, top: int, default: int = 1):
        self.top, self.default = top, default

    def read(self, key: str, given, files) -> int:
        value = given or ""
        if not value:
            return self.default
        if not isinstance(value, str) or not (value.isascii() and value.isdigit()) or not 1 <= int(value) <= self.top:
            raise Unbuildable(f"{key}={value} - a number from 1 to {self.top}")
        return int(value)


NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")      # 3, -2, 0.5, .5 - ASCII's digits, a point
ESCAPED = re.compile(r"\\([{}#%&_$\\~^])")                        # \& and the like: the character a deck means
MATH = re.compile(r"((?<!\\)\$(?:\\.|[^\\$\n])+\$)")               # a formula, $...$: its escapes are its own


def unescaped(text: str) -> str:
    """A deck's text with \\& and the like as the characters they stand for - but not inside a formula, where
    \\{ and \\% are the formula's own: $\\{A, B\\}$ is a set, $50\\%$ fifty percent (KaTeX reads them so). The
    one rule for a kind's keys (build/activity.py) and a kind's references (kinds)."""
    return "".join(part if i % 2 else ESCAPED.sub(r"\1", part) for i, part in enumerate(MATH.split(text)))


class Number(Option):
    """A number from low to high as a deck writes it - 3, 0.5, -2 -: ASCII's digits and one point, no exponent
    (a deck's number is a person's, not a program's)."""

    def __init__(self, low: float, high: float, default: float = 0):
        self.low, self.high, self.default = low, high, default

    def read(self, key: str, given, files) -> float:
        value = given or ""
        if not value:
            return self.default
        if not isinstance(value, str) or not NUMBER.fullmatch(value.strip()) or not self.low <= float(value) <= self.high:
            raise Unbuildable(f"{key}={value} - a number from {self.low:g} to {self.high:g}")
        return float(value)


class InBody(Option):
    """What a deck writes in the environment's body - \\reference{...} - and not as a key, which is refused: the
    kinds without files (texstage's own) take their references so. Declared, a body the kind takes is no
    unused key of the deck's (Options.unused)."""

    def read(self, key: str, given, files) -> None:
        if given:
            raise Unbuildable(f"{key}={given} - write \\{key}{{...}} in the activity instead")
        return None


class Flag(Option):
    """On or off: true or false - as a deck writes it (review=false), or a key written without a value (review),
    which the build gives as True."""

    def read(self, key: str, given, files) -> bool:
        if given is None or isinstance(given, bool):
            return bool(given)
        if given in ("true", "false"):
            return given == "true"
        raise Unbuildable(f"{key}={given} - true or false")


class Choice(Option):
    def __init__(self, *values: str):
        self.values = values

    def read(self, key: str, given, files) -> str:
        value = given or ""
        if value and value not in self.values:
            raise Unbuildable(f"{key}={value} - {' or '.join(self.values)}")
        return value or self.values[0]


class Named:
    """A file a deck names: its name, its suffix in lower case, and its text - read when it is asked for,
    Unbuildable when the file is not there."""

    def __init__(self, name: str, what: str, files):
        self.name, self.suffix, self._what, self._files = name, Path(name).suffix.lower(), what, files

    def text(self) -> str:
        return self._files(self.name, self._what)


class File(Option):
    """A file of the deck's folder; suffixes: the types it may be (the first is the bundle's). Whether a
    name has one of them is the kind's to say, in its own words."""

    def __init__(self, *suffixes: str):
        self.suffixes = suffixes

    def read(self, key: str, given, files) -> Named | None:
        return Named(given, key, files) if given else None


class Options:
    """What a deck gave for an activity, as its kind reads it: options["min"] is the value of its type -
    read and checked once, when it is first asked for; given("fields") what the deck wrote; unused(),
    the keys the kind does not take.

    given: the record's keys in its order - words as lists, a number as its digits, a file as its name;
    files(name, what): a file of the deck's folder as text, Unbuildable when it is not there."""

    def __init__(self, declared, given: dict, files=None):
        self._declared, self._given, self._files, self._read = declared, dict(given), files, {}

    def given(self, key: str):
        return self._given.get(key)

    def __getitem__(self, key: str):
        if key not in self._read:
            self._read[key] = self._declared[key].read(key, self._given.get(key), self._files)
        return self._read[key]

    def unused(self, bodies: dict | None = None) -> list[str]:
        """The keys a deck gave that this kind does not take - a warning of the build's. A seed or a
        reference is given as a key or in the body; a key left at its preset was not given."""
        bodies = bodies or {}
        body = {"seed": bodies.get("seed"), "reference": bodies.get("references")}
        out = []
        for key in [*self._given, *(k for k in body if k not in self._given)]:    # (a body's key, though the record has none)
            value = self._given.get(key)
            if key in self._declared or key in CORE:
                continue
            if key in PRESETS and isinstance(value, (list, tuple)) and list(value) == PRESETS[key]:
                continue
            if value or body.get(key):
                out.append(key)
        return out
