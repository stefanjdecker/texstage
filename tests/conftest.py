# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: the demo deck built once per test run (texstage build, needs pdflatex); the default
activity type after every test."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from texstage.build.builder import BuildOptions, build

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo" / "demo.tex"


@pytest.fixture(autouse=True)
def default_activity_type():
    """The activity type a server runs is the process's (server/types.py: use), and every server a test makes
    sets it: after each test it is the default again, the core's (the plan of F2, package 14)."""
    yield
    from texstage.server import types
    types.use()


@pytest.fixture(scope="session")
def demo_build(tmp_path_factory):
    """(BuildResult, deck.json, keys.json) of the demo deck."""
    if shutil.which("pdflatex") is None:
        pytest.skip("needs pdflatex")
    result = build(DEMO, tmp_path_factory.mktemp("demo"),
                   BuildOptions(server="https://quiz.example.org", key="demo-presenter-key"))
    return result, json.loads((result.bundle / "deck.json").read_text(encoding="utf-8")), \
        json.loads((result.bundle / "keys.json").read_text(encoding="utf-8"))
