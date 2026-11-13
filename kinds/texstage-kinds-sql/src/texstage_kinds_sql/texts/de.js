// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The words of sql-query, in German (texts/en.js says what they are).
export default {
  changesData: () => "nur Anfragen werden ausgeführt – diese ändert die Daten",
  noStatement: () => "keine Anweisung",
  oneStatement: () => "nur eine Anweisung auf einmal",
  queriesOnly: () => "nur Anfragen werden ausgeführt: SELECT, VALUES oder WITH … SELECT",
  tooMuchMemory: () => "braucht mehr Speicher, als eine Prüfung verwenden darf",
  engine: ({ text }) => text,                    // die Worte von SQLite, wie es sie sagte
};
