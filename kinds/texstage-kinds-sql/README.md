<!--
SPDX-FileCopyrightText: 2026 Stefan Decker
SPDX-License-Identifier: Apache-2.0
-->
# texstage-kinds-sql

texstage's kind of live activity for SQL.

| kind | what the students send | how it is checked |
|---|---|---|
| `sql-query` | a query over the seed's tables | Python's `sqlite3`, on the server; answers with the same result form one group |

This is today's `input=code, engine=sql`, as a class behind the provisional contract of the activity
framework (`texstage.activities.kind`; the framework's
[design](../../docs/architecture/activity-framework-design.md), section 17, and its
[plan for F2](../../docs/architecture/activity-framework-plan-f2.md), package 1). The contract may
still change, and nothing of the server uses the class yet: F1's activity type runs the lectures.

The check itself is F1's `texstage.checks.sql` and moves into this package once F1 is in `main`. The
package is not installed yet either - the tests put its `src` on the path (`tests/test_kinds.py`);
package 2 of the plan adds the registry, which finds a kind by its entry point.
