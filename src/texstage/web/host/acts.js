// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// The host console's line of the deck's live activities, with --activities core (host.js; docs/
// architecture/activity-framework-design.md, 13): each one's phase - and of the current one its time
// left, which counts down between the server's pushes (the server tells a running time once, with when
// it read it), and its counts, from the lecturer's picture (activity.view: whatever the projector holds
// back). The picture is asked for when the step's version changes, at most every ASK_MS - a change that
// comes sooner is asked for when that time is up, not dropped.

import { clock, timeLeft } from "../play/activities.js";

export const ASK_MS = 2000;
export const TICK_MS = 1000;

const timers = {
  now: () => Date.now(),
  after: (f, ms) => setTimeout(f, ms),
  every: (f, ms) => setInterval(f, ms),
  cancel: (t) => { clearTimeout(t); clearInterval(t); },
};

export class ActsLine {
  // read(msg) -> the server's reply; now() -> the server's clock; render() draws the line anew
  constructor({ read, now, render, time = timers }) {
    this.read = read;
    this.now = now;
    this.render = render;
    this.time = time;
    this.acts = null;                // the windows' part of the state: {current, items}
    this.picture = null;             // {id, version, picture}
    this.asked = -Infinity;          // when the last picture was asked for
    this.busy = false;
    this.later = null;               // an ask put off
    this.ticker = null;              // the time counting down
  }

  update(acts) {
    // the state as it came: the picture asked for if the current step's version is another
    this.acts = acts || null;
    const cur = acts?.current ? acts.items?.[acts.current] : null;
    if (cur && (this.picture?.id !== acts.current || this.picture.version !== cur.version)) this.ask();
    const running = Boolean(cur && cur.phase === "open" && cur.time !== null && cur.time !== undefined);
    if (running && this.ticker === null) this.ticker = this.time.every(() => this.render(), TICK_MS);
    else if (!running && this.ticker !== null) {
      this.time.cancel(this.ticker);
      this.ticker = null;
    }
  }

  ask() {
    if (this.busy || this.later !== null) return;
    const wait = ASK_MS - (this.time.now() - this.asked);
    if (wait > 0) {                  // (asked a moment ago: asked again when the time is up)
      this.later = this.time.after(() => { this.later = null; this.update(this.acts); }, wait);
      return;
    }
    const id = this.acts.current, version = this.acts.items[id].version;
    this.asked = this.time.now();
    this.busy = true;
    this.read({ t: "activity.view", activity: id }).then((r) => {
      this.busy = false;
      this.picture = { id, version, picture: r.picture };
      this.render();
      this.update(this.acts);        // (a newer version meanwhile)
    }, () => { this.busy = false; });
  }

  said(id, words) {
    // what the line says of an activity besides its phase: of the current one, its time left and its counts
    const st = this.acts?.items?.[id];
    if (!st || id !== this.acts.current) return "";
    const p = this.picture?.id === id ? this.picture.picture : null;
    const left = timeLeft({ phase: st.phase, time: st.time, since: st.since }, this.now());
    return [left === null ? "" : clock(left), p && !p.held ? words.counts(p.students || 0, p.entries || 0, p.waiting || 0) : ""]
      .filter(Boolean).join(" · ");
  }

  destroy() {
    if (this.later !== null) this.time.cancel(this.later);
    if (this.ticker !== null) this.time.cancel(this.ticker);
    this.later = this.ticker = null;
  }
}
