# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pages' Content-Security-Policy (AF 7.3; the F2 plan's 4.5, package 10): one per page, and one for
every script the server sends, for when it runs as a worker. What runs in a page or a worker - texstage's
scripts and a kind's modules from /kinds/ - takes its scripts from the server and connects to the server
alone, by the browser's rule rather than by convention.

- The phone's (/play) loads the least: the server, and the hints' worker from it. Another site may frame
  it (a course's page may embed the join page); the presenter's and the projector's windows and the host
  console hold the presenter key and are framed by the server's own pages alone.
- The presenter's window (/stage) and the projector's (/stage/projector) take YouTube's and Vimeo's
  players besides (web/stage/video.js: their scripts, their frames, and Vimeo's oEmbed, which its script
  asks for every player) and a deck's video files from wherever the deck names them (build/video.py: an
  MP4 or WebM address). The presenter's compiles the engines of F1's checks (web/stage/evaluator.js), so
  it may compile WebAssembly.
- The add-in (/addin/) takes Office.js from Microsoft's CDN; PowerPoint frames it where it runs on the
  web, so it says nothing of framing.
- Only the phone's and the windows' pages start workers. A worker takes its policy from its own
  response, not from the page that starts it, so every script the server sends carries one: a kind's
  file reaches nothing as a worker, texstage's scripts reach the server (PDF.js's worker, which compiles
  WebAssembly), the hints' worker and the evaluator's have their own, and none starts a worker of its own.

Styles may be inline on every page: the pages write style attributes (web/shared/live.js, the phone's
buttons) and KaTeX does; an attribute fetches nothing the policy does not allow. Pages and workers report
what their policy refuses (`report-uri`): the server's log says it (Reports), since nobody sees the
console of a phone or of PowerPoint.

Limits. The windows load media from any address (a deck's video), so a script there can still send
something out as a video's address. No policy governs navigation (a link, `location`, `window.open`),
DNS prefetch or WebRTC: a kind is installed by the lecturer and trusted as the server's Python is (AF
7.3) - the policies shut the ways a page or a worker fetches. 'wasm-unsafe-eval' needs Chrome 97, Safari
16 or Firefox 102: an older iPad as the presenter's window cannot run F1's checks there. A proxy that
rewrites Host names its backend in the WebSocket's sources - harmless where 'self' matches ws:, as it
does in today's browsers."""
from __future__ import annotations

import json
import re
import time
import unicodedata
from urllib.parse import urlsplit

SELF = "'self'"
NONE = "'none'"
REPORTS = "/api/csp-report"
REPORT_BYTES = 8000         # a report is a few hundred bytes and the policy; more is not one

# what every page allows: its server, inline styles, the pictures it draws itself (data:, blob:)
BASE = {
    "default-src": (SELF,),
    "script-src": (SELF,),
    "style-src": (SELF, "'unsafe-inline'"),
    "img-src": (SELF, "data:", "blob:"),
    "font-src": (SELF, "data:"),
    "connect-src": (SELF,),
    "media-src": (SELF, "blob:"),
    "worker-src": (NONE,),
    "frame-src": (NONE,),
    "object-src": (NONE,),
    "base-uri": (NONE,),
    "form-action": (SELF,),
}
PLAYERS = ("https://www.youtube.com", "https://player.vimeo.com")        # their scripts (video.js: script())
FRAMES = ("https://www.youtube-nocookie.com", "https://player.vimeo.com")  # their players
OEMBED = "https://vimeo.com"                                              # Vimeo's script asks it for a player
WORKERS = {"worker-src": (SELF,)}           # the hints' (play), the evaluator's and PDF.js's (the windows)
WINDOWS = {
    **WORKERS,
    "script-src": (SELF, *PLAYERS),
    "connect-src": (SELF, OEMBED),
    "media-src": (SELF, "blob:", "https:", "http:"),    # a deck's video file online
    "frame-src": FRAMES,
    "frame-ancestors": (SELF,),
}
PAGES = {
    "play": WORKERS,
    "stage": {**WINDOWS, "script-src": (SELF, "'wasm-unsafe-eval'", *PLAYERS)},
    "projector": WINDOWS,
    "host": {"frame-ancestors": (SELF,)},
    "addin": {"script-src": (SELF, "https://appsforoffice.microsoft.com")},
}
# the pages' files, as /static serves them too: with the same policy there
FILES = {"play/index.html": "play", "stage/index.html": "stage", "stage/projector.html": "projector",
         "host/index.html": "host", "addin/index.html": "addin"}
HOST = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?", re.IGNORECASE)


def header(directives: dict) -> str:
    """Directives as a policy's header says them, reporting what it refuses."""
    return "; ".join(f"{name} {' '.join(sources)}" for name, sources in directives.items()) + f"; report-uri {REPORTS}"


# a script as a worker: a kind's file and the hints' worker fetch nothing (the hints' worker imports a
# kind's hint.js and what it imports, from the server); texstage's scripts the server alone, compiling
# WebAssembly (PDF.js's worker); the evaluator's runs the students' queries, which reach nothing
KIND = header({"default-src": (NONE,), "script-src": (SELF,), "worker-src": (NONE,)})
HINTS = KIND
SCRIPT = header({"default-src": (NONE,), "script-src": (SELF, "'wasm-unsafe-eval'"), "connect-src": (SELF,),
                 "worker-src": (NONE,)})
EVALUATOR = header({"connect-src": (NONE,), "worker-src": (NONE,)})
SCRIPTS = {"play/hint-worker.js": HINTS, "stage/evaluator-worker.js": EVALUATOR}
OTHER = header({"default-src": (NONE,), "base-uri": (NONE,), "form-action": (NONE,), "frame-ancestors": (NONE,)})


def policy(page: str, host: str | None = None) -> str:
    """The page's policy as its header says it. host: the request's Host - its WebSocket addresses
    (ws:, wss:) are named besides 'self', which matches them by CSP 3 but not in every browser a phone
    may have (an IPv6 address cannot be named: 'self' alone then)."""
    directives = {**BASE, **PAGES[page]}
    if host and HOST.fullmatch(host):
        directives["connect-src"] = (*directives["connect-src"], f"ws://{host}", f"wss://{host}")
    return header(directives)


def of_file(path: str, host: str | None = None) -> str:
    """The policy for a file of web/ that /static serves (its path below web/, with /): a page's its page's,
    a script its own for when it runs as a worker; any other HTML file nothing."""
    if path in FILES:
        return policy(FILES[path], host)
    if path.lower().endswith((".js", ".mjs")):
        return SCRIPTS.get(path, SCRIPT)
    return OTHER


class Reports:
    """What the policies refused, as the browsers report it (report-uri): one line in the log per page or
    worker, directive and what was refused - 1,000 phones refused the same say it once -, at most `most`
    new lines in `window` seconds, the rest counted. kinds: the names of the kinds whose files have a hash
    (/kinds/<hash>/...), so that a line says whose file it was. A report is the browser's, so anybody's:
    one that cannot be read is none; what is logged is cut short, without control or format characters."""

    def __init__(self, most: int = 20, window: float = 60.0, kept: int = 500, clock=time.monotonic, kinds=None):
        self.most, self.window, self.kept, self.clock = most, window, kept, clock
        self.kinds = kinds or (lambda digest: "")
        self.seen: set[tuple] = set()
        self.times: list[float] = []
        self.dropped = 0

    def take(self, body: bytes) -> str | None:
        """The log line for a report (a request's body), or None: not one, said already, or too many."""
        try:
            read = self.read(body)
        except Exception:               # (urlsplit's ValueError, a RecursionError of deep JSON ...): none
            return None
        if read is None:
            return None
        key, line = read
        if key in self.seen:
            return None
        now = self.clock()
        self.times = [t for t in self.times if now - t < self.window]
        if len(self.times) >= self.most:
            self.dropped += 1
            return (f"more than {self.most} new refusals in {self.window:g} s: the next are counted, not logged"
                    if self.dropped == 1 else None)
        if len(self.seen) < self.kept:
            self.seen.add(key)
        self.times.append(now)
        more, self.dropped = self.dropped, 0
        return line + (f" - and {more} more {'report' if more == 1 else 'reports'} since, not logged" if more else "")

    def read(self, body: bytes) -> tuple[tuple, str] | None:
        """(its key, its line) of a report - None if it is none (no page or worker, no directive)."""
        if len(body) > REPORT_BYTES:
            return None
        report = json.loads(body.decode("utf-8", "replace")).get("csp-report")
        if not isinstance(report, dict):
            return None
        document = urlsplit(clean(report.get("document-uri"))).path
        directive = clean(report.get("effective-directive") or report.get("violated-directive")).split(" ")[0]
        if not document or not directive:
            return None
        blocked = clean(report.get("blocked-uri")) or "inline"
        parts = urlsplit(blocked)
        if parts.netloc:                                   # an address by its origin, without user or password
            what = f"{parts.scheme}://{parts.hostname}" + (f":{parts.port}" if parts.port else "")
        else:
            what = blocked
        source = urlsplit(clean(report.get("source-file"))).path      # (without its query: no PIN, no key)
        number = report.get("line-number")
        at = f" ({self.name(source)}:{number})" if source and type(number) is int else ""
        kind = "worker" if document.lower().endswith((".js", ".mjs")) else "page"
        return (document, directive, what), f"the {kind} {self.name(document)} refused {directive} {what}{at}"

    def name(self, path: str) -> str:
        """A page or a script as the log names it: a kind's file by its kinds, one of web/ by its path there."""
        if m := re.fullmatch(r"/kinds/([0-9a-f]+)/(.+)", path):
            return f"{self.kinds(m[1]) or 'a kind'}: {m[2]}"
        if path.startswith("/static/"):
            return path[len("/static/"):]
        return path


def clean(value) -> str:
    """A report's value as the log may take it: text without control or format characters (no line
    breaks, no bidi controls), cut short."""
    text = str(value or "")[:400]
    return "".join(" " if unicodedata.category(c)[0] == "C" else c for c in text)[:200].strip()
