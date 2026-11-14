// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The words of texstage's own kinds - choice, number, text -, in English (docs/architecture/activity-framework-
// design.md, 7.4). Their checks say nothing of their own (no MESSAGES); a key "<kind>:<status>" is a kind's own
// word for a check's status in place of the core's (web/kinds.js: status) - a choice is chosen, a number or a
// text is received, none of them runs. texts/de.js has the same keys.
export default {
  "choice:ok": "Chosen ✓",
  "number:ok": "Received ✓",
  "text:ok": "Received ✓",
  // what normalize refused (the core's word would be "Syntax error"): the reason follows in the core's words
  "choice:invalid": "Not taken",
  "number:invalid": "Not taken",
  "text:invalid": "Not taken",
};
