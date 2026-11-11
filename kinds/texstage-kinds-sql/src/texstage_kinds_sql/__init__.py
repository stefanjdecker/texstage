# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage's kind for SQL (docs/architecture/activity-framework-design.md, section 17):

    sql-query   a query over the seed's tables, run by Python's sqlite3 - today's input=code, engine=sql

Behind the provisional contract (texstage.activities.kind; F2's plan, package 1). The check itself is
still F1's (texstage.checks.sql) and moves here once F1 is in main."""
from __future__ import annotations

try:
    from texstage.activities.code import CodeKind
except ImportError as e:                                  # an older texstage: say what is missing
    raise ImportError("texstage-kinds-sql needs a texstage with the activity framework's contract "
                      "(texstage.activities); this one has none") from e
from texstage.activities.kind import Prepared

__all__ = ["SqlQuery"]


class SqlQuery(CodeKind):
    NAME = "sql-query"
    ENGINE = "sql"
    MODULE = "texstage.checks.sql"
    SEED = {".sql": "application/sql"}
    TOKENS = ["*", ",", "(", ")", "=", "'", "."]
    TEXT = "a query"

    def prepare(self, item: dict, keys: dict, files: dict[str, bytes], limits: dict | None = None,
                copy: bytes | None = None) -> Prepared:
        """The seed's database - run from the seed, or loaded from the copy another worker's run left, so
        that a seed with random() or the time gives every worker the same data. limits: heap_allowance,
        the memory SQLite itself may take here (its own cap: beyond it a check is the student's error)."""
        options = {}
        if limits and limits.get("heap_allowance"):
            options["heap_allowance"] = limits["heap_allowance"]
        if copy is not None:
            options["image"] = copy
        return Prepared(self.engine.load(self.seed(item, files), **options))

    def copy(self, prepared: Prepared, most: int) -> bytes | None:
        """The database as the seed left it, where it can be copied whole and has at most `most` bytes -
        for every worker, the first too (kind.first): the run's own database counts its changes."""
        return self.engine.image(prepared.state, most)
