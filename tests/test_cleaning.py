# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""What a phone sent, made fit to check (texstage/checks/cleaning.py) - each case with the result written
out, not held against another caller of the same function: the activity type and the kinds both clean
with it, so a test that compares the two sees no fault in it (the review of F2's package 1: seventeen
faults put into the cleaning passed such tests, twelve the whole suite). And a text without its comments,
where they are being given: where an engine finds them is tests/test_checks.py's, what the kinds make of
both tests/test_kinds.py's."""
from __future__ import annotations

import random

import pytest

from texstage.checks import cleaning
from texstage.checks.cleaning import Unfit, clean_code, clean_term, is_literal, norm_term, term_key, uncommented

TOO_LONG = ("a query has 1 to 2000 characters", "text")
NO_TEXT = ("a query is text", "invalid")
NO_FIELD = ("every field has 1 to 60 characters", "field")
NOT_A_FIELD = ("a field is text", "invalid")


def refusal(clean, *args) -> tuple[str, str]:
    with pytest.raises(Unfit) as e:
        clean(*args)
    return str(e.value), e.value.code


# ------------------------------------------------------------------ a text
@pytest.mark.parametrize("sent, cleaned", [
    ("SELECT 1", "SELECT 1"),
    ("  SELECT 1  \r\n\r\n", "  SELECT 1"),                         # the indent stays, the line's end and the blank lines go
    ("a\r\nb\rc\nd", "a\nb\nc\nd"),                                 # every line end is \n
    ("\n\nSELECT\t1 \n FROM t \n\n", "SELECT\t1\n FROM t"),         # a tab stays, spaces at a line's end go
    ("a\n\n\nb", "a\n\n\nb"),                                       # blank lines inside stay
    ("x \u00a0\n\u3000y\u2003", "x\n\u3000y"),                      # other spaces at a line's end go too
    ("a\x00b\x07c\x1bd\x7fe", "abcde"),                             # control characters
    ("a\u200bb\u00adc\ufeffd", "abcd"),                             # ... and the invisible ones: zero width, soft hyphen, BOM
    ("a\ue000b\U000e0001c", "abc"),                                 # private use, a tag
    ("e\u0301", "\u00e9"),                                          # composed (NFC)
    ("\u212b", "\u00c5"),                                           # the angstrom sign is the letter
    ("\ufb01", "\ufb01"),                                           # ... but a ligature stays: NFC, not NFKC
    ("e\u00ad\u0308", "\u00eb"),                                    # composed after the soft hyphen is out
    ("x" * 2000, "x" * 2000),
    ("x" * 2000 + "  \n\n", "x" * 2000),                            # the length is the cleaned text's
    ("SELECT '\u00e4\U0001f600'", "SELECT '\u00e4\U0001f600'"),
])
def test_a_text_as_typed(sent, cleaned):
    assert clean_code(sent) == cleaned
    assert clean_code(cleaned) == cleaned


@pytest.mark.parametrize("sent, why", [
    ("", TOO_LONG), ("   \n \t", TOO_LONG), ("\x00\u200b", TOO_LONG), ("x" * 2001, TOO_LONG),
    (None, NO_TEXT), (7, NO_TEXT), (["SELECT 1"], NO_TEXT), (b"SELECT 1", NO_TEXT),
])
def test_a_text_that_is_refused(sent, why):
    assert refusal(clean_code, sent) == why


def test_a_refusal_calls_the_text_what_its_engine_calls_it():
    assert refusal(clean_code, "", "a Turtle text") == ("a Turtle text has 1 to 2000 characters", "text")
    assert refusal(clean_code, None, "a Turtle text") == ("a Turtle text is text", "invalid")


def test_the_blank_lines_in_front_stay_where_an_error_names_a_line():
    """top: a text's lines keep their numbers - only what is behind the last one goes."""
    assert clean_code("\n\n SELECT 1 \n\n", top=True) == "\n\n SELECT 1"
    assert clean_code("  \n\t\nx", top=True) == "\n\nx"
    assert clean_code("\n\nx", top=True) == clean_code(clean_code("\n\nx", top=True), top=True)
    assert clean_code("x \n", top=True) == clean_code("x \n") == "x"
    assert refusal(clean_code, "\n \n", "a query", True) == TOO_LONG


# ------------------------------------------------------------------ a text without its comments
def cut(text: str, *comments: str, lines: bool = False) -> str:
    """The text without these comments, each where it is first found behind the one before."""
    spans, at = [], 0
    for c in comments:
        start = text.index(c, at)
        spans.append((start, at := start + len(c)))
    return uncommented(text, spans, lines=lines)


@pytest.mark.parametrize("text, comments, left", [
    ("SELECT 1", [], "SELECT 1"),
    ("SELECT 1 -- one", ["-- one"], "SELECT 1"),                         # the spaces in front of it go with it
    ("-- by Max\nSELECT 1", ["-- by Max"], "SELECT 1"),                  # a line of nothing but comments goes
    ("SELECT a\n  -- b\nFROM t", ["-- b"], "SELECT a\nFROM t"),
    ("SELECT a\n\n-- b\n\nFROM t", ["-- b"], "SELECT a\n\n\nFROM t"),    # ... a line that was blank stays
    ("SELECT/**/1", ["/**/"], "SELECT 1"),                               # between two words: a space
    ("SELECT /* c */ 1", ["/* c */"], "SELECT 1"),                       # ... one, not two
    ("SELECT/* c */ 1", ["/* c */"], "SELECT 1"),
    ("SELECT /* c */1", ["/* c */"], "SELECT 1"),
    ("SELECT\t/* c */1", ["/* c */"], "SELECT\t1"),
    ("1 -/* c */-1", ["/* c */"], "1 - -1"),                             # no comment comes of taking one out
    ("a //* c */* b", ["/* c */"], "a / * b"),
    ("a/* b *//* c */d", ["/* b */", "/* c */"], "a d"),                 # two of them: one space
    ("a /* b */ /* c */ d", ["/* b */", "/* c */"], "a d"),
    ("a /* b\nc */ d", ["/* b\nc */"], "a d"),                           # over two lines: they are one now
    ("  /* c */ SELECT 1", ["/* c */"], "  SELECT 1"),                   # the indent stays
    ("SELECT 1 /* c */\n/* d */\n  FROM t -- e\n-- f", ["/* c */", "/* d */", "-- e", "-- f"], "SELECT 1\n  FROM t"),
    ("\u00a0/* c */x", ["/* c */"], "\u00a0 x"),                         # a space only where SQLite reads one
    ("x \u00a0 -- c", ["-- c"], "x"),                                    # at a line's end every space goes, as ever
])
def test_a_text_without_its_comments(text, comments, left):
    assert cut(text, *comments) == left
    assert clean_code(left) == left


@pytest.mark.parametrize("text, comments, left", [
    ("ASK {} # c", ["# c"], "ASK {}"),
    ("# by Max\nASK {}", ["# by Max"], "\nASK {}"),                      # the line stays, empty: ASK is in line 2
    ("a # b\n  # c\n\nd # e\n# f\n", ["# b", "# c", "# e", "# f"], "a\n\n\nd"),
    ("\n\na #b", ["#b"], "\n\na"),
    ("a#b\nc", ["#b"], "a\nc"),
    ("a (* b\nc\nd *)\ne", ["(* b\nc\nd *)"], "a\n\n\ne"),               # a comment over three lines: three lines
])
def test_a_text_without_its_comments_keeps_its_lines(text, comments, left):
    assert cut(text, *comments, lines=True) == left
    assert clean_code(left, top=True) == left
    assert left.count("\n") <= text.count("\n")
    for was, now in zip(text.split("\n"), left.split("\n")):
        assert was.startswith(now) or "*)" in was                        # every column as it was


def test_a_text_of_nothing_but_comments_is_refused():
    for lines in (False, True):
        with pytest.raises(Unfit, match="a Turtle text is more than its comments") as e:
            uncommented("# a\n  # b", [(0, 3), (6, 9)], "a Turtle text", lines)
        assert e.value.code == "text"
    assert uncommented("x", [], lines=True) == "x"


# ------------------------------------------------------------------ a term
@pytest.mark.parametrize("sent, cleaned", [
    (":Kant", ":Kant"),
    ("  Immanuel   Kant \u00a0", "Immanuel Kant"),                  # spaces collapsed, none around
    ("a\x00b", "ab"), ("a\u200bb", "ab"),                           # control characters out
    ("a\tb", "ab"), ("a\nb", "ab"),                                 # ... a tab and a line end are such: no space for them
    ("e\u0301", "\u00e9"), ("e\u00ad\u0308", "\u00eb"),             # composed, after the soft hyphen is out
    ("\u201cKant\u201d@de", '"Kant"@de'),                           # iOS's quotes are Turtle's
    ("\u201eKant\u201c", '"Kant"'), ("\u00abKant\u00bb", '"Kant"'), ("\u201fKant\u201d", '"Kant"'),
    ("\u2018Kant\u2019", "'Kant'"), ("\u201aKant\u2018", "'Kant'"), ("\u201bKant\u2019", "'Kant'"),
    ("\u201cStefan\u2019s lecture\u201d", '"Stefan\u2019s lecture"'),   # an apostrophe inside a string stays
    ("\u2018a \u201cb\u201d c\u2019", "'a \u201cb\u201d c'"),
    (":Stefan\u2019s", ":Stefan\u2019s"),                           # no string: as typed
    ("x\u201d", "x\u201d"),
    ("x" * 60, "x" * 60), ("  " + "x" * 60 + "  ", "x" * 60),
])
def test_a_term_as_typed(sent, cleaned):
    assert clean_term(sent) == cleaned
    assert clean_term(cleaned) == cleaned


@pytest.mark.parametrize("sent, why", [
    ("", NO_FIELD), ("   ", NO_FIELD), ("\x00", NO_FIELD), ("x" * 61, NO_FIELD),
    ("\u0301", NO_FIELD), ("\u00b4", NO_FIELD), ("\u00a8 \u02dc", NO_FIELD),     # accents only: no key
    (None, NOT_A_FIELD), (5, NOT_A_FIELD), (["a"], NOT_A_FIELD),
])
def test_a_term_that_is_refused(sent, why):
    assert refusal(clean_term, sent) == why


@pytest.mark.parametrize("term, key", [
    ("Kant", "kant"), ("  KANT  ", "kant"), ("K\u00f6ln", "koln"), ("Ko\u0308ln", "koln"),
    ("Stra\u00dfe", "strasse"), ("a   b\tc", "a b c"), ("\uff2bant", "kant"),      # a full-width K
    ("\ufb01n", "fin"), ("x\u00b2", "x2"), ("\u00c5", "a"), ("\u212b", "a"), ("\u0130", "i"),
    ("x\N{TRADE MARK SIGN}", "xtm"), ("\N{SERVICE MARK}", "sm"),     # capitals that only the compatibility form has
])
def test_a_terms_loose_key(term, key):
    """As the word cloud groups words: case, accents, spacing and compatibility forms do not matter."""
    assert norm_term(term) == key
    assert term_key(term, {"terms": "loose"}) == key
    assert term_key(term, {"terms": "exact"}) == term and term_key(term, {}) == term   # (a deck built before the key)


@pytest.mark.parametrize("term", ['"Kant"', '"Kant"@de', '"42"^^xsd:integer', "'x'", '"', "\u201cx", "\u2018x", '"a\nb"',
                                  "42", "-3.5", "+7", ".5", "1.", "1e10", "+2E-3", "1.5e-7", "true", "false"])
def test_what_is_written_as_a_literal(term):
    assert is_literal(term)


@pytest.mark.parametrize("term", [":Kant", "ex:a", "_:b", "<http://x>", "TRUE", "True", "truely", "4x", "1.2.3", "", "e10",
                                  "-", ".", "1e", "x42", "\u00b2", "a\"b"])
def test_what_names_a_resource(term):
    assert not is_literal(term)


# ------------------------------------------------------------------ cleaned once is clean
ALPHABET = ["a", "E", "\u00e9", "e", "\u0301", "\u0308", "\u00ad", "\u200b", "\u200d", " ", "\u00a0", "\t", "\n", "\r", "\x00",
            "\u201c", "\u201d", "\u2018", "\u2019", '"', "'", "\u1100", "\u1161", "\u11a8", "\u0f73", "\U0001f600", "\ufb01",
            "\u00b4", "\u2028", "<", "\u0338", "\ue000", ":", "1", "."]


def test_cleaning_what_is_clean_changes_nothing():
    """A normal form: 20,000 texts of characters that compose, vanish, or are spaces - cleaned twice as once."""
    rng = random.Random(20261110)
    cleaned = 0
    for _ in range(20_000):
        text = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(1, 12)))
        for clean in (clean_code, clean_term):
            try:
                once = clean(text)
            except Unfit:
                continue
            cleaned += 1
            assert clean(once) == once, (clean.__name__, ascii(text), ascii(once), ascii(clean(once)))
    assert cleaned > 20_000


def test_the_bounds_are_the_ones_the_phones_are_told():
    assert (cleaning.TERM_MAX, cleaning.TEXT_MAX) == (60, 2000)
