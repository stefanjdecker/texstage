// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The words of texstage-kinds-rdf's kinds, in German (texts/en.js says what they are).
export default {
  at: ({ line, column, message }) => `Zeile ${line}, Spalte ${column}: ${message}`,
  tooDeep: ({ n }) => `mehr als ${n} Ebenen tief verschachtelt`,
  service: () => "SERVICE (eine Anfrage an einen anderen Endpunkt) wird nicht ausgeführt",
  noTriples: () => "keine Tripel",
  tooManyTriples: ({ n }) => `mehr als ${n} Tripel`,
  engine: ({ text }) => text,                    // die Worte von Oxigraph, wie es sie sagte
  "turtle-graph:ok": "Gültiges Turtle ✓",
  "turtle-graph:timeout": "Das Parsen dauerte zu lange.",
  "turtle-graph:refused": "Das wird nicht angenommen",
};
