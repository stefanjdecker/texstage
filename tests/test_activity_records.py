# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Activity metadata must not depend on the TeX version's verbatim line endings - and an older
texactivity.sty's records, which name no fields, are said to be one."""
import pytest

from texstage.build.activity import ActivityError, entries, read
from texstage.build.tqz import Tqz

CORE = {"id": "query", "kind": "", "input": "code", "engine": "sparql".encode("utf-8").hex(), "limit": "", "open": "auto",
        "seed": "", "reference": "", "file": "", "line": "1"}


def some_reference_runs(act, name, item, keys, files, language):
    return [{"status": "ok", "key": f"key-{i}"} for i, _ in enumerate(keys.get("reference") or [])]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r", "\\obeyedline "],
                         ids=["lf", "crlf", "cr", "obeyedline"])
def test_activity_reference_and_seed_line_endings(tmp_path, newline):
    reference = 'SELECT ?n WHERE {\n  ?p :name ?n .  # 100% unchanged\n\n  FILTER(?n != "")\n}'
    seed = '@prefix : <https://example.org/> .\n:ada :name "Ada" .\n\n:ada :escape "\\r\\n" .'
    records = ["activity|" + "|".join(f"{k}={v}" for k, v in CORE.items())]
    for kind, text in (("activityref", reference), ("activityseed", seed)):
        encoded = (newline + text.replace("\n", newline) + newline).encode("utf-8").hex()
        records.append(f"{kind}|id=query|text={encoded}")
    path = tmp_path / "activity.tqz"
    path.write_text("\n".join(records) + "\n", encoding="utf-8")

    tqz = Tqz.read(path)
    activity = read(tqz)["query"]
    assert activity.references == [reference]
    assert activity.seed_text == seed
    warnings = []
    acts = entries(tqz, tmp_path, {}, warnings, checker=some_reference_runs)
    assert acts.keys == {"query": {"reference": [reference], "referenceKeys": ["key-0"]}}
    assert acts.files[acts.items["query"]["seed"]] == (seed + "\n").encode("utf-8")
    assert warnings == []


def test_an_older_texactivity_is_said_to_be_one(tmp_path):
    """F1's texactivity.sty wrote its records by position: a deck that loads it - through TEXINPUTS, from a
    lecture's tools/ - is told to update them, not given a kind it did not name."""
    path = tmp_path / "activity.tqz"
    path.write_text("activity|query|code|sparql||||||false|auto|||||1\n", encoding="utf-8")
    with pytest.raises(ActivityError, match="it loads an older texactivity.sty than this builder"):
        read(Tqz.read(path))
