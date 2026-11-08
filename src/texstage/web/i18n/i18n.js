// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The texts of texstage's windows and phones in the languages they speak - English and German so
// far -, area by area (en.js lists them): what the views over a slide say (live), a live activity's
// box on the projector (box), the phone (phone) and its activity screen (activity), the server's
// refusals by their code (errors), and the presenter, projector, host and add-in windows.
//
// Everything a deck's audience or its lecturer reads speaks the deck's language: deck.json's
// "language", babel's (or polyglossia's) main language as the build found it - a BCP 47 tag, de or
// en (build/bundle.py, language_tag) -, English for any other and for a deck built before
// 2026-10-24, which names none. A page that shows no deck yet - the phone's join form, the list of
// decks, a device being paired - speaks its browser's language until a deck says its own.
//
//   import { texts } from "../i18n/i18n.js";
//   const T = texts(deck.language).phone;          T.join  T.rank(2, 17)
//
// A text is a string or a function of what it names (a count, a name): German has every text
// English has, functions with the same arguments (tests/web-i18n.test.mjs). Another language is
// a catalog like de.js and its line in CATALOGS, its babel names in build/bundle.py (LANGUAGES), its
// slide texts in latex/texstage.sty and its words for the polls typed in a lecture in
// server/polls.py (WORDS) - a text it lacks stays English.
//
// A window that shows one deck at a time says what it is in usePageLanguage(deck.language) - and
// usePageLanguage(null) when it shows none again -: its parts that get no deck of their own (the
// dialogs of ask.js, the upload button) speak pageTexts().

import en from "./en.js";
import de from "./de.js";

export const CATALOGS = Object.freeze({ en, de });

const own = (o, key) => Object.prototype.hasOwnProperty.call(o, key);
const isTable = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// whether a tag names a language with texts: de, de-AT, DE_ch -> de; fr, "" -> null
export function supported(tag) {
  const base = String(tag ?? "").trim().toLowerCase().split(/[-_]/)[0];
  return base && own(CATALOGS, base) ? base : null;
}

// the language a tag gets: its own if there are texts for it, else English
export function languageOf(tag) {
  return supported(tag) || "en";
}

// the browser's language, for a page before its deck: the first of the browser's languages
// with texts (navigator.languages: fr, de -> de), else English
export function browserLanguage() {
  const nav = globalThis.navigator || {};
  for (const tag of [...(Array.isArray(nav.languages) ? nav.languages : []), nav.language]) {
    const lang = supported(tag);
    if (lang) return lang;
  }
  return "en";
}

// a catalog over English's, table by table: a text the catalog lacks stays English
function over(base, mine) {
  const out = {};
  for (const [key, value] of Object.entries(base)) {
    out[key] = !own(mine, key) ? value : isTable(value) && isTable(mine[key]) ? over(value, mine[key]) : mine[key];
  }
  return out;
}

const cache = new Map();

// all texts of the language a tag gets (languageOf), area by area: texts("de").phone.join
export function texts(tag) {
  const lang = languageOf(tag);
  if (!cache.has(lang)) cache.set(lang, Object.freeze(lang === "en" ? en : over(en, CATALOGS[lang])));
  return cache.get(lang);
}

// what a refusal says in a language: the text of its code (err.code - the server's error, a
// login's or a request's), else - a code no person meets in normal use - the server's own words
// after a sentence that says it did not work
export function errorText(tag, err) {
  const E = texts(tag).errors;
  const code = err?.code;
  if (typeof code === "string" && own(E, code) && code !== "unexpected") {
    const text = E[code];
    return typeof text === "function" ? text(err) : text;
  }
  const detail = String((typeof err === "string" ? err : err?.message) ?? "").trim();
  return detail ? E.unexpected(detail) : E.failed;
}

// the language a page speaks, on its <html lang> (screen readers, hyphenation)
export function markLanguage(tag) {
  const root = globalThis.document?.documentElement;
  if (root) root.lang = languageOf(tag);
}

let page = null;           // the deck's language while the page shows one (usePageLanguage)

// the page's language from now on - its deck's (a tag), or the browser's (null: no deck); its texts
export function usePageLanguage(tag) {
  page = tag === undefined || tag === null ? null : languageOf(tag);
  markLanguage(pageLanguage());
  return pageTexts();
}

export function pageLanguage() {
  return page ?? browserLanguage();
}

export function pageTexts() {
  return texts(pageLanguage());
}
