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
may still change until it is called API 1, and nothing of the server uses the kinds yet: F1's
activity type runs the lectures.

Install it after texstage, from the repository's root, and check it:

```sh
python -m pip install --no-deps --no-build-isolation -e kinds/texstage-kinds-rdf
texstage kinds check triples sparql-query turtle-graph
```

`texstage kinds check` runs the kit on the fixtures beside the module (`tests/*.json`): the golden
fixtures of today's SPARQL and Turtle engines, made by `tests/fixtures/checks/to_kinds.py`, safety
cases - `SERVICE` in every spelling, nesting beyond the parsers' cap - and the cases of `triples`.

The two checks are F1's `texstage.checks.sparql` and `texstage.checks.turtle` and move into this
package once F1 is in `main`.
