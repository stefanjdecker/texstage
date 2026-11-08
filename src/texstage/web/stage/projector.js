// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// texstage's projector window (docs/texstage-design.md, sections 4-7): the slide the lecturer
// shows, full screen and without any controls - the stage PDF's page with the live quiz views
// (live.js), a video (video.js, with the sound), a live activity's picture (activity.js), the ink, the laser pointer, zoomed if the
// presenter zooms, or a whiteboard page -,
// black, white or frozen when the presenter window says so. It sends nothing to the server
// (role display) but asks for a frame's ink - and sends a pen's, when the window is on a pen display
// in the hall (pen.js: under the presenter window's name, so its undo takes it); its keys go to the presenter window
// (BroadcastChannel), so a clicker works whichever of the two has the focus. When the presenter
// window opens another deck, this window follows in place: it stays full screen, and a screen
// share or a recording of it goes on. It speaks the deck's language (i18n.js: its own few texts
// are "projector", the slide's views are live.js's), before the deck the browser's.

import { errorText, pageLanguage, pageTexts, usePageLanguage } from "/static/i18n/i18n.js";
import { Client, hostFetch } from "/static/shared/client.js";
import { Stage } from "/static/shared/live.js";
import { InkBook, InkLayer, PointerLayer } from "/static/stage/ink.js";
import { PdfDeck, PdfSurface, fit, inkKey, linkable, shownSlide, zoomOverlay } from "/static/stage/pdfview.js";
import { Pen } from "/static/stage/pen.js";
import { VideoBox, mediaAddresses } from "/static/stage/video.js";
import { ActivityBox } from "/static/stage/activity.js";

const $ = (sel) => document.querySelector(sel);
const KEY = "texquiz:presenter-key";
const words = () => pageTexts().projector;     // in the window's language: the deck's, before it the browser's
const why = (err) => errorText(pageLanguage(), err);   // a refusal (hostFetch's: its code) in the window's language

let bundle = new URLSearchParams(location.search).get("bundle");
let key = null;
let deck = null;
let pdf = null;
let stage = null;
let state = null;
let client = null;
let channel = null;
let book = null;        // the ink (ink.js)
let ink = null;
let laser = null;
let held = null;        // while frozen: the state when it froze - the live views do not move on either
let heldAt = null;      // the server clock at that instant, including countdowns and live media
let shown = { frame: null, zoom: null };    // the ink's frame on the screen, and the zoom: for the pen
let page = null;        // the stage PDF's page on the screen (its links), or null
let idle = null;

start();

async function start() {
  usePageLanguage(null);
  document.title = words().title;
  key = (() => { try { return localStorage.getItem(KEY); } catch { return null; } })();
  if (!key) {
    try {
      key = (await (await fetch("/api/presenter-key")).json()).key || null;   // only on the server's machine
    } catch { key = null; }
  }
  if (!key || !bundle) return hint(words().open, true);
  new BroadcastChannel("texstage").onmessage = (e) => {
    if (e.data?.type === "deck" && typeof e.data.bundle === "string" && e.data.bundle !== bundle) load(e.data.bundle);
  };
  await load(bundle);
}

async function load(b) {
  bundle = b;
  history.replaceState(null, "", `${location.pathname}?bundle=${encodeURIComponent(b)}`);   // a reload: this deck
  client?.close();
  channel?.close();
  client = channel = state = held = heldAt = null;
  let d, p;
  try {
    d = await (await hostFetch(`/api/deck/${encodeURIComponent(b)}`, key)).json();
    p = await PdfDeck.open(d.bundle, key);
  } catch (err) {
    return hint(why(err), true);
  }
  if (b !== bundle) return p.close();             // another deck came meanwhile
  pdf?.close();
  deck = d;
  pdf = p;
  usePageLanguage(deck.language || "");           // (a deck built before 2026-10-24 names none: English)
  const aspect = deck.pdf.width / deck.pdf.height;
  document.documentElement.style.setProperty("--tq-aspect", String(aspect));
  document.title = `${deck.name} - texstage`;
  const box = Object.assign(document.createElement("div"), { id: "stage" });
  $("#stage").replaceWith(box);
  stage = new Stage(box, { surface: new PdfSurface(pdf),
    sketches: (quiz, players) => client.send({ t: "sketch.get", quiz, players }).then((r) => r.sketches),
    types: { video: VideoBox, activity: ActivityBox },   // a video with the sound; a click into this window, if the browser wants one
    host: { role: "projector", media: mediaAddresses(d.bundle, key), click: (what) => channel?.postMessage({ type: "video", click: what }),
      read: (msg) => client.send(msg) } });           // (an activity's picture: activity.view)
  fit(box, aspect);
  channel = new BroadcastChannel(`texstage:${deck.bundle}`);
  const own = client = new Client({
    onState: (m) => { state = m; render(); },
    onStatus: (s) => {
      if (s === "open" && book?.loaded.size) {                  // back after a break: the ink anew
        book.reset();
        ink.reload();
      }
    },
    onEvent: (m) => {
      if (m.t === "ink" && m.op === "reload") {                 // a new presentation, or a lecture continued
        book.reset();
        ink.reload();
      } else if (m.t === "ink") book.event(m);
      else if (m.t === "pointer") {
        if (m.off) laser.off();
        else laser.move(m.x, m.y);
      }
    },
  });
  book = new InkBook(client);
  ink = new InkLayer(book, aspect);
  laser = new PointerLayer(aspect);
  box.append(ink.element, laser.element);
  new Pen(box, { book, laser, aspect, where: () => shown, raw: (m) => client.raw(m),
    send: (m) => client.send(m).catch((err) => hint(why(err), false)) });
  linkable(box, { pdf: () => pdf, page: () => page, active: (e) => e.pointerType !== "pen",   // a pen writes
    at: (e) => {
      const r = box.getBoundingClientRect();
      const v = shown.zoom || { x: 0, y: 0, w: 1, h: 1 };
      return [v.x + ((e.clientX - r.left) / r.width) * v.w, v.y + ((e.clientY - r.top) / r.height) * v.h];
    } });
  try {
    await own.login({ t: "hello", role: "display", key, deck: deck.deck, bundle: deck.bundle });
  } catch (err) {
    if (own === client) hint(why(err), true);
    return;
  }
  hint(document.fullscreenElement ? "" : words().full, false);
}

function render() {
  const screen = state.stage?.screen;
  if (screen === "freeze") {
    if (!held) { held = state; heldAt = client.now(); }
  } else {
    held = heldAt = null;
  }
  const view = held || state;
  const slide = shownSlide(deck, view);                 // (M6: a poll or sketches instead of the slide)
  const zoom = slide?.overlay ? null : view.stage?.zoom || null;
  stage.surface.zoom = zoom;
  stage.show(slide, deck, view, () => heldAt ?? client.now());
  zoomOverlay($("#stage"), zoom);
  ink.show(inkKey(slide), zoom);
  shown = { frame: inkKey(slide), zoom };
  page = slide && !slide.board && !slide.overlay ? slide.page || null : null;
  if (page) pdf.links(page);                            // its links ready for the first click
  laser.show(zoom);
  $("#cover").className = `cover ${screen === "black" || screen === "white" ? screen : ""}`;
  const i = deck.slides.indexOf(slide);
  const [w, h] = stage.surface.size();
  if (i >= 0 && !zoom) pdf.prefetch(deck.slides.slice(i + 1, i + 3).map((s) => [s.page, w, h]));
}

function hint(text, stay) {
  const el = $("#hint");
  el.textContent = text;
  el.classList.toggle("stay", stay);
  el.classList.toggle("show", Boolean(text));
  clearTimeout(el.timer);
  if (!stay) el.timer = setTimeout(() => el.classList.remove("show"), 3000);
}

document.addEventListener("click", () => {
  if (deck && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
});

document.addEventListener("fullscreenchange", () => {
  if (document.fullscreenElement) hint("", false);
});

document.addEventListener("mousemove", () => {
  document.body.classList.remove("idle");
  clearTimeout(idle);
  idle = setTimeout(() => document.body.classList.add("idle"), 2000);
  if (deck && !document.fullscreenElement) hint(words().full, false);
});

document.addEventListener("keydown", (e) => {
  if (!channel || e.ctrlKey || e.metaKey || e.altKey || e.key === "F11") return;
  channel.postMessage({ type: "key", key: e.key });
  e.preventDefault();
});
