// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The words of texstage-kinds-rdf's kinds - sparql-query, turtle-graph; triples says nothing of its own -,
// in English (docs/architecture/activity-framework-design.md, 7.4): what a check may say, by its code (the
// kinds' MESSAGES), each made with the message's arguments - the phone and the windows say it in the
// deck's language; the server sends no words. A key "<kind>:<status>" is a kind's own word for a check's
// status, in place of the core's (web/kinds.js: status): a Turtle text is valid, it does not run.
// texts/de.js has the same keys.
export default {
  at: ({ line, column, message }) => `line ${line}, column ${column}: ${message}`,
  tooDeep: ({ n }) => `nested more than ${n} levels deep`,
  service: () => "SERVICE (a query to another endpoint) is not run",
  noTriples: () => "no triples",
  tooManyTriples: ({ n }) => `more than ${n} triples`,
  engine: ({ text }) => text,                    // Oxigraph's own words, as it said them
  "turtle-graph:ok": "Valid Turtle ✓",
  "turtle-graph:timeout": "Parsing it took too long.",
  "turtle-graph:refused": "That is not taken",
};
