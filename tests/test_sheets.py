# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The archive's tables as CSV (server/sheets.py): what a student wrote that a spreadsheet would run as a
formula is written with an apostrophe in front; numbers stay numbers; a CSV's lines end once."""
from __future__ import annotations

import csv

from texstage.server.sheets import cell, csv_text


def test_a_cell_a_spreadsheet_would_run_is_shown_instead():
    for formula in ("=1+2", "+A1", "-2+3", "@SUM(A1:A2)", "=HYPERLINK(" + chr(34) + "x" + chr(34) + ")", chr(9) + "x",
                    chr(13) + "x", chr(10) + "=1", "-", "+", chr(0xFF1D) + "1+2", chr(0xFF20) + "SUM(A1)"):   # (full-width)
        assert cell(formula) == "'" + formula, formula
    for kept in ("Ada", "12", "-5", "+3.5", "-0.25", "1e5", "-1.5E-3", "", " =1", "a=b", 12, -3.5, None):
        assert cell(kept) == kept, kept


def test_the_rows_as_csv():
    text = csv_text([["time", "input"], ["10:00", "=1+2"], ["10:01", "-7"], ["10:02", "a, b"]])
    assert chr(13) * 2 not in text and text.count(chr(13) + chr(10)) == 4
    assert list(csv.reader(text.splitlines())) == [["time", "input"], ["10:00", "'=1+2"], ["10:01", "-7"],
                                                   ["10:02", "a, b"]]
