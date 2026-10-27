// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Texts typed during the lecture (texstage M6): ad-hoc polls and the audience's questions, with
// formulas between $...$, typeset by KaTeX (web/vendor/katex). A page loads KaTeX the first time
// a text holds a formula; until it is there, the text shows as typed, and `onReady` says when
// to draw it again.
//
//   el.innerHTML = textHTML("Is $O(n \\log n)$ optimal?", () => redraw());

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const MATH = /(\$[^$\n]+\$)/;

let katex = null;
let loading = null;

export function hasMath(text) {
  return MATH.test(String(text ?? ""));
}

export function loadMath() {
  if (katex) return Promise.resolve(katex);
  loading ||= new Promise((resolve, reject) => {
    const css = Object.assign(document.createElement("link"), { rel: "stylesheet", href: "/static/vendor/katex/katex.min.css" });
    const js = Object.assign(document.createElement("script"), { src: "/static/vendor/katex/katex.min.js" });
    js.onload = () => {
      katex = window.katex;
      resolve(katex);
    };
    js.onerror = () => {
      loading = null;                               // try again with the next text
      reject(new Error("KaTeX did not load"));
    };
    document.head.append(css, js);
  });
  return loading;
}

function typeset(tex) {
  try {
    // the audience types these too: no links or other trusted commands, bounded sizes
    return katex.renderToString(tex, { throwOnError: false, trust: false, strict: "ignore", maxSize: 20, maxExpand: 200 });
  } catch {
    return esc(`$${tex}$`);
  }
}

// the text as HTML: escaped, its line breaks kept, its formulas typeset (once KaTeX is there)
export function textHTML(text, onReady = null) {
  const parts = String(text ?? "").split(MATH);
  if (parts.length > 1 && !katex) loadMath().then(() => onReady?.()).catch(() => {});
  return parts.map((p, i) => (i % 2 && katex ? typeset(p.slice(1, -1)) : esc(p).replace(/\n/g, "<br>"))).join("");
}
