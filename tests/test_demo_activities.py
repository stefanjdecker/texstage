# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The demo deck of texstage's own kinds (examples/demo/activities.tex, its README): a choice of several
options, a number and a short answer build with their references in keys.json alone, checked as the server
checks them - and only a server of the core's type plays the deck (texstage present ... --activities core)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from texstage.build.builder import BuildOptions, build
from texstage.server import types as stage_types
from texstage.server.bundles import BundleStore

DECK = Path(__file__).resolve().parents[1] / "examples" / "demo" / "activities.tex"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """(BuildResult, deck.json, keys.json) of the deck, built as texstage build builds it."""
    from texstage.activities import registry
    if shutil.which("pdflatex") is None:
        pytest.skip("needs pdflatex")
    if "choice" not in registry.kinds():
        pytest.skip("texstage is not installed (pip install -e .): its own kinds are not found")
    result = build(DECK, tmp_path_factory.mktemp("activities"),
                   BuildOptions(server="https://quiz.example.org", key="demo-presenter-key"))
    return result, json.loads((result.bundle / "deck.json").read_text(encoding="utf-8")), \
        json.loads((result.bundle / "keys.json").read_text(encoding="utf-8"))


def test_the_demo_of_texstages_own_kinds_builds(built):
    result, deck, keys = built
    assert result.problems == [] and result.warnings == []
    assert sorted(deck["kinds"]) == ["choice", "number", "text"]
    items = {aid: {k: v for k, v in item.items() if k != "prompt"} for aid, item in deck["items"]["activity"].items()}
    assert items == {"rdf-syntaxes": {"kind": "choice", "limit": 10, "select": "many",
                                      "options": ["Turtle", "JSON-LD", "SPARQL", "N-Triples"]},
                     "turtle-count": {"kind": "number", "limit": 5},
                     "query-language": {"kind": "text", "limit": 5}}
    assert {aid: k["referenceKeys"] for aid, k in keys["items"]["activity"].items()} == {      # (a choice of several:
        "rdf-syntaxes": ["Turtle\nJSON-LD\nN-Triples"], "turtle-count": ["3"], "query-language": ["sparql"]}   # a line each)


def test_only_a_server_of_the_cores_type_plays_it(built):
    result, _, _ = built
    try:
        stage_types.use("f1")
        f1 = BundleStore([result.bundle.parent])
        assert not f1.bundles and "start it with texstage serve --activities core" in " ".join(f1.problems)
        stage_types.use("core")
        assert result.bundle_id in BundleStore([result.bundle.parent]).bundles
    finally:
        stage_types.use("f1")                       # (the type a server runs is the process's: F1's after)
