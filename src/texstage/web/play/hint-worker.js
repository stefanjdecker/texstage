// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// A kind's hints, in a Web Worker of their own (docs/architecture/activity-framework-design.md, 7.3): the
// kind's web/hint.js - from the server's /kinds/... only - gets the step's public part, the student's text
// and the phone's words, and gives null or {code, args, at}. A slow or failing hint holds up nothing: the
// phone drops what comes for a text that is gone (kinds.js: Hints).
const module = new URL(new URL(self.location.href).searchParams.get("module") || "/", self.location.origin);
const loaded = module.origin === self.location.origin && module.pathname.startsWith("/kinds/")      // (as the URL
  ? import(module.href) : Promise.reject(new Error("not a kind's module"));                            // reads it: no ../)
loaded.catch(() => {});

self.onmessage = async (e) => {
  const { n, step, text, words } = e.data || {};
  let hint = null;
  try {
    const m = await loaded;
    hint = typeof m.hint === "function" ? (await m.hint(step, text, words)) ?? null : null;
  } catch {
    hint = null;
  }
  self.postMessage({ n, hint });
};
