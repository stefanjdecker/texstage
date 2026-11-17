<!--
SPDX-FileCopyrightText: 2026 Stefan Decker
SPDX-License-Identifier: Apache-2.0
-->
# texstage-kinds-rdf

texstage's kinds of live activity for RDF.

| kind | what the students send | how it is checked |
|---|---|---|
| `triples` | two or three terms - a node, an edge's label, a node | nothing is run: the terms are cleaned and keyed, and the crowd's graph is drawn from them |
| `sparql-query` | a query over the seed's graph | pyoxigraph, on the server; answers with the same result form one group |
| `turtle-graph` | a graph written in Turtle | pyoxigraph's Turtle parser; of the seed only its `@base` and `@prefix` lines count |

These are today's `input=tuple`, `input=code, engine=sparql` and `input=code, engine=turtle`, as
kinds of the activity framework's contract, API 0 (`texstage.activities.kind`; the framework's
[design](../../docs/architecture/activity-framework-design.md), sections 7 and 17, and its
[plan for F2](../../docs/architecture/activity-framework-plan-f2.md), packages 1 and 2). The contract
may still change until it is called API 1. A server uses the kinds when it runs the core's activity
type (`texstage serve --activities core`); F1's type, a server's default, needs none of them.

Install it after texstage 0.2.1.dev4 or later, wherever decks are built - the build checks an
activity's keys and runs its references with its kind - and wherever they are served; from the
repository's root, and check it:

```sh
python -m pip install --no-deps --no-build-isolation ./kinds/texstage-kinds-rdf
texstage kinds check triples sparql-query turtle-graph
```

Its dependency, pyoxigraph, is among texstage's locked ones (`requirements/runtime.txt`); for
development install it with `-e` ([development.md](../../docs/development.md)).

`texstage kinds check` runs the kit on the fixtures beside the module (`tests/*.json`): the golden
fixtures of today's SPARQL and Turtle engines, made by `tests/fixtures/checks/to_kinds.py`, safety
cases - `SERVICE` in every spelling, nesting beyond the parsers' cap -, texts with comments and the
cases of `triples`. `sparql-query` and `turtle-graph` take a text's comments out before it is
checked, since a group of answers is shown by such a text; every line stays, so that an error's
line is the student's own.

The two checks are texstage's, `texstage.checks.sparql` and `texstage.checks.turtle`, which F1's
activity type uses too; they stay there while that type does.
