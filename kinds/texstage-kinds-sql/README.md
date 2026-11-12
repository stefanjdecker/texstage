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
may still change until it is called API 1, and nothing of the server uses the kind yet: F1's activity
type runs the lectures.

Install it after texstage, from the repository's root, and check it:

```sh
python -m pip install --no-deps --no-build-isolation -e kinds/texstage-kinds-sql
texstage kinds check sql-query
```

`texstage kinds check` runs the kit on the fixtures beside the module (`tests/*.json`): the golden
fixtures of today's SQL engine, made by `tests/fixtures/checks/to_kinds.py`, safety cases, and texts
with comments: the kind takes a text's comments out before it is checked, since a group of answers
is shown by such a text.

The check itself is F1's `texstage.checks.sql` and moves into this package once F1 is in `main`.
