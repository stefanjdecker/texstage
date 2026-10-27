# Vendored libraries

Third-party code the pages load from the server itself, so that presenting works without a
network (docs/texstage-design.md, section 2). Each folder holds the files as published, with
their licence; nothing here is edited.

| Folder | Library | Version | Licence | Files |
|---|---|---|---|---|
| `pdfjs/` | PDF.js (`pdfjs-dist` on npm) | 6.4.299 | Apache-2.0 | `build/pdf.min.mjs`, `build/pdf.worker.min.mjs`, `LICENSE` |
| `perfect-freehand/` | perfect-freehand (Steve Ruiz) | 1.2.3 | MIT | `dist/esm/index.mjs`, `LICENSE` |
| `pdf-lib/` | pdf-lib (Andrew Dillon) | 1.17.1 | MIT | `dist/pdf-lib.esm.min.js`, `LICENSE.md` |
| `katex/` | KaTeX (Khan Academy and contributors) | 0.19.0 | MIT | `dist/katex.min.js`, `dist/katex.min.css`, `dist/fonts/*.woff2`, `LICENSE` |
| `oxigraph/` | Oxigraph (Oxigraph developers) | 0.5.11 | MIT OR Apache-2.0 | `web.js`, `web_bg.wasm`, `LICENSE-MIT`, `LICENSE-APACHE` |
| `sqljs/` | sql.js (sql.js authors) - SQLite, in the public domain | 1.14.2 | MIT | `sql-wasm-browser.js`, `sql-wasm-browser.wasm` (from `dist/`), `LICENSE`, `AUTHORS` |

PDF.js renders texstage's stage PDF (`web/stage/pdfview.js`). Taken from
`npm pack pdfjs-dist@6.4.299` (tarball integrity
`sha512-AVl138zALtfaAPvADulE0PZThbYzCBS79nL4pOSL/6Sm/4AH5A21BD9VHt97OlCuzJuCpmeZtAtkinisF4Vb1g==`,
checked by npm). Not taken: the WebAssembly decoders (JPEG 2000 images; ICC colour
profiles, for which PDF.js falls back to the profile's plain colour space), the CMaps (CJK
fonts without embedded encodings) and the standard fonts (base-14 fonts not embedded) -
Beamer PDFs from pdfTeX embed their fonts; a JPEG 2000 picture in a deck would not show.

perfect-freehand turns the points of a pen stroke, with their pressure, into the outline of the
stroke (`web/stage/ink.js`). Taken from `npm pack perfect-freehand@1.2.3` (tarball integrity
`sha512-bHZSfqDHGNlPpgH2yxXgPHlQSPpEbo+qg7li0M78J9vNAi2yjwLeA4x79BEQhX44lEWpCLSFCeRZwpw0niiXPA==`).

pdf-lib writes the annotated PDF for the students in the presenter window (`web/stage/export.js`):
the slide pages copied from the stage PDF, the ink drawn into them as vector paths. Taken from
`npm pack pdf-lib@1.17.1` (tarball integrity
`sha512-V/mpyJAoTsN4cnP31vc0wfNA1+p20evqqnap0KLoRUN0Yk/p3wN52DOEsL4oBFcLdb76hlpKPtzJIgo67j/XLw==`); the
bundle includes its dependencies pako (MIT and zlib), @pdf-lib/standard-fonts (MIT), @pdf-lib/upng
(MIT) and tslib (0BSD). Its last release was in 2022.

KaTeX typesets the formulas (`$...$`) in texts typed during the lecture - ad-hoc polls and
questions (texstage M6, `web/shared/text.js`) - on the phones, the projector and the presenter
window; a page loads it only when a text holds a formula. Taken from `npm pack katex@0.19.0`
(tarball integrity
`sha512-v6Tznz3zJ7u3niRCoDTsumM2+HA2XXcCu+WAacCeHD2z3p9A9Ks987o5FzfTGBN0e8A0vjEgIDvLbICrXpdw/Q==`,
checked). Not taken: the fonts as WOFF and TTF (the stylesheet names them after the WOFF2
files, which every current browser reads, so they are never fetched), the ES module (the same
code, not minified) and the contrib extensions.

To update: `npm pack <package>@<version>`, unpack it, copy the files over and change the
version and integrity above.

Oxigraph runs the live activities' SPARQL queries in the presenter window's worker
(`web/stage/evaluator-worker.js`, the engine `web/engines/sparql.js`; docs/live-activities-design.md,
section 8), and its Turtle parser reads the Turtle engine's texts (`web/engines/turtle.js`, section
8.9). Taken from `npm pack oxigraph@0.5.11` (2026-09-02; tarball integrity
`sha512-zKdgmp1tsrutGzC1lCCywwZRPpLJKaJnKSDWoY2hIhMiwiCRRXNN1DU7WUyTInBvgPKT8Y5N+RgwTL8qKXpLng==`,
checked by npm): its browser build, `web.js` and `web_bg.wasm` (4.0 MB). Not taken: the Node build,
the TypeScript declarations and the README. The package carries no licence files: `LICENSE-MIT` and
`LICENSE-APACHE` are the repository's (github.com/oxigraph/oxigraph) at the release's tag, v0.5.11
(fetched 2026-10-17).
Oxigraph is licensed under either of them, at the licensee's option.

sql.js runs the live activities' SQL queries in the same worker (the engine `web/engines/sql.js`;
docs/live-activities-design.md, section 8.8): SQLite compiled to WebAssembly. Taken from
`npm pack sql.js@1.14.2` (released 2026-08-14 - 1.15.0, four days old, was passed over; fetched
2026-10-18; tarball integrity
`sha512-3ZGPovObMFrdw79zrUHbfdE/DLIsy8jdNdssmMSQuRAymedU6q84asPt0kgiqrdMYlPegDItiIMfmIXzZnYFcw==`,
checked by npm and again by hand): its browser build, `dist/sql-wasm-browser.js` and
`dist/sql-wasm-browser.wasm` (0.7 MB), with `LICENSE` and the `AUTHORS` it names. Not taken: the
asm.js builds, the debug builds, the builds for Node and for a worker of their own, the zip files.
The browser build is a UMD script, not an ES module; the engine loads it as published (sql.js,
`start`).
