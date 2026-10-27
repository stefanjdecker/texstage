# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The engines of live activities (web/engines/), in Node: SPARQL on the vendored Oxigraph, SQL on
the vendored sql.js and Turtle on Oxigraph's parser - canonical forms and keys, what is refused,
errors, summaries, the comparison with a reference; and the engines' two tables, the windows' and
the build's, naming the same."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from texstage.engines import ENGINES

WEB = Path(__file__).resolve().parents[1] / "src" / "texstage" / "web"


def node_test(name: str):
    script = Path(__file__).with_name(name)
    result = subprocess.run([shutil.which("node"), "--test", str(script)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_sparql_engine():
    node_test("web-activity-engine.test.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_sql_engine():
    node_test("web-activity-sql.test.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="browser JavaScript tests need Node.js")
def test_the_turtle_engine():
    node_test("web-activity-turtle.test.mjs")


def test_the_engine_tables_agree():
    """web/engines/index.js (what the presenter's browser runs) and texstage/engines.py (what the
    build accepts, what the server serves) name the same engines, and every file is there; each
    engine of the build's table has its seed's file types, its tokens and a name for a student's
    text (the server's messages)."""
    js = (WEB / "engines" / "index.js").read_text(encoding="utf-8")
    table = re.search(r"export const ENGINES = \{(.*?)\n\};", js, re.S).group(1)
    rows = re.findall(r'^\s*(\w+): \{ module: "\./([\w-]+\.js)", wasm: "\.\./(vendor/[\w./-]+)" \},?$', table, re.M)
    assert {name for name, _, _ in rows} == set(ENGINES) and len(rows) == len(ENGINES)
    for name, module, wasm in rows:
        assert (WEB / "engines" / module).is_file() and (WEB / wasm).is_file(), name
    for name, engine in ENGINES.items():
        assert set(engine) == {"seed", "tokens", "text"}, name
        assert engine["seed"] and all(s.startswith(".") for s in engine["seed"]) and engine["tokens"], name
    assert ENGINES["turtle"]["seed"] == ENGINES["sparql"]["seed"] == {".ttl": "text/turtle; charset=utf-8"}
    assert dict((n, w) for n, _, w in rows)["turtle"] == dict((n, w) for n, _, w in rows)["sparql"], \
        "the Turtle engine parses with the SPARQL engine's Oxigraph"
