<!--
SPDX-FileCopyrightText: 2026 Stefan Decker
SPDX-License-Identifier: Apache-2.0
-->
# texstage-kinds-sql

texstage's kind of live activity for SQL.

| kind | what the students send | how it is checked |
|---|---|---|
| `sql-query` | a query over the seed's tables | Python's `sqlite3`, on the server; answers with the same result form one group |

This is today's `input=code, engine=sql`, as a kind of the activity framework's contract, API 0
(`texstage.activities.kind`; the framework's
[design](../../docs/architecture/activity-framework-design.md), sections 7 and 17, and its
[plan for F2](../../docs/architecture/activity-framework-plan-f2.md), packages 1 and 2). The contract
may still change until it is called API 1. A server uses the kind when it runs the core's activity
type (`texstage serve --activities core`); F1's type, a server's default, does not need it.

Install it after texstage 0.2.1.dev4 or later, wherever decks are built - the build checks an
activity's keys and runs its references with its kind - and wherever they are served; from the
repository's root, and check it:

```sh
python -m pip install --no-deps --no-build-isolation ./kinds/texstage-kinds-sql
texstage kinds check sql-query
```

It needs nothing beyond texstage: Python's `sqlite3` runs the queries. For development install it
with `-e` ([development.md](../../docs/development.md)).

`texstage kinds check` runs the kit on the fixtures beside the module (`tests/*.json`): the golden
fixtures of today's SQL engine, made by `tests/fixtures/checks/to_kinds.py`, safety cases, and texts
with comments: the kind takes a text's comments out before it is checked, since a group of answers
is shown by such a text.

The check itself is texstage's, `texstage.checks.sql`, which F1's activity type uses too; it stays
there while that type does.
