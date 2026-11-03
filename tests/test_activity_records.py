# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Activity metadata must not depend on the TeX version's verbatim line endings."""
import pytest

from texstage.build.activity import entries, read
from texstage.build.tqz import Tqz


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r", "\\obeyedline "],
                         ids=["lf", "crlf", "cr", "obeyedline"])
def test_activity_reference_and_seed_line_endings(tmp_path, newline):
    reference = 'SELECT ?n WHERE {\n  ?p :name ?n .  # 100% unchanged\n\n  FILTER(?n != "")\n}'
    seed = '@prefix : <https://example.org/> .\n:ada :name "Ada" .\n\n:ada :escape "\\r\\n" .'
    fields = ["query", "code", "sparql", "", "", "", "", "", "false", "", "", "", "", "", "1"]
    records = ["activity|" + "|".join(fields)]
    for kind, text in (("activityref", reference), ("activityseed", seed)):
        encoded = (newline + text.replace("\n", newline) + newline).encode("utf-8").hex()
        records.append(f"{kind}|query|{encoded}")
    path = tmp_path / "activity.tqz"
    path.write_text("\n".join(records) + "\n", encoding="utf-8")

    tqz = Tqz.read(path)
    activity = read(tqz)["query"]
    assert activity.references == [reference]
    assert activity.seed_text == seed
    warnings = []
    items, keys, files = entries(tqz, tmp_path, {}, warnings)
    assert keys == {"query": {"reference": [reference]}}
    assert files[items["query"]["seed"]] == (seed + "\n").encode("utf-8")
    assert warnings == []
