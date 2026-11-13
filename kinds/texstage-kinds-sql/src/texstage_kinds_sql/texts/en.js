// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The words of sql-query, in English (docs/architecture/activity-framework-design.md, 7.4): what a check
// may say, by its code (the kind's MESSAGES), each made with the message's arguments - the phone and the
// windows say it in the deck's language; the server sends no words. texts/de.js has the same codes.
export default {
  changesData: () => "only queries are run - this one changes the data",
  noStatement: () => "no statement",
  oneStatement: () => "one statement at a time",
  queriesOnly: () => "only queries are run: SELECT, VALUES or WITH ... SELECT",
  tooMuchMemory: () => "needs more memory than a check may use",
  engine: ({ text }) => text,                    // SQLite's own words, as it said them
};
