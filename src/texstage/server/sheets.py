# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The lecture archive's tables as CSV (archive.py) - files a lecturer opens in a spreadsheet. A cell that
a student wrote and that begins as a formula would (=, +, -, @, a tab, a line's end, their full-width
forms: a nickname, an answer) is written with an apostrophe in front, so that the spreadsheet shows it and
runs nothing (OWASP: CSV injection); a number - also a negative one - stays as it is. No module of the
server's is imported here: the activity types' archives use it too."""
from __future__ import annotations

import csv
import io
import re

__all__ = ["cell", "csv_text"]

FORMULA = ("=", "+", "-", "@", "\t", "\r", "\n",       # (and their full-width forms, which some spreadsheets read so)
           chr(0xFF1D), chr(0xFF0B), chr(0xFF0D), chr(0xFF20))
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def cell(value):
    """A cell as the archive writes it: a text a spreadsheet would read as a formula with ' in front."""
    if isinstance(value, str) and value.startswith(FORMULA) and not NUMBER.fullmatch(value):
        return "'" + value
    return value


def csv_text(rows) -> str:
    """The rows as CSV, each cell as cell() writes it."""
    buf = io.StringIO()
    csv.writer(buf).writerows([cell(v) for v in row] for row in rows)
    return buf.getvalue()
