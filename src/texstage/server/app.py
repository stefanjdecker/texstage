# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The texstage server: HTTP and WebSocket around the engine (docs/design.md, sections 6-8).

    GET /                                    -> /play;  GET /api/status: status (no PINs, no names)
    GET /play                                the phone page; /host the host console
    GET /stage, /stage/projector             texstage: the presenter and the projector window
    GET /static/...                          their scripts and styles (texstage/web/)
    GET /api/presenter-key                   the presenter key, only to the machine itself:
                                             PowerPoint on the laptop pairs without typing it
    POST /api/pair, GET|POST /api/pair/<t>,  texstage: pairing a presenter device (devices.py) -
        GET /api/devices, DELETE ...<id>     with the presenter key; the device: POST
                                             /api/pair/claim {token, name}, /api/pair/wait {claim}
    GET /api/decks, /api/deck/<bundle>,      for hosts (header X-Texquiz-Key, or a paired
                                             device's X-Texquiz-Device): the bundles,
        /api/deck/<bundle>/pdf,              a bundle's deck.json, its stage PDF (texstage;
        /api/results/<session>.csv           it holds every reveal page), a game's results
    PATCH|DELETE /api/decks/<deck>,          texstage's deck page (library.py), for hosts: a deck's
        GET|POST /api/folders,               folder and shown name, off the list (an uploaded deck
        PATCH|DELETE /api/folders/<id>       deleted); the lecturer's folders
    PUT /api/archive/<session>/annotated.pdf, GET /api/archive/<session>.zip
        GET /api/archive/<session>/files     texstage: the lecture archive, <data>/archive/<deck>/<date>-<pin>/
    POST /api/archive/<session>/recording {ext} -> {take}, PUT /api/recording/<take>/<part>,
        POST /api/recording/<take>/done, GET /api/recording/<take>,
        POST /api/recording/<take>/download -> {url}: /download/<ticket>/<name> (archive.py)
                                             texstage: a recording, in parts while it is made
    PUT /api/bundles/<id>                    for hosts: a bundle (zip), from texstage publish
    POST /api/bundles                        for hosts: a deck's .bundle.zip uploaded by hand (the ID: its deck.json's)
    GET /addin/, /addin/manifest.xml         the PowerPoint add-in's page and manifest
    GET /bundle/<id>/<slides|phone>/<h>.png  pictures; their names are content hashes that
                                             only deck.json lists, and deck.json only hosts
                                             get - reveal slides stay with the hosts
    GET /join/<pin>.svg                      QR code of the join URL
    WS  /ws                                  the game (below)

Protocol: one WebSocket per client, JSON messages {"t": type, ...}. A command may carry an
"id"; the reply ("ok", "welcome", "error") carries it back as "re", and a command resent
with the same id (after a reconnect) is answered from a cache instead of being run twice
(not the commands that only read: they run again).

    any     hello {role: "host"|"stage"|"display", key | device, deck, bundle}   -> welcome {role, session}
            join {pin, nickname, join_nonce?}         -> welcome {role, player, token}
            resume {token}                            -> welcome {role, player}
            ping                                      -> pong {now}
    host    slide {slide}  skip/pause/continue/reveal/again {quiz?}  extend {quiz?, seconds}
            kick {player}  rename {player, nickname}  finish  restart  prepare {on}
    stage   (texstage's presenter window) what a host can, and
            screen {screen: live|black|white|freeze}  timer {action: start|pause|reset|target, seconds?}
            zoom {rect: {x, y, w, h} | null}  board {after, kind: blank|grid} -> {board}  go {board}
            pointer {x, y} | {off}   (no answer when sent without an id; texstage sends one
                    position at a time, the next when this one is answered - no backlog)
            ink.begin {device, frame, stroke: {id, tool, color, width, sim}, points}
            ink.points {stroke, points}  ink.end {stroke}  ink.erase {device, frame, strokes}
            ink.clear / ink.undo / ink.redo {device, frame} -> {event}  ink.load {frame} -> {strokes, drawing}
            ink.all -> {frames: {frame: [strokes]}}   (the annotated PDF)
            (M6) poll.create {kind, prompt?, answers?, select?, time?} -> {quiz}  poll.show {quiz | null}
            sketch.list {quiz, after?, round?} -> {round, cursor, active, sketches: [{n, player, strokes}]}
            sketch.show {quiz, players}
            qa.open {on}  qa.show {question | null}  qa.mark {question, state: open|done|deleted}
            qa.block {question}
            a new presentation, or an earlier lecture continued - its welcome says what there is,
            earlier: {game, open, at, frames, boards} | null, and presenters (its other windows):
            lecture.new -> {session, pin} (a new game without the ink and the whiteboard pages)
            lecture.continue {game} -> {frames, boards} (copies of an ended game's ink and pages)
    display (texstage's projector window) only ink.load, sketch.get {quiz, players} -> {sketches}, and a pen's
            ink on its screen (a pen display in the hall): ink.begin, ink.points, ink.end, ink.erase,
            and its side button's laser: pointer {x, y} | {off}
    player  answer {round, answer}  (M6) qa.ask {text} -> {question}  qa.vote {question, on}
            qa.watch {on}   (the phone shows the questions: its states carry them)

Ink and pointer go to the game's other texstage windows as they happen: {"t": "ink", op:
begin|points|end|erase|restore, ...} and {"t": "pointer", x, y | off} (ink.py); {"t": "ink",
op: "reload"} after lecture.new and lecture.continue: the ink anew.

The server pushes {"t": "state", "now": <ms>, "role": ...} with the role's view (game.py)
after every change - players at once, hosts (and stage and display windows: the host view)
at most every 200 ms while answers come in, phones that show the audience's questions their
changes at most every 500 ms - and {"t": "bye", reason} when a player is removed or the game
is over. "now" is the server's clock: clients compute their offset and count down locally.
"""
from __future__ import annotations

import asyncio
import contextlib
import csv
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import time
import zipfile
import zlib
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import segno
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from texstage import __version__
from texstage.builds import build_folders
from texstage.keys import load_presenter_key  # noqa: F401  (the server's key: texstage serve)
from texstage.server import archive
from texstage.server import types as stage_types
from texstage.server.archive import ArchiveError, Recordings
from texstage.server.bundles import BundleError, BundleStore, holds, load_bundle
from texstage.server.devices import PAIR_MS, Devices
from texstage.server.lecturers import Lecturers
from texstage.server.library import Library, LibraryError
from texstage.server.game import Engine, GameError, Settings, clean_nickname, token_hash
from texstage.server.store import Store
from texstage.plugins import PluginError
from texstage.plugins.policy import catalog_for
from texstage.server.plugins import PluginHost

log = logging.getLogger("texstage.server")
HOST_PUSH_S = 0.2           # live counts to the hosts: at most 5 updates a second
QA_PUSH_S = 0.5             # the audience's questions and votes to the phones that show them
READS = {"ink.load", "ink.all", "sketch.list", "sketch.get"}    # answered anew, not from the reply cache
MESSAGE_MAX = 16 * 1024
REPLY_CACHE = 64
JOIN_REPLAY_MS = 10 * 60_000                     # a welcome lost while a phone reconnects
JOIN_REPLAY_MAX = 10_000
JOIN_NONCE = re.compile(r"[0-9a-f]{32}")          # 128 random bits, independent of request ids
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
FORWARDED = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip",    # set by proxies
             "cf-connecting-ip")                                                # (Cloudflare's tunnel)
WEB = Path(__file__).resolve().parents[1] / "web"
BUNDLE_MAX = 200 * 1024 * 1024                       # a published bundle, packed and unpacked
ARCHIVE_MAX = 300 * 1024 * 1024                      # an annotated PDF (texstage)
DOWNLOAD_MS = 600_000                                 # a recording's download address stays valid
MEDIA_MS = 12 * 3_600_000                             # a video's address (a ticket): a lecture day
BUNDLE_ENTRY = re.compile(r"^(deck\.json|keys\.json|(slides|phone)/[0-9a-f]{16}\.png|media/[0-9a-f]{16}\.(mp4|m4v|webm|mov|jpg|png)"
                          r"|plugin-data/[0-9a-f]{64}\.(json|txt|csv|sql|ttl|png|jpg)"
                          r"|stage/[0-9a-f]{16}\.pdf" + "".join(f"|{p}" for p in stage_types.FILES) + r")$")
ZIP_JUNK = re.compile(r"(^|/)(__MACOSX/|\.DS_Store$|Thumbs\.db$|desktop\.ini$)", re.IGNORECASE)   # zipped by hand
ZIP_ERRORS = (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError, zlib.error)  # broken, Deflate64, encrypted
DECK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
HOSTS = ("host", "stage", "display")    # the lecturer's connections (presenter key): the host view
PEN = ("ink.begin", "ink.points", "ink.end", "ink.erase", "pointer")   # what the projector window may send besides
KEEP_BUILDS = 10            # builds kept per lecturer and deck (and per served deck)
WRONG_PAIRINGS = (20, 600)  # pairing codes that do not exist, per client address and window (s)
WRONG_PINS = (300, 600)     # wrong PINs per client address and window (s): a whole lecture hall
                            # behind one NAT address mistypes far less, a PIN guesser is slowed


mimetypes.add_type("text/javascript", ".mjs")      # PDF.js's modules (web/vendor); a Windows registry
                                                    # may say text/plain, and browsers refuse that
mimetypes.add_type("application/wasm", ".wasm")    # Oxigraph's engine (web/vendor/oxigraph): compiled as it comes
EVALUATOR = "evaluator-worker.js"                   # a live activity's queries run there: no network (web/stage)


class Static(StaticFiles):
    """The pages' files, revalidated on every load (a server update must not leave old
    scripts in the phones' caches)."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        if str(args[0] if args else kwargs.get("full_path", "")).endswith(EVALUATOR):
            response.headers["Content-Security-Policy"] = "connect-src 'none'"    # a student's query reaches nothing
        if str(args[0] if args else kwargs.get("full_path", "")).endswith("plugin-evaluator-worker.js"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'none'; worker-src 'none'"
        return response


def now_ms() -> int:
    return int(time.time() * 1000)


def rename(src: Path, dest: Path, tries: int = 6):
    """src.rename(dest) - tried again for a moment if Windows refuses it: a virus scanner or the
    search indexer may still hold a file that was just written (WinError 5 or 32)."""
    for attempt in range(tries):
        try:
            src.rename(dest)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05 * 2 ** attempt)           # 0.05 s to 0.8 s: 1.55 s in all


def make_icon(size: int) -> bytes:
    """The add-in's icon: the four answer shapes on the texstage purple."""
    from PIL import Image, ImageDraw
    scale = 4                                            # draw large, then shrink: smooth edges
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 5, fill="#46178f")
    q = s / 2
    pad = s * 0.12
    w = q - 1.5 * pad
    for i, (shape, fill) in enumerate((("tri", "#e21b3c"), ("dia", "#1368ce"), ("cir", "#d89e00"), ("sq", "#26890c"))):
        x0 = pad + (i % 2) * (w + pad)
        y0 = pad + (i // 2) * (w + pad)
        box = (x0, y0, x0 + w, y0 + w)
        if shape == "tri":
            d.polygon([(x0 + w / 2, y0), (x0 + w, y0 + w), (x0, y0 + w)], fill=fill)
        elif shape == "dia":
            d.polygon([(x0 + w / 2, y0), (x0 + w, y0 + w / 2), (x0 + w / 2, y0 + w), (x0, y0 + w / 2)], fill=fill)
        elif shape == "cir":
            d.ellipse(box, fill=fill)
        else:
            d.rectangle(box, fill=fill)
    buf = io.BytesIO()
    im.resize((size, size), Image.LANCZOS).save(buf, "PNG")
    return buf.getvalue()


def lan_address() -> str:
    """This machine's address in the local network (what phones in the room can reach)."""
    import socket
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("192.0.2.1", 9))          # no packet is sent: this only picks the route
        return s.getsockname()[0]
    return "127.0.0.1"


def listen(host: str, port: int) -> list:
    """The server's listening sockets. Windows tries "localhost" over IPv6 first, and a
    server only on IPv4 makes every new connection to http://localhost wait about a second
    before the fallback - PowerPoint's add-in pages load from there (M6). So all interfaces
    means IPv4 and IPv6 (one dual-stack socket), and the loopback means 127.0.0.1 and ::1."""
    import socket
    if host in ("0.0.0.0", "::", ""):
        if socket.has_dualstack_ipv6():
            with contextlib.suppress(OSError):                  # e.g. a container without IPv6
                return [socket.create_server(("::", port), family=socket.AF_INET6, dualstack_ipv6=True)]
        return [socket.create_server(("0.0.0.0", port))]
    if host in ("127.0.0.1", "localhost", "::1"):
        sockets = [socket.create_server(("127.0.0.1", port))]
        with contextlib.suppress(OSError):
            sockets.append(socket.create_server(("::1", port), family=socket.AF_INET6))
        return sockets
    return [socket.create_server((host, port), family=socket.AF_INET6 if ":" in host else socket.AF_INET)]


def lan_addresses() -> list[str]:
    """All IPv4 addresses of this machine, the one of the default route first: with a VPN,
    a hotspot or virtual adapters the phones may be on another network than the default."""
    import socket
    found = [lan_address()]
    with contextlib.suppress(OSError):
        for *_, addr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = addr[0]
            if ip not in found and not ip.startswith(("127.", "169.254.")):
                found.append(ip)
    return [ip for ip in found if not ip.startswith("127.")] or ["127.0.0.1"]


class Attempts:
    """Wrong PINs per client address in a sliding window: guessing PINs gets slow."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s * 1000
        self.wrong: dict[str, deque] = defaultdict(deque)

    def _recent(self, addr: str, now: int) -> deque:
        q = self.wrong[addr]
        while q and q[0] <= now - self.window:
            q.popleft()
        if not q:
            del self.wrong[addr]
        return q

    def blocked(self, addr: str, now: int) -> bool:
        return len(self._recent(addr, now)) >= self.limit

    def failed(self, addr: str, now: int):
        self.wrong[addr].append(now)
        if len(self.wrong) > 10000:                      # forget addresses that stopped
            for a in list(self.wrong):
                self._recent(a, now)


@dataclass
class ServerConfig:
    bundles: list[Path]
    data_dir: Path
    public_url: str
    presenter_key: str                   # the server's own lecturer's key (<data>/presenter-key)
    settings: Settings = field(default_factory=Settings)
    owner: str = "local"                 # that lecturer's name; more in <data>/lecturers.json


class Conn:
    """One WebSocket. Replies are queued in order; state pushes replace each other, so a
    slow phone only ever gets the newest state."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.addr = ws.client.host if ws.client else ""    # behind a proxy: the forwarded address
        self.role: str | None = None
        self.session: str | None = None
        self.player: str | None = None
        self.deck: str | None = None
        self.lecturer: str | None = None                   # hosts: whose key they brought
        self.device: str | None = None                     # a paired presenter device's id (devices.py)
        self.qa = False                                    # a phone that shows the audience's questions
        self.key = secrets.token_hex(6)                    # names this connection to the engine (a type's lease)
        self.outbox: deque = deque()
        self.state: dict | None = None
        self.ready = asyncio.Event()
        self.closing = False

    def send(self, msg: dict):
        self.outbox.append(msg)
        self.ready.set()

    def push(self, state: dict):
        self.state = state
        self.ready.set()

    def bye(self, reason: str, message: str):
        self.send({"t": "bye", "reason": reason, "message": message})
        self.closing = True

    async def writer(self):
        try:
            while True:
                await self.ready.wait()
                self.ready.clear()
                while self.outbox:
                    await self.ws.send_json(self.outbox.popleft())
                if self.state is not None:
                    state, self.state = self.state, None
                    await self.ws.send_json(state)
                if self.closing:
                    await self.ws.close()
                    return
        except (WebSocketDisconnect, RuntimeError, OSError):
            return                                   # the client has gone; the reader notices


def bundle_files(z: zipfile.ZipFile) -> list[tuple[str, zipfile.ZipInfo]]:
    """A zip's files by their names in the bundle. The build's .bundle.zip and texstage publish
    have them at the top; a .bundle folder zipped by hand has them in that folder - some tools
    write backslashes, Finder adds __MACOSX/ - and those are taken the same way."""
    files = [(i.filename.replace("\\", "/"), i) for i in z.infolist()]
    files = [(n, i) for n, i in files if not n.endswith("/") and not ZIP_JUNK.search(n)]
    while files and all("/" in n for n, _ in files) and len({n.split("/", 1)[0] for n, _ in files}) == 1:
        files = [(n.split("/", 1)[1], i) for n, i in files]              # one folder around it all
    return files


def zip_bundle_id(packed: Path) -> str:
    """The bundle ID an uploaded zip's deck.json names (an upload by hand, POST /api/bundles)."""
    try:
        with zipfile.ZipFile(packed) as z:
            info = dict(bundle_files(z)).get("deck.json")
            if info is None:
                raise BundleError("not a deck: no deck.json in it - upload the .bundle.zip from the build folder")
            if info.file_size > 20 * 1024 * 1024:
                raise BundleError("deck.json is too large")
            deck = json.loads(z.read(info))
    except (*ZIP_ERRORS, ValueError) as err:
        raise BundleError(f"not a deck's .bundle.zip: {err}") from None
    bid = deck.get("bundle") if isinstance(deck, dict) else None
    if not isinstance(bid, str) or not re.fullmatch(r"[0-9a-f]{16}", bid):
        raise BundleError("its deck.json names no bundle ID")
    return bid


def _str(msg: dict, key: str) -> str | None:
    """A string field of a client message (anything else counts as missing)."""
    v = msg.get(key)
    return v if isinstance(v, str) else None


def _int(msg: dict, key: str, default=None) -> int | None:
    v = msg.get(key, default)
    return v if isinstance(v, int) and not isinstance(v, bool) else None


class Server:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.plugin_catalog = catalog_for(config.data_dir)
        self.published = config.data_dir / "bundles"         # texstage publish puts bundles here
        self.published.mkdir(parents=True, exist_ok=True)
        self.incoming = config.data_dir / "incoming"         # uploads being unpacked (not scanned)
        self.served = config.data_dir / "served"             # copies of served decks being played
        self.served.mkdir(parents=True, exist_ok=True)
        roots = [Path(r) for r in config.bundles]
        for own in (self.published, self.served):
            if not any(r.resolve() == own.resolve() for r in roots):
                roots.append(own)
        self.bundles = BundleStore(roots, published=self.published,     # <lecturer>/<deck>.bundle
                                   more=lambda: build_folders(config.data_dir), catalog=self.plugin_catalog)
        self.lecturers = Lecturers(config.data_dir / "lecturers.json", {config.owner: config.presenter_key})
        self.devices = Devices(config.data_dir / "devices.json")
        self.library = Library(config.data_dir / "library.json")     # the deck page: folders, names
        self.attempts = Attempts(*WRONG_PINS)
        self.pair_attempts = Attempts(*WRONG_PAIRINGS)
        self.publishing = asyncio.Lock()
        self.store = Store(config.data_dir / "texquiz.sqlite3")   # its name since 0.1: the games, archives
        self.engine = Engine(self.bundles, self.store, config.settings)
        self.recordings = Recordings(config.data_dir / "archive")      # texstage (archive.py)
        self.downloads: dict[str, tuple[Path, str, int]] = {}         # ticket -> file, its name, valid until
        self.media: dict[str, tuple[str, str, int]] = {}              # ticket -> bundle ID, relative video file, valid until
        self.conns: dict[str, set[Conn]] = defaultdict(set)    # session id -> connections
        self.dirty: set[str] = set()                           # sessions whose hosts need a push
        self.plugin_dirty: set[str] = set()                    # coalesced full plugin projections
        self.plugin_recipients: dict[str, set[str] | None] = {}
        self.plugin_push_after: dict[str, float] = {}          # monotonic next broadcast time
        self.qa_dirty: set[str] = set()                        # ... whose questions changed (M6)
        self.qa_pushed = 0.0
        self.replies: dict[tuple, OrderedDict] = defaultdict(OrderedDict)
        self.join_replies: OrderedDict[str, tuple[int, str, str, str]] = OrderedDict()
        self.wake = asyncio.Event()
        self.tasks: list[asyncio.Task] = []
        self.instance = secrets.token_hex(8)       # in /api/status: does an address lead to this server?
        self.plugins = PluginHost(self, self.plugin_catalog)

    # ------------------------------------------------------------ pushing
    def _attach(self, conn: Conn, sid: str):
        if conn.session:
            self.conns[conn.session].discard(conn)
        conn.session = sid
        self.conns[sid].add(conn)

    def push(self, sid: str, hosts: bool = True, players: bool = True, only: str | set | None = None,
             asking: bool = False, *, connections=None, complete: bool = True):
        """The views of the game's connections: hosts, players (`only` one, or a set; `asking`:
        those that show the audience's questions)."""
        now = now_ms()
        if sid not in self.engine.sessions:
            self.plugin_dirty.discard(sid)
            self.plugin_recipients.pop(sid, None)
            self._sweep()
            return
        if complete and players and only is None and not asking:
            self.engine.due.pop(sid, None)            # every phone gets its state now
        host_view = None
        connections = (list(self.conns.get(sid, ())) if connections is None else
                       [c for c in connections if c in self.conns.get(sid, ()) and c.session == sid])
        recipients = [c for c in connections if (c.role in HOSTS and hosts) or
                      (c.role == "player" and players
                       and (only is None or (c.player in only if isinstance(only, set) else c.player == only))
                       and (not asking or c.qa))]
        plugin_views = self.plugins.safe_views(recipients)
        for c in connections:
            try:
                if c.role in HOSTS and hosts:
                    if host_view is None:
                        host_view = self.engine.host_view(sid, now)
                        host_view["session"]["join"] = f"{self.config.public_url}/play?pin={host_view['session']['pin']}"
                        host_view["session"]["qr"] = f"/join/{host_view['session']['pin']}.svg"
                    c.push({"t": "state", "now": now, "role": c.role, **host_view, **plugin_views[c]})
                elif (c.role == "player" and players
                      and (only is None or (c.player in only if isinstance(only, set) else c.player == only))
                      and (not asking or c.qa)):
                    view = self.engine.player_view(c.player, now, questions=c.qa)
                    c.push({"t": "state", "now": now, "role": "player", **view, **plugin_views[c]})
            except PluginError as err:
                c.push({"t": "plugin.error", "message": str(err)})
            except GameError as err:
                c.bye(err.code, str(err))
                self.conns[sid].discard(c)
        if complete and hosts:
            self.dirty.discard(sid)
        if complete and hosts and players and only is None and not asking:
            self.plugin_dirty.discard(sid)
            self.plugin_recipients.pop(sid, None)

    def _sweep(self):
        """Connections of sessions that ended: hosts move to the deck's new session, if there
        is one; players are told to join again."""
        live = set(self.engine.sessions) | set(self.engine.players)
        for sid in self.plugin_push_after.keys() - self.engine.sessions.keys():
            self.plugin_push_after.pop(sid, None)
            self.plugin_dirty.discard(sid)
            self.plugin_recipients.pop(sid, None)
        for key in [k for k in self.replies if k[1] not in live]:   # retry caches of ended games
            del self.replies[key]
        for sid in [sid for sid in self.conns if sid not in self.engine.sessions]:
            conns = self.conns.pop(sid)
            for c in conns:
                if c.role in HOSTS:
                    deck = c.deck
                    new = next((s for s in self.engine.sessions.values()
                                if s.deck == deck and s.owner == c.lecturer), None)
                    if new is not None:
                        self._attach(c, new.id)
                        self.push(new.id, players=False)
                        continue
                c.bye("no-session", "this game is over - join the new one")

    # ------------------------------------------------------------ background
    async def ticker(self):
        """Phase changes at their deadlines (get-ready -> open -> closed)."""
        while True:
            due = self.engine.next_deadline()
            timeout = None if due is None else max(0.0, (due - now_ms()) / 1000) + 0.002
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), timeout)
            self.wake.clear()
            try:
                for sid in self.engine.tick(now_ms()):
                    self.push(sid)
            except Exception:                        # a bug must not stop the clock
                log.exception("tick failed")
                await asyncio.sleep(1)

    async def flusher(self):
        while True:
            await asyncio.sleep(HOST_PUSH_S)
            try:
                await self.flush_plugins()
                for sid in list(self.dirty):
                    self.push(sid, players=False)
                if self.qa_dirty and time.monotonic() - self.qa_pushed >= QA_PUSH_S:
                    self.qa_pushed = time.monotonic()
                    for sid in list(self.qa_dirty):
                        self.qa_dirty.discard(sid)
                        self.push(sid, hosts=False, asking=True)
            except Exception:
                log.exception("host push failed")

    def questions_changed(self, sid: str):
        """The audience's questions changed: the hosts and the phones that show them learn it soon."""
        self.dirty.add(sid)
        self.qa_dirty.add(sid)

    def plugins_changed(self, sid: str, only: set[str] | None = None):
        # Commands and durable receipts are immediate. Render the latest full,
        # role-filtered snapshots at a rate bounded by measured broadcast cost.
        # A burst must not render N audience views again for each of N answers.
        self.plugin_dirty.add(sid)
        if only is None:
            self.plugin_recipients[sid] = None
        elif self.plugin_recipients.get(sid, set()) is not None:
            self.plugin_recipients.setdefault(sid, set()).update(only)

    async def flush_plugins(self):
        # Reserve time for socket replies, worker module requests and job
        # delivery when a full class projection is expensive. Aim for at most
        # 25% of the loop in these broadcasts, with at most one second added
        # coalescing delay. Cheap projections retain the ordinary 200 ms rate.
        # Presenter controls and core navigation still call push immediately.
        for sid in list(self.plugin_dirty):
            start = time.monotonic()
            if start < self.plugin_push_after.get(sid, 0):
                continue
            # Consume this generation before yielding. Any later mutation leaves
            # a new dirty marker. Views/membership are refreshed per bounded batch.
            self.plugin_dirty.discard(sid)
            self.dirty.discard(sid)
            recipients = self.plugin_recipients.pop(sid, None)
            peers = [c for c in self.conns.get(sid, ()) if
                     recipients is None or c.role in HOSTS or c.player in recipients]
            if not peers:
                self.push(sid)
            for offset in range(0, len(peers), 16):
                self.push(sid, only=recipients, connections=peers[offset:offset + 16], complete=False)
                await asyncio.sleep(0)
            end = time.monotonic()
            if sid in self.engine.sessions:
                self.plugin_push_after[sid] = end + min(1.0, max(HOST_PUSH_S, 3 * (end - start)))

    def push_due(self):
        """The phones a content type's change concerns get their state (game.py: take_due)."""
        for sid, who in self.engine.take_due().items():
            self.push(sid, hosts=False, only=None if who is True else who)

    async def start(self):
        self.tasks = [asyncio.create_task(self.ticker()), asyncio.create_task(self.flusher())]

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        self.store.close()
        self.plugins.close()

    # ------------------------------------------------------------ publishing
    def unpack_bundle(self, packed: Path, bid: str, lecturer: str) -> Path:
        """An uploaded bundle (zip): checked, then unpacked to bundles/<lecturer>/<deck>/<id>/
        in the data folder - every build of a deck apart, so a PPTX always finds its own
        version (the newest KEEP_BUILDS stay, prune). deck.json keeps the build's time.
        Runs in a worker thread; only names of bundle files are accepted (no path tricks)."""
        work = self.incoming / f"new-{secrets.token_hex(6)}"
        try:
            try:
                with zipfile.ZipFile(packed) as z:
                    entries = bundle_files(z)
                    if sum(i.file_size for _, i in entries) > BUNDLE_MAX:
                        raise BundleError("the bundle is too large")
                    for name, i in entries:
                        if not BUNDLE_ENTRY.match(name):
                            raise BundleError(f"not a bundle file: {name}")
                        dest = work / name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(z.read(i))      # at most file_size bytes: no zip bombs
                        if name == "deck.json":          # "built": when it was made, not uploaded
                            with contextlib.suppress(OverflowError, ValueError, OSError):
                                t = time.mktime(i.date_time + (0, 0, -1))
                                os.utime(dest, (t, t))
            except ZIP_ERRORS as err:
                raise BundleError(f"not a zip file: {err}") from None
            try:
                b = load_bundle(work, catalog=self.plugin_catalog)
            except BundleError as err:                   # without the server's own folder in it
                raise BundleError(str(err).removeprefix(f"{work}: ")) from None
            if b.id != bid:
                raise BundleError(f"the upload is bundle {b.id}, not {bid}")
            if not DECK_ID.match(b.deck):
                raise BundleError(f"deck {b.deck!r}: a deck ID has lowercase letters, digits and dashes")
            target = self.published / lecturer / b.deck / b.id          # names: lecturers.NAME, DECK_ID
            target.parent.mkdir(parents=True, exist_ok=True)
            old = self.incoming / f"old-{secrets.token_hex(6)}"
            if target.exists():
                rename(target, old)
            try:
                rename(work, target)
            except OSError:
                if old.exists():
                    rename(old, target)                  # keep the previous build
                raise
            shutil.rmtree(old, ignore_errors=True)
            return target
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def prune(self, folder: Path):
        """Keeps the newest KEEP_BUILDS builds in a deck's folder (<id>/ each) and every
        build a game plays."""
        playing = {s.bundle for s in self.engine.sessions.values()}
        builds = sorted((d for d in folder.iterdir() if (d / "deck.json").is_file()),
                        key=lambda d: (d / "deck.json").stat().st_mtime, reverse=True)
        for d in builds[KEEP_BUILDS:]:
            if d.name not in playing:
                self.bundles.drop(d)
                shutil.rmtree(d, ignore_errors=True)

    def snapshot(self, b):
        """A deck from a served folder (a laptop's build folder) that a game plays is copied
        to served/<deck>/<id>/ in the data folder: a rebuild replaces the build folder, and
        the game - or an older PPTX - goes on with its own version's pictures."""
        if b.owners is not None or not DECK_ID.match(b.deck) or not holds(b):
            return
        dest = self.served / b.deck / b.id
        if b.path.resolve() == dest.resolve():
            return
        if not dest.is_dir():
            tmp = self.incoming / f"copy-{secrets.token_hex(6)}"
            shutil.copytree(b.path, tmp)
            dest.parent.mkdir(parents=True, exist_ok=True)
            rename(tmp, dest, tries=3)                # on the event loop: 0.15 s at most
        b.path = dest
        self.prune(dest.parent)

    # ------------------------------------------------------------ the protocol
    async def handle(self, conn: Conn, msg: dict):
        t, mid = msg.get("t"), msg.get("id")
        now = now_ms()
        try:
            if t == "ping":
                conn.send({"t": "pong", "re": mid, "now": now})
            elif t == "hello":
                self._hello(conn, msg, mid, now)
            elif t == "join":
                if self.attempts.blocked(conn.addr, now):
                    raise GameError("too-many-attempts", "too many wrong PINs from this network - try again in a few minutes")
                try:
                    p, token = self._join(msg, now)
                except GameError as err:
                    if err.code == "unknown-pin":
                        self.attempts.failed(conn.addr, now)
                    raise
                self._enter(conn, p, mid, token)
            elif t == "resume":
                self._enter(conn, self.engine.player_by_token(_str(msg, "token")), mid, None)
            elif conn.role is None:
                raise GameError("hello-first", "say hello, join or resume first")
            elif isinstance(t, str) and t.startswith("plugin."):
                reply = self.plugins.handle(conn, msg)
                conn.send({"t": "ok", "re": mid, **reply})
            else:
                key = (conn.role, conn.player or conn.session)
                cache = self.replies[key]
                if mid is not None and mid in cache:
                    conn.send(cache[mid])
                    return
                if conn.role == "player":
                    reply = self._player(conn, t, msg, now)
                elif conn.role == "stage":
                    reply = self._stage(conn, t, msg, now)
                elif conn.role == "host":
                    reply = self._host(conn, t, msg, now)
                elif t == "ink.load":                    # display: texstage's projector window
                    reply = self.engine.ink_load(conn.session, msg.get("frame"))
                elif t == "sketch.get":                  # ... and the sketches it shows
                    reply = self.engine.sketch_get(conn.session, msg.get("quiz"), msg.get("players"))
                elif t in stage_types.READS:             # ... what a content type shows (types.py)
                    reply = self.engine.type_message(conn.session, t, msg, now, role=conn.role, conn=conn.key)
                elif t in PEN:                           # ... and a pen on its screen (pen.js)
                    reply = self._stage(conn, t, msg, now)
                else:
                    raise GameError("read-only", "the projector window only shows the slides")
                if mid is None and t == "pointer":      # sent without an id: no answer wanted
                    return
                reply = {"t": "ok", "re": mid, **(reply or {})}
                if mid is not None and t not in READS and t not in stage_types.READS and t != "pointer":
                    cache[mid] = reply                   # (the laser's answer: the next may go)
                    while len(cache) > REPLY_CACHE:
                        cache.popitem(last=False)
                conn.send(reply)
        except PluginError as err:
                        conn.send({"t": "error", "re": mid, "error": err.code, "message": str(err)})
        except GameError as err:
            conn.send({"t": "error", "re": mid, "error": err.code, "message": str(err)})
        except Exception as err:                         # a bug: report it, keep the connection
            log.exception("command %r failed", t)
            conn.send({"t": "error", "re": mid, "error": "internal", "message": type(err).__name__})
        finally:
            self.wake.set()
            try:
                self.push_due()
            except Exception:                            # a bug must not break the connection
                log.exception("phones' push failed")

    def _join(self, msg: dict, now: int):
        """Recover a lost welcome with the phone's random secret, never its nickname or id.

        Legacy clients can omit the nonce. Replay entries live only in memory, for ten
        minutes, and are bounded; normal reconnections use the persisted player token.
        """
        pin, nickname, nonce = _str(msg, "pin"), clean_nickname(msg.get("nickname")), msg.get("join_nonce")
        if nonce is not None and (not isinstance(nonce, str) or not JOIN_NONCE.fullmatch(nonce)):
            raise GameError("invalid", "join_nonce must be 32 random hexadecimal characters")
        while self.join_replies and next(iter(self.join_replies.values()))[0] <= now:
            self.join_replies.popitem(last=False)
        key = token_hash(nonce) if nonce is not None else None
        prior = self.join_replies.get(key) if key is not None else None
        if prior is not None:
            _, original_pin, original_name, token = prior
            if (pin, nickname) != (original_pin, original_name):
                raise GameError("invalid", "a join retry must keep its original PIN and nickname")
            return self.engine.player_by_token(token), token       # a kicked/ended player stays out
        player, token = self.engine.join(pin, nickname, now)
        if key is not None:
            self.join_replies[key] = (now + JOIN_REPLAY_MS, pin, nickname, token)
            while len(self.join_replies) > JOIN_REPLAY_MAX:
                self.join_replies.popitem(last=False)
        return player, token

    def _hello(self, conn: Conn, msg: dict, mid, now: int):
        role = msg.get("role")
        if role not in HOSTS:
            raise GameError("invalid", "hello is for hosts; players join or resume")
        lecturer, device = self.lecturers.who(msg.get("key")), None
        if lecturer is None and msg.get("device") is not None:       # a paired presenter device (texstage)
            lecturer, device = self.devices.who(msg.get("device"), now) or (None, None)
        if lecturer is None:
            raise GameError("bad-key", "wrong presenter key")
        conn.device = device
        deck, bid = _str(msg, "deck"), _str(msg, "bundle")
        b = self.bundles.get(bid) if bid else None
        if b is None or not b.open_to(lecturer):          # another lecturer's deck: not here for this one
            raise GameError("unknown-bundle", f"deck {deck}, bundle {bid} is not on this server")
        s = self.engine.open_session(deck, bid, now, owner=lecturer)
        try:
            self.snapshot(b)
        except OSError as err:                            # the game goes on from the build folder
            log.warning("could not keep a copy of %s: %s", b.path, err)
        conn.role, conn.deck, conn.lecturer = role, s.deck, lecturer
        self._attach(conn, s.id)
        welcome = {"t": "welcome", "re": mid, "role": role, "session": s.id, "pin": s.pin}
        if role == "stage":                               # a new presentation, or the lecture continued?
            welcome["earlier"] = self.engine.earlier(s.id)
            welcome["presenters"] = sum(1 for c in self.conns[s.id] if c is not conn and c.role == "stage")
        conn.send(welcome)
        self._sweep()
        self.push(s.id, players=False)

    def _enter(self, conn: Conn, p, mid, token):
        if conn.player and conn.player != p.id:
            self.engine.connect(conn.player, -1)
        if conn.player != p.id:
            self.engine.connect(p.id, +1)
        conn.role, conn.player = "player", p.id
        self._attach(conn, p.session)
        welcome = {"t": "welcome", "re": mid, "role": "player", "player": p.id, "nickname": p.nickname}
        if token:
            welcome["token"] = token
        conn.send(welcome)
        self.push(p.session, hosts=False, only=p.id)
        self.dirty.add(p.session)

    def _host(self, conn: Conn, t, msg: dict, now: int) -> dict | None:
        e, sid, quiz, player = self.engine, conn.session, _str(msg, "quiz"), _str(msg, "player")
        if t == "slide":
            slide = _int(msg, "slide")
            if slide is None:
                raise GameError("invalid", "slide is the PowerPoint slide ID (a number)")
            new = e.show_slide(sid, slide, now)
            if new.id != sid:                        # a new game after the podium
                self._sweep()
                return {"session": new.id, "pin": new.pin}
        elif t == "prepare":                         # the add-in prepares the live slides
            e.prepare(sid, bool(msg.get("on")), now)
        elif t == "skip":
            e.skip(sid, quiz, now)
        elif t == "extend":
            e.extend(sid, quiz, _int(msg, "seconds", 10), now)
        elif t == "pause":
            e.pause(sid, quiz, now)
        elif t == "continue":
            e.resume(sid, quiz, now)
        elif t == "again":
            e.again(sid, quiz, now)
        elif t == "reveal":
            e.reveal(sid, quiz, now)
        elif t == "finish":
            e.finish(sid, now)
        elif t == "kick":
            e.kick(sid, player, now)
            for c in list(self.conns.get(sid, ())):
                if c.player == player:
                    c.bye("kicked", "you have been removed from the game")
                    self.conns[sid].discard(c)
        elif t == "rename":
            e.rename(sid, player, msg.get("nickname"), now)
        elif t == "restart":
            new = e.restart(sid, now)
            self._sweep()
            return {"session": new.id, "pin": new.pin}
        else:
            raise GameError("unknown-command", f"unknown command {t!r}")
        self.push(sid)
        return None

    def _stage(self, conn: Conn, t, msg: dict, now: int) -> dict | None:
        """texstage's presenter window: ink, pointer, zoom, whiteboard pages, the projector's
        screen and the timer, and everything a host does (it drives the game with `slide` as
        the add-in does)."""
        e, sid, reply = self.engine, conn.session, None
        if t.startswith("ink."):
            return self._ink(conn, t, msg, now)
        if t == "pointer":                                # not stored: straight to the others
            x, y = msg.get("x"), msg.get("y")
            on = all(isinstance(v, (int, float)) and not isinstance(v, bool) and -1 <= v <= 2 for v in (x, y))
            self.relay(conn, {"t": "pointer", **({"x": round(x, 4), "y": round(y, 4)} if on else {"off": True})})
            return None
        if t == "screen":
            e.screen(sid, msg.get("screen"), now)
        elif t == "timer":
            e.timer(sid, msg.get("action"), _int(msg, "seconds"), now)
        elif t == "zoom":
            e.zoom(sid, msg.get("rect"), now)
        elif t == "board":
            reply = {"board": e.board_add(sid, msg.get("after"), msg.get("kind"), now)}
        elif t == "go":
            e.go_board(sid, msg.get("board"), now)
        elif t == "poll.create":                          # M6: asked at once - the phones too
            quiz = e.poll_create(sid, {k: msg[k] for k in ("kind", "prompt", "answers", "select", "time") if k in msg},
                                 now)
            self.push(sid)
            return {"quiz": quiz}
        elif t == "poll.show":
            e.poll_show(sid, msg.get("quiz"), now)
        elif t == "sketch.list":
            return e.sketch_list(sid, msg.get("quiz"), msg.get("after", 0), msg.get("round"))
        elif t == "sketch.get":
            return e.sketch_get(sid, msg.get("quiz"), msg.get("players"))
        elif t == "sketch.show":
            e.sketch_show(sid, msg.get("quiz"), msg.get("players"), now)
        elif t in ("qa.open", "qa.block"):                # every phone: may it ask?
            if t == "qa.open":
                e.qa_open(sid, msg.get("on"), now)
            else:
                e.qa_block(sid, msg.get("question"), now)
            self.push(sid)
            return None
        elif t == "qa.show":
            e.qa_show(sid, msg.get("question"), now)
        elif t == "qa.mark":
            e.qa_mark(sid, msg.get("question"), msg.get("state"), now)
            self.qa_dirty.add(sid)
        elif t == "lecture.new":                          # a new presentation: no ink, no whiteboard pages
            new = e.fresh(sid, now)
            self._sweep()                                 # the windows move to the new game
            self.relay(conn, {"t": "ink", "op": "reload"})
            return {"session": new.id, "pin": new.pin}
        elif t == "lecture.continue":                     # the lecture before goes on: its ink and pages
            reply = e.take_over(sid, msg.get("game"), now)
            self.relay(conn, {"t": "ink", "op": "reload"})
        elif t in stage_types.MESSAGES:                   # a content type's (a video: play, pause, seek)
            reply = e.type_message(sid, t, msg, now, role=conn.role, conn=conn.key)
            if t in stage_types.READS:                    # (a read changes nothing to push)
                return reply
            if t in stage_types.QUIET:                    # (in bulk: the windows within 200 ms)
                self.dirty.add(sid)
                return reply
        else:
            return self._host(conn, t, msg, now)
        self.push(sid, players=False)
        return reply

    def _ink(self, conn: Conn, t, msg: dict, now: int) -> dict | None:
        """Ink (game.py, ink.py): what happens goes to the other texstage windows of the game;
        undo, redo and clear tell the sender too (`event` in the answer)."""
        e, sid, device, frame = self.engine, conn.session, msg.get("device"), msg.get("frame")
        if t == "ink.load":
            return e.ink_load(sid, frame)
        if t == "ink.all":                             # the annotated PDF
            return e.ink_all(sid)
        if t == "ink.begin":
            event = e.ink_begin(sid, device, frame, msg.get("stroke"), msg.get("points"), now)
        elif t == "ink.points":
            event = e.ink_points(sid, msg.get("stroke"), msg.get("points"))
        elif t == "ink.end":
            event = e.ink_end(sid, msg.get("stroke"), now)
        elif t == "ink.erase":
            event = e.ink_erase(sid, device, frame, msg.get("strokes"), now)
        elif t in ("ink.clear", "ink.undo", "ink.redo"):
            act = {"ink.clear": e.ink_clear, "ink.undo": e.ink_undo, "ink.redo": e.ink_redo}[t]
            event = act(sid, device, frame, now)
            if event:
                self.relay(conn, {"t": "ink", **event})
            return {"event": event}
        else:
            raise GameError("unknown-command", f"unknown command {t!r}")
        if event:
            self.relay(conn, {"t": "ink", **event})
        return None

    def relay(self, sender: Conn, msg: dict):
        """To the game's other texstage windows (presenter and projector), as it happens."""
        for c in list(self.conns.get(sender.session, ())):
            if c is not sender and c.role in ("stage", "display"):
                c.send(msg)

    def _player(self, conn: Conn, t, msg: dict, now: int) -> dict | None:
        if t in stage_types.PLAYER_MESSAGES:              # a content type's (types.py)
            reply = self.engine.type_player_message(conn.player, t, msg, now)
            self.push(conn.session, hosts=False, only=conn.player)      # this phone: at once
            self.dirty.add(conn.session)                               # the hosts: soon
            return reply
        if t in ("qa.ask", "qa.vote", "qa.watch"):        # the audience's questions (M6)
            reply = None
            if t == "qa.ask":
                reply = {"question": self.engine.qa_ask(conn.player, msg.get("text"), now).id}
                self.questions_changed(conn.session)
            elif t == "qa.vote":
                if self.engine.qa_vote(conn.player, msg.get("question"), msg.get("on"), now):
                    self.questions_changed(conn.session)
            else:
                conn.qa = bool(msg.get("on"))
            self.push(conn.session, hosts=False, only=conn.player)      # this phone: at once
            return reply
        if t != "answer":
            raise GameError("unknown-command", f"unknown command {t!r}")
        rid = _str(msg, "round")
        s = self.engine.sessions.get(conn.session)
        r = s.rounds.get(rid) if s and rid else None
        before = r.phase if r else None
        a = self.engine.answer(conn.player, rid, msg.get("answer"), now)
        if r is not None and r.phase != before:          # the last answer closed the round
            self.push(conn.session)
        else:
            self.push(conn.session, hosts=False, only=conn.player)
            self.dirty.add(conn.session)
        return {"answer": a.payload}

    def disconnect(self, conn: Conn):
        self.plugins.disconnect(conn)
        if conn.role in HOSTS:
            self.engine.left(conn.key)                   # what it held (a content type's lease) is free
        if conn.session:
            self.conns[conn.session].discard(conn)
            if not self.conns[conn.session]:
                self.conns.pop(conn.session, None)
        if conn.player:
            self.engine.connect(conn.player, -1)
            if conn.session in self.engine.sessions:
                self.dirty.add(conn.session)

    def results_csv(self, s) -> tuple[str, str]:
        """A game's results as CSV - (file name, text): a row per player (game.py results_table)."""
        buf = io.StringIO()
        if self.plugins.runtime is not None and s.ended is None:
            self.plugins.sync(s.id)
        csv.writer(buf).writerows(self.engine.results_table(s.id))
        day = time.strftime("%Y-%m-%d", time.localtime(s.created / 1000))
        return f"{s.deck}-{day}-{s.pin}.csv", "﻿" + buf.getvalue()         # BOM: Excel reads UTF-8

    def write_archive(self, s) -> Path:
        """The game's folder in the lecture archive with what the game has now: the results,
        and (M6) its polls, the audience's questions and the sketches as SVG."""
        folder = archive.folder(self.config.data_dir, s)
        name, text = self.results_csv(s)
        (folder / name).write_text(text, encoding="utf-8")
        tables = {"polls.csv": self.engine.polls_table(s.id), "questions.csv": self.engine.questions_table(s.id)}
        for row in tables["questions.csv"][1:]:
            row[3] = time.strftime("%H:%M:%S", time.localtime(row[3] / 1000))
        for file, rows in tables.items():
            if len(rows) > 1:
                buf = io.StringIO()
                csv.writer(buf).writerows(rows)
                (folder / file).write_text("﻿" + buf.getvalue(), encoding="utf-8")
        for quiz, n, strokes in self.engine.sketch_answers(s.id):
            (folder / f"sketch-{quiz}-{n}.svg").write_text(archive.sketch_svg(strokes), encoding="utf-8")
        for file, text in self.engine.type_archive(s.id, now_ms()).items():     # the content types' (types.py)
            if archive.FILE.match(file):
                (folder / file).write_text(text, encoding="utf-8")
            else:
                log.warning("not an archive file: %r", file)
        if self.plugins.runtime is not None:
            target = folder / "plugins.json"
            temporary = folder / "plugins.json.tmp"
            temporary.write_text(json.dumps(self.plugins.runtime.archive(s.id), ensure_ascii=True), encoding="utf-8")
            temporary.replace(target)
        return folder

    def take_info(self, t) -> dict:
        """A recording (archive.py Take) as the presenter window sees it."""
        size = t.file.stat().st_size if t.finished and t.file.exists() else t.size
        return {"take": t.id, "file": t.file.name, "folder": t.folder.relative_to(self.config.data_dir).as_posix(),
                "size": size, "parts": t.parts, "started": t.started, "finished": t.finished,
                "remuxing": t.id in self.recordings.remuxing}

    def media_ticket(self, bundle: str, name: str, now: int) -> str:
        """The address of a video file for the lecturer's windows: a <video> cannot send the key,
        so the address is the key - random, for a lecture day (docs/content-types-design.md, section 7)."""
        for ticket in [k for k, (_, _, until) in self.media.items() if until < now]:
            del self.media[ticket]
        ticket = secrets.token_urlsafe(18)
        # The physical copy can change when another lecturer deletes their upload.
        # Keep the content identity so existing byte-range requests use the surviving copy.
        self.media[ticket] = (bundle, name, now + MEDIA_MS)
        return f"/media/{ticket}/{Path(name).name}"

    def download(self, path: Path, name: str, now: int) -> str:
        """An address that downloads the file for a while, without the key a link cannot send."""
        for ticket in [k for k, (_, _, until) in self.downloads.items() if until < now]:
            del self.downloads[ticket]
        ticket = secrets.token_urlsafe(18)
        self.downloads[ticket] = (path, name, now + DOWNLOAD_MS)
        return f"/download/{ticket}/{name}"

    def remove_device(self, owner: str, device: str) -> bool:
        """A paired presenter device removed (devices.py): its connections end now."""
        if not self.devices.remove(owner, device):
            return False
        for conns in self.conns.values():
            for c in list(conns):
                if c.device == device:
                    c.bye("removed", "this device was removed in the presenter window")
        return True


async def small_json(request: Request) -> dict:
    """The JSON object of a small request body ({} if there is none or it is not one)."""
    body = await request.body()
    try:
        data = json.loads(body) if 0 < len(body) <= 4096 else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def create_app(config: ServerConfig) -> Starlette:
    server = Server(config)

    async def status(request: Request):
        return JSONResponse({"server": "texstage", "version": __version__, "join": f"{config.public_url}/play",
                             "instance": server.instance, "bundles": len(server.bundles.bundles),
                             "games": len(server.engine.sessions)})

    async def presenter_key(request: Request):
        # Only to the machine itself, asked as localhost: not through a proxy (behind Caddy
        # every request comes from a local address) and not to a web page that had its own
        # name resolve to 127.0.0.1 (DNS rebinding).
        host = request.headers.get("host", "")
        name = (host[:host.rindex(":")] if ":" in host and not host.endswith("]") else host).strip("[]").lower()
        local = (request.client is not None and request.client.host in LOOPBACK and name in LOOPBACK
                 and not any(h in request.headers for h in FORWARDED))
        if not local:
            return JSONResponse({"error": "only on the machine the server runs on"}, status_code=403)
        return JSONResponse({"key": config.presenter_key})

    def bundle_info(b) -> dict:
        return {"bundle": b.id, "deck": b.deck, "name": b.name, "quizzes": len(b.quizzes), "slides": len(b.slides)}

    async def publish(request: Request):
        """PUT /api/bundles/<id>: a bundle from `texstage publish` or a PPTX's join slide (a zip
        of the bundle folder); it belongs to the lecturer whose key comes with it."""
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        bid = request.path_params["bundle"]
        if not re.fullmatch(r"[0-9a-f]{16}", bid):
            return JSONResponse({"error": "not a bundle ID"}, status_code=404)
        if have(bid, lect):
            server.library.show(lect, server.bundles.bundles[bid].deck)    # uploaded again: listed again
            return JSONResponse(bundle_info(server.bundles.bundles[bid]) | {"new": False})
        return await receive(request, lect, bid)

    async def upload(request: Request):
        """POST /api/bundles: a deck's .bundle.zip uploaded by hand (the deck list of texstage
        or of the host page); its ID is the one its deck.json names."""
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        return await receive(request, lect, None)

    def have(bid: str, lect: str) -> bool:
        """The lecturer's server has this bundle complete already (an incomplete one is replaced)."""
        known = server.bundles.bundles.get(bid)
        return known is not None and known.open_to(lect) and known in server.bundles.current() and known.complete()

    async def receive(request: Request, lect: str, bid: str | None):
        """An upload into incoming/ (at most BUNDLE_MAX), checked and unpacked; bid None: the
        ID its deck.json names (an upload by hand)."""
        server.incoming.mkdir(parents=True, exist_ok=True)
        packed = server.incoming / f"{secrets.token_hex(6)}.zip"
        try:
            size = 0
            with packed.open("wb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > BUNDLE_MAX:
                        return JSONResponse({"error": "the bundle is too large"}, status_code=413)
                    f.write(chunk)
            if bid is None:
                bid = await asyncio.to_thread(zip_bundle_id, packed)
                if have(bid, lect):
                    server.library.show(lect, server.bundles.bundles[bid].deck)
                    return JSONResponse(bundle_info(server.bundles.bundles[bid]) | {"new": False})
            async with server.publishing:
                target = await asyncio.to_thread(server.unpack_bundle, packed, bid, lect)
                b = server.bundles.add(target)
                server.prune(target.parent)
            server.library.show(lect, b.deck)            # a deck taken off the list, uploaded again
        except BundleError as err:
            return JSONResponse({"error": str(err)}, status_code=400)
        finally:
            packed.unlink(missing_ok=True)
        log.info("published by %s: %s %s (%s)", lect, b.deck, b.id, target)
        return JSONResponse(bundle_info(b) | {"new": True}, status_code=201)

    async def picture(request: Request):
        b = server.bundles.get(request.path_params["bundle"])
        path = b.file(f"{request.path_params['kind']}/{request.path_params['file']}") if b else None
        if path is None:
            return PlainTextResponse("not found", status_code=404)
        mime = stage_types.FILE_TYPES.get(path.suffix) or stage_types.video.TYPES.get(path.suffix, "image/png")
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    async def deck_media(request: Request):
        """POST: the addresses of the deck's video files for this window - {file: address}."""
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        b = server.bundles.get(request.path_params["bundle"])
        if b is None or not b.open_to(lect):
            return JSONResponse({"error": "no such bundle"}, status_code=404)
        now = now_ms()
        return JSONResponse({name: server.media_ticket(b.id, name, now)
                             for name in stage_types.video.media(b.items.get("video", {}))
                             if (path := b.media(name)) is not None})

    async def media_file(request: Request):
        found = server.media.get(request.path_params["ticket"])
        if found is None or found[2] < now_ms() or Path(found[1]).name != request.path_params["name"]:
            return PlainTextResponse("this video's address expired - reload the window", status_code=404)
        bundle = server.bundles.get(found[0])
        path = bundle.media(found[1]) if bundle is not None else None
        if path is None:
            return PlainTextResponse("this video's address expired - reload the window", status_code=404)
        return FileResponse(path, media_type=stage_types.video.TYPES.get(path.suffix, "video/mp4"),
                            headers={"Cache-Control": "private, max-age=43200"})   # byte ranges: seeking

    async def join_qr(request: Request):
        pin = request.path_params["pin"]
        if not pin.isdigit() or len(pin) != 6:
            return PlainTextResponse("not found", status_code=404)
        buf = io.BytesIO()
        segno.make_qr(f"{config.public_url}/play?pin={pin}", error="m").save(buf, kind="svg", scale=8, border=2)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        conn = Conn(ws)
        writer = asyncio.create_task(conn.writer())
        try:
            while not conn.closing:
                text = await ws.receive_text()
                if len(text) > MESSAGE_MAX:
                    conn.send({"t": "error", "error": "too-large", "message": "message too large"})
                    continue
                try:
                    msg = json.loads(text)
                except ValueError:
                    msg = None
                if not isinstance(msg, dict):
                    conn.send({"t": "error", "error": "bad-json", "message": "expected a JSON object"})
                    continue
                await server.handle(conn, msg)
        except (WebSocketDisconnect, RuntimeError, KeyError):
            pass
        finally:
            server.disconnect(conn)
            if conn.closing:
                with contextlib.suppress(asyncio.TimeoutError, Exception):
                    await asyncio.wait_for(writer, 2)
            writer.cancel()

    def lecturer(request: Request, devices: bool = True) -> str | None:
        """The lecturer whose presenter key the request brings (header X-Texquiz-Key) - or,
        unless devices=False (publishing, pairing), whose paired device it comes from
        (X-Texquiz-Device, texstage)."""
        found = server.lecturers.who(request.headers.get("x-texquiz-key"))
        if found is None and devices and request.headers.get("x-texquiz-device"):
            found = (server.devices.who(request.headers.get("x-texquiz-device"), now_ms()) or (None,))[0]
        return found

    # ------------------------------------------------------------ presenter devices (texstage)
    async def pair_offer(request: Request):
        """A one-time pairing code for the QR code in the presenter window (devices.py)."""
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        p = server.devices.offer(lect, now_ms())
        url = f"{config.public_url}/stage#pair={p.token}"          # in the fragment: never sent to a server
        qr = segno.make_qr(url, error="m").svg_inline(scale=6, border=2)
        return JSONResponse({"token": p.token, "url": url, "qr": qr, "expires": p.created + PAIR_MS})

    async def pair_status(request: Request):
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        p = server.devices.status(lect, request.path_params["token"], now_ms())
        if p is None:
            return JSONResponse({"state": "expired"}, status_code=404)
        return JSONResponse({"state": p.state, "name": p.name, "code": p.code})

    async def pair_decide(request: Request):
        """The lecturer allows the device whose code matches - or does not."""
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        allow = (await small_json(request)).get("allow") is True
        p = server.devices.decide(lect, request.path_params["token"], allow, now_ms())
        if p is None:
            return JSONResponse({"error": "no device is waiting for this code"}, status_code=404)
        return JSONResponse({"state": p.state})

    async def pair_claim(request: Request):
        """The device that opened the QR code: it waits for the lecturer, with a code to compare."""
        addr, now = request.client.host if request.client else "", now_ms()
        if server.pair_attempts.blocked(addr, now):
            return JSONResponse({"error": "too many unknown codes from this network - try again later"}, status_code=429)
        body = await small_json(request)
        p = server.devices.claim(body.get("token"), body.get("name"), now)
        if p is None:
            server.pair_attempts.failed(addr, now)
            return JSONResponse({"error": "this pairing code is used or expired"}, status_code=404)
        return JSONResponse({"claim": p.claim, "code": p.code})

    async def pair_wait(request: Request):
        """The device asks whether it may: approved - its token, once -, denied, or still waiting."""
        p = server.devices.wait((await small_json(request)).get("claim"), now_ms())
        if p is None:
            return JSONResponse({"state": "expired"}, status_code=404)
        return JSONResponse({"state": p.state, **({"device": p.device} if p.state == "approved" else {})})

    async def devices_list(request: Request):
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        return JSONResponse(server.devices.list(lect))

    async def device_remove(request: Request):
        lect = lecturer(request, devices=False)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        return JSONResponse({"removed": server.remove_device(lect, request.path_params["device"])})

    def page(name: str, file: str = "index.html"):
        async def endpoint(request: Request):
            return FileResponse(WEB / name / file, headers={"Cache-Control": "no-cache"})
        return endpoint

    def built_ms(b) -> int:
        return int((b.path / "deck.json").stat().st_mtime * 1000)

    def uploaded_builds(lect: str, deck: str) -> list[Path]:
        """The builds of a deck this lecturer uploaded: bundles/<lecturer>/<deck>/<id>/."""
        folder = server.published / lect / deck
        if not DECK_ID.match(deck) or not folder.is_dir():
            return []
        return [d for d in folder.iterdir() if (d / "deck.json").is_file()]

    async def decks(request: Request):
        """The decks this lecturer can play, newest build of each first, with their games - and
        each deck's folder and shown name on the lecturer's deck page (library.py). A deck taken
        off the list stays off it until a newer build of it comes."""
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        server.bundles.scan()
        lib = server.library.view(lect)["decks"]

        def listed(b) -> bool:
            hidden = (lib.get(b.deck) or {}).get("hidden") if isinstance(lib.get(b.deck), dict) else None
            return b.open_to(lect) and (not isinstance(hidden, int) or built_ms(b) > hidden)

        running = {s.deck: s for s in server.engine.sessions.values() if s.owner == lect}
        newest = {}                                      # per deck its newest build, and the one played
        for b in server.bundles.current():
            if listed(b) and (b.deck not in newest or built_ms(b) > built_ms(newest[b.deck])):
                newest[b.deck] = b
        shown = {b.id: b for b in newest.values()}
        for s in running.values():
            b = server.bundles.bundles.get(s.bundle)
            if b is not None and listed(b):
                shown[b.id] = b
        out = []
        for b in shown.values():
            s = running.get(b.deck)
            entry = lib.get(b.deck) if isinstance(lib.get(b.deck), dict) else {}
            out.append({"bundle": b.id, "deck": b.deck, "name": b.name, "quizzes": len(b.quizzes),
                        "slides": len(b.slides), "built": built_ms(b),
                        "complete": b.complete(), "stage": b.stage_pdf() is not None,
                        "game": {"pin": s.pin, "players": len(s.active_players()), "session": s.id}
                        if s and s.bundle == b.id else None,
                        "folder": entry.get("folder"), "label": entry.get("label"),
                        "uploaded": bool(uploaded_builds(lect, b.deck))})   # deleting deletes them
        out.sort(key=lambda d: (d["name"].casefold(), -d["built"]))
        return JSONResponse(out)

    # ------------------------------------------------------------ the deck page (library.py)
    async def json_body(request: Request) -> dict:
        try:
            data = await request.json()
        except ValueError:
            raise LibraryError("not JSON") from None
        if not isinstance(data, dict):
            raise LibraryError("not a JSON object")
        return data

    def refused(err: LibraryError) -> JSONResponse:
        return JSONResponse({"error": str(err)}, status_code=404 if err.missing else 400)

    def known_deck(lect: str, deck: str) -> bool:
        return any(b.deck == deck and b.open_to(lect) for b in server.bundles.current())

    async def folders(request: Request):
        """GET /api/folders: the lecturer's folders [{id, name, parent}]; POST: a new one {name, parent}."""
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        if request.method == "GET":
            return JSONResponse(server.library.folders(lect))
        try:
            data = await json_body(request)
            fid = server.library.add_folder(lect, data.get("name"), data.get("parent"))
        except LibraryError as err:
            return refused(err)
        return JSONResponse({"id": fid}, status_code=201)

    async def folder(request: Request):
        """PATCH /api/folders/<id> {name, parent}: renames or moves it (parent null: to the top);
        DELETE: deletes it, its folders and decks move up to its parent."""
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        fid = request.path_params["folder"]
        try:
            if request.method == "DELETE":
                server.library.remove_folder(lect, fid)
            else:
                data = await json_body(request)
                server.library.change_folder(lect, fid, {k: data[k] for k in ("name", "parent") if k in data})
        except LibraryError as err:
            return refused(err)
        return JSONResponse({"ok": True})

    async def deck_entry(request: Request):
        """PATCH /api/decks/<deck> {folder, label}: moves it (folder null: to the top) or gives it
        another shown name (label "" or null: its own). DELETE: off the deck page - the builds of it
        this lecturer uploaded are deleted, a laptop's builds only leave the list (the next build
        brings the deck back). A game this lecturer plays from an uploaded build refuses the delete
        while it runs; one left over from an earlier lecture ends (its results stay in the archive)."""
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        deck = request.path_params["deck"]
        if not known_deck(lect, deck):
            return JSONResponse({"error": "no such deck"}, status_code=404)
        if request.method == "PATCH":
            try:
                data = await json_body(request)
                server.library.change_deck(lect, deck, {k: data[k] for k in ("folder", "label") if k in data})
            except LibraryError as err:
                return refused(err)
            return JSONResponse({"ok": True})
        async with server.publishing:
            mine = uploaded_builds(lect, deck)
            now = now_ms()
            ids = {d.name for d in mine}
            games = [s for s in server.engine.sessions.values()
                     if s.owner == lect and s.ended is None and s.bundle in ids]
            if any(now - s.last_active < server.engine.settings.stale_ms for s in games):
                return JSONResponse({"error": "a game of this deck is running - delete it after the lecture"},
                                    status_code=409)
            folder = server.published.resolve() / lect / deck
            if any(not d.resolve().is_relative_to(folder) for d in mine):
                return JSONResponse({"error": "uploaded build is outside its deck folder"}, status_code=400)
            for s in games:
                server.engine.end(s.id, now)
            for d in mine:
                server.bundles.drop(d)
                await asyncio.to_thread(shutil.rmtree, d, True)
            with contextlib.suppress(OSError):
                (server.published / lect / deck).rmdir()  # its folder, now empty
        laptop = known_deck(lect, deck)                  # a laptop's builds, or served copies of them
        if laptop:
            server.library.hide(lect, deck, now)
        log.info("deck %s off %s's list: %d uploaded builds deleted%s", deck, lect, len(mine),
                 ", the laptop's hidden" if laptop else "")
        return JSONResponse({"deleted": len(mine), "hidden": laptop})

    async def deck_json(request: Request):
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        b = server.bundles.get(request.path_params["bundle"])
        if b is None or not b.open_to(lect):
            return JSONResponse({"error": "no such bundle"}, status_code=404)
        return JSONResponse(b.deck_json)

    async def deck_pdf(request: Request):
        """The stage PDF (texstage): every page of the deck, reveal pages too, so for hosts
        only - not a picture name to guess (docs/texstage-design.md, section 3)."""
        lect = lecturer(request)
        if lect is None:
            return JSONResponse({"error": "presenter key required"}, status_code=403)
        b = server.bundles.get(request.path_params["bundle"])
        path = b.stage_pdf() if b is not None and b.open_to(lect) else None
        if path is None:
            return JSONResponse({"error": "no stage PDF for this bundle (build the deck again, without --no-stage)"}, status_code=404)
        return FileResponse(path, media_type="application/pdf",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

    def own_game(request: Request):
        """(the game named in the path, None) - or (None, the refusal): not the lecturer's."""
        lect = lecturer(request)
        if lect is None:
            return None, PlainTextResponse("presenter key required", status_code=403)
        s = server.engine.sessions.get(request.path_params["session"])
        if s is None or s.ended is not None or s.owner != lect:
            return None, PlainTextResponse("no such game", status_code=404)      # or another lecturer's
        return s, None

    async def results(request: Request):
        s, refused = own_game(request)
        if refused:
            return refused
        name, text = server.results_csv(s)
        return Response(text, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    async def plugin_archive(request: Request):
        s, refused = own_game(request)
        if refused: return refused
        return JSONResponse(server.plugins.runtime.archive(s.id) if server.plugins.runtime else {"format": 1, "items": []},
                            headers={"Cache-Control": "no-store"})

    async def plugin_public_archive(request: Request):
        s, refused = own_game(request)
        if refused: return refused
        result = server.plugins.runtime.public_archive(s.id) if server.plugins.runtime else {
            "format": 1, "surface": "projector-overlay", "items": []}
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    async def plugin_asset(request: Request):
        try:
            raw, mime = server.plugins.asset(request.path_params["payload"], request.path_params["name"])
        except PluginError:
            return PlainTextResponse("not found", status_code=404)
        return Response(raw, media_type=mime, headers={"Cache-Control": "public, max-age=31536000, immutable",
                                                       "X-Content-Type-Options": "nosniff"})

    async def archive_pdf(request: Request):
        """PUT /api/archive/<game>/annotated.pdf: the annotated PDF the presenter window made
        (texstage, M4) into the lecture archive, with the game's results as they are now."""
        s, refused = own_game(request)
        if refused:
            return refused
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > ARCHIVE_MAX:
                return JSONResponse({"error": "the PDF is too large"}, status_code=413)
        if not data.startswith(b"%PDF-"):
            return JSONResponse({"error": "not a PDF"}, status_code=400)
        folder = server.write_archive(s)
        tmp = folder / "annotated.pdf.tmp"
        tmp.write_bytes(bytes(data))
        tmp.replace(folder / "annotated.pdf")
        return JSONResponse({"folder": folder.relative_to(config.data_dir).as_posix(),
                             "files": [f["name"] for f in archive.files(folder)]})

    async def archive_zip(request: Request):
        """GET /api/archive/<game>.zip: the game's folder in the lecture archive - the annotated
        PDF, the results, polls, questions and sketches (made anew) - as one file. Recordings
        are downloaded on their own."""
        s, refused = own_game(request)
        if refused:
            return refused
        folder = server.write_archive(s)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in archive.files(folder):
                if "take" not in f:
                    z.write(folder / f["name"], f["name"], compress_type=zipfile.ZIP_DEFLATED)
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{folder.parent.name}-{folder.name}.zip"'})

    async def archive_files(request: Request):
        """GET /api/archive/<game>/files: what the game's folder holds, recordings with their take."""
        s, refused = own_game(request)
        if refused:
            return refused
        folder = archive.folder(config.data_dir, s, make=False)
        return JSONResponse([f | ({"remuxing": True} if f.get("take") in server.recordings.remuxing else {})
                             for f in archive.files(folder)])

    # ------------------------------------------------------------ recordings (texstage, M5)
    async def recording_start(request: Request):
        """POST /api/archive/<game>/recording {ext: webm|mp4}: a new recording, kept in the
        game's folder of the archive (also if the lecture goes on with another game)."""
        s, refused = own_game(request)
        if refused:
            return refused
        try:
            t = server.recordings.start(archive.folder(config.data_dir, s), s.owner,
                                        (await small_json(request)).get("ext"), now_ms())
        except ArchiveError as err:
            return JSONResponse({"error": str(err)}, status_code=err.status)
        log.info("recording %s started for %s (%s)", t.id, s.owner, t.folder)
        return JSONResponse(server.take_info(t), status_code=201)

    def own_take(request: Request):
        """(the recording named in the path, None) - or (None, the refusal): not the lecturer's."""
        lect = lecturer(request)
        if lect is None:
            return None, JSONResponse({"error": "presenter key required"}, status_code=403)
        t = server.recordings.get(request.path_params["take"], lect)
        if t is None:
            return None, JSONResponse({"error": "no such recording"}, status_code=404)
        return t, None

    async def recording_part(request: Request):
        """PUT /api/recording/<take>/<part>: the next part (MediaRecorder's data) -> {next, size}."""
        t, refused = own_take(request)
        if refused:
            return refused
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > archive.PART_MAX:
                return JSONResponse({"error": "the part is too large"}, status_code=413)
        try:
            n = server.recordings.add(t, request.path_params["part"], bytes(data))
        except ArchiveError as err:
            return JSONResponse({"error": str(err), "next": t.parts}, status_code=err.status)
        except OSError as err:
            log.error("recording %s: %s", t.id, err)
            return JSONResponse({"error": f"the server cannot write the recording ({err.strerror or err})"},
                                status_code=507)
        return JSONResponse({"next": n, "size": t.size})

    async def recording_done(request: Request):
        """POST /api/recording/<take>/done: the recording stopped - its file is finished (and
        remuxed in the background, if ffmpeg is installed)."""
        t, refused = own_take(request)
        if refused:
            return refused
        try:
            path = server.recordings.finish(t, now_ms())
        except OSError as err:
            return JSONResponse({"error": f"the server cannot finish the recording ({err.strerror or err})"},
                                status_code=507)
        if path is None:
            return JSONResponse({"take": t.id, "file": None, "size": 0})      # nothing was recorded
        log.info("recording %s finished: %s, %d bytes", t.id, path, t.size)
        return JSONResponse(server.take_info(t))

    async def recording_status(request: Request):
        t, refused = own_take(request)
        if refused:
            return refused
        return JSONResponse(server.take_info(t))

    async def recording_download(request: Request):
        """POST /api/recording/<take>/download -> {url}: an address that downloads the file -
        a link cannot send the key, and a recording is too large for the page's memory."""
        t, refused = own_take(request)
        if refused:
            return refused
        if t.finished is None or t.id in server.recordings.remuxing or not t.file.exists():
            return JSONResponse({"error": "the recording is not finished yet"}, status_code=409)
        return JSONResponse({"url": server.download(t.file, t.download_name(), now_ms())})

    async def download_file(request: Request):
        found = server.downloads.get(request.path_params["ticket"])
        if found is None or found[2] < now_ms() or found[1] != request.path_params["name"] or not found[0].exists():
            return PlainTextResponse("this download address expired - ask the presenter window again", status_code=404)
        path, name, _ = found
        return FileResponse(path, filename=name, media_type="video/mp4" if name.endswith(".mp4") else "video/webm",
                            headers={"Cache-Control": "private, no-store"})       # not in a proxy's cache

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await server.start()
        try:
            yield
        finally:
            await server.stop()

    async def home(request: Request):
        return RedirectResponse("/play")                 # people type just the address

    async def client_log(request: Request):
        """Errors and diagnostics from host pages (the add-in runs inside PowerPoint, where
        nobody sees its console): written to the server's log."""
        lect = lecturer(request)
        if lect is None:
            return PlainTextResponse("presenter key required", status_code=403)
        body = (await request.body())[:4000].decode("utf-8", "replace")
        log.warning("client (%s): %s", lect, body)
        return PlainTextResponse("ok")

    async def addin_manifest(request: Request):
        from texstage.addin import manifest
        origin = f"{request.url.scheme}://{request.url.netloc}"
        return Response(manifest(origin), media_type="application/xml")

    icons: dict[int, bytes] = {}

    async def addin_icon(request: Request):
        size = int(request.path_params["size"])
        if size not in (16, 32, 64, 80, 128):
            return PlainTextResponse("not found", status_code=404)
        if size not in icons:
            icons[size] = make_icon(size)
        return Response(icons[size], media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    app = Starlette(routes=[
        Route("/", home),
        Route("/api/status", status),
        Route("/plugins/{payload}/{name:path}", plugin_asset),
        Route("/api/archive/{session}/plugins.json", plugin_archive),
        Route("/api/archive/{session}/plugins-public.json", plugin_public_archive),
        Route("/play", page("play")),
        Route("/host", page("host")),
        Route("/stage", page("stage")),
        Route("/stage/projector", page("stage", "projector.html")),
        Route("/addin/", page("addin")),
        Route("/addin/manifest.xml", addin_manifest),
        Route("/addin/icon-{size:int}.png", addin_icon),
        Mount("/static", Static(directory=WEB)),
        Route("/api/presenter-key", presenter_key),
        Route("/api/pair", pair_offer, methods=["POST"]),
        Route("/api/pair/claim", pair_claim, methods=["POST"]),
        Route("/api/pair/wait", pair_wait, methods=["POST"]),
        Route("/api/pair/{token}", pair_status, methods=["GET"]),
        Route("/api/pair/{token}", pair_decide, methods=["POST"]),
        Route("/api/devices", devices_list),
        Route("/api/devices/{device}", device_remove, methods=["DELETE"]),
        Route("/api/decks", decks),
        Route("/api/decks/{deck}", deck_entry, methods=["PATCH", "DELETE"]),
        Route("/api/folders", folders, methods=["GET", "POST"]),
        Route("/api/folders/{folder}", folder, methods=["PATCH", "DELETE"]),
        Route("/api/deck/{bundle}", deck_json),
        Route("/api/deck/{bundle}/pdf", deck_pdf),
        Route("/api/deck/{bundle}/media", deck_media, methods=["POST"]),
        Route("/media/{ticket}/{name}", media_file),
        Route("/api/results/{session}.csv", results),
        Route("/api/archive/{session}/annotated.pdf", archive_pdf, methods=["PUT"]),
        Route("/api/archive/{session}.zip", archive_zip),
        Route("/api/archive/{session}/files", archive_files),
        Route("/api/archive/{session}/recording", recording_start, methods=["POST"]),
        Route("/api/recording/{take}", recording_status),
        Route("/api/recording/{take}/done", recording_done, methods=["POST"]),
        Route("/api/recording/{take}/download", recording_download, methods=["POST"]),
        Route("/api/recording/{take}/{part:int}", recording_part, methods=["PUT"]),
        Route("/download/{ticket}/{name}", download_file),
        Route("/api/client-log", client_log, methods=["POST"]),
        Route("/api/bundles/{bundle}", publish, methods=["PUT"]),
        Route("/api/bundles", upload, methods=["POST"]),
        Route("/bundle/{bundle}/{kind}/{file}", picture),
        Route("/join/{pin}.svg", join_qr),
        WebSocketRoute("/ws", ws_endpoint),
    ], lifespan=lifespan)
    app.state.server = server
    return app
