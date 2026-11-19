# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Quiz bundles on the server: loading, checking, finding them by ID.

A bundle is the folder `texstage build` writes (<name>.bundle/: deck.json, keys.json,
slides/, phone/, with --stage stage/; see texstage/build/bundle.py). The server never changes it. Bundles are
found in the folders given to `texstage serve`: a folder is a bundle itself, or holds
bundles (searched three levels deep, e.g. a lecture chapter's build/texquiz/), and in the
data folder: bundles/<lecturer>/<deck>/<id>/ (uploads, the lecturer's) and served/<deck>/<id>/
(copies of served decks being played). An unknown bundle ID makes the store look again, so
a rebuilt deck is picked up without a restart. A folder it cannot play is skipped, and says why
(Skipped): texstage serve prints those of its first look, the server's log a new one found later,
and the deck list shows them (GET /api/skipped). A look reads a folder again only where its
deck.json, keys.json or built.json changed since the last (their stamps), and the server takes the
looking out of its event loop (BundleStore.collect in a worker thread, apply on the loop): a deck
list asked for in a lecture holds up no phone. A build's time is its built.json's, which the build
writes beside deck.json and the bundle's copies keep - an old build copied or checked out again is
not the newest -, else deck.json's file time (builds made before 2026-11-17).
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from texstage.build.bundle import LANGUAGES, READS, bundle_id
from texstage.server import types as stage_types

log = logging.getLogger("texstage.server")
FILE = re.compile(r"^((slides|phone)/[0-9a-f]{16}\.png|media/[0-9a-f]{16}\.(jpg|png))$")   # pictures, posters
STAGE_PDF = re.compile(r"^stage/[0-9a-f]{16}\.pdf$")
BUILT = "built.json"                 # a build's time (ms), beside deck.json - no part of the bundle's ID; it may
                                     # hold the build's warnings too, which the server keeps and does not read
KNOWN_TYPES = stage_types.KNOWN      # the content types this server knows: a deck that needs another is refused


class BundleError(ValueError):
    """A folder is not a usable bundle."""


@dataclass
class QuizDef:
    id: str
    type: str                 # single multiple truefalse poll numeric text open order sketch
    time: int                 # seconds
    points: str               # standard double none
    scored: bool
    leaderboard: bool
    reveal: str               # slide none
    select: str               # polls: single multiple
    ids: list[str]            # public answer ids in display order (A, B, ...)
    numeric: dict             # min max step unit (public)
    open: dict                # display max_chars
    public: dict              # deck.json's entry: what the phones get
    keys: dict                # keys.json's entry: host only, phones after the reveal

    @property
    def base(self) -> int:
        return {"standard": 1000, "double": 2000}.get(self.points, 0)


@dataclass
class SlideInfo:
    id: int                   # PowerPoint slide ID
    index: int                # 1-based position in the deck
    phase: str | None         # join read question reveal answer leaderboard podium, None: ordinary
    quiz: str | None
    shows: dict[str, tuple[str, ...]] = field(default_factory=dict)   # per content type its items on it
    marks: dict[str, dict[str, str]] = field(default_factory=dict)    # per type what the page is of an item: its
    #                                                                   live box's phase (an activity's: open, revealed)


@dataclass
class Bundle:
    id: str
    deck: str
    name: str
    path: Path
    slides: dict[int, SlideInfo]
    quizzes: dict[str, QuizDef]
    deck_json: dict = field(repr=False, default_factory=dict)
    keys: dict = field(repr=False, default_factory=dict)
    owners: set[str] | None = None       # the lecturers who uploaded it; None: open to every lecturer
    items: dict = field(repr=False, default_factory=dict)   # per content type its items (deck.json's)
    built: int = 0                       # when it was built (ms): its built.json's time, else deck.json's -
    #                                      an upload and a served copy keep the build's; the newest of its copies

    def open_to(self, lecturer: str | None) -> bool:
        return lecturer is not None and (self.owners is None or lecturer in self.owners)

    @property
    def language(self) -> str:
        """The deck's language as its windows and phones speak it (web/i18n/i18n.js): deck.json's
        BCP 47 tag if texstage speaks it (build/bundle.py, LANGUAGES), else - another language, a
        deck built before 2026-10-24 - English."""
        tag = self.deck_json.get("language")
        return tag if isinstance(tag, str) and tag in LANGUAGES else "en"

    def file(self, rel: str) -> Path | None:
        """A picture of the bundle (a slide, a phone picture, a video's poster) or a file a
        content type serves as the pictures are (types.py: FILES); None for anything else (no
        path tricks)."""
        if not FILE.match(rel) and not stage_types.bundle_file(rel):
            return None
        path = self.path / rel
        return path if path.is_file() else None

    @property
    def thumb(self) -> str | None:
        """The first slide's picture (slides/<hash>.png), the deck page's card shows it small; None if
        deck.json names none."""
        slides = self.deck_json.get("slides")
        first = slides[0] if isinstance(slides, list) and slides and isinstance(slides[0], dict) else {}
        image = first.get("image")
        return image if isinstance(image, str) and FILE.match(image) and image.startswith("slides/") else None

    def media(self, rel: str) -> Path | None:
        """A video file the deck names (served by ticket only); None for anything else."""
        if rel not in stage_types.video.media(self.items.get("video", {})):
            return None
        path = self.path / rel
        return path if path.is_file() else None

    def stage_pdf(self) -> Path | None:
        """The stage PDF for texstage (every texstage build but --no-stage); None if the build has none."""
        name = (self.deck_json.get("pdf") or {}).get("file", "")
        if not STAGE_PDF.match(name):
            return None
        path = self.path / name
        return path if path.is_file() else None

    def complete(self) -> bool:
        """Whether every file the bundle names is there. The bundle a PowerPoint file
        carries (uploaded by its add-in) lacks the ordinary slides' pictures and the stage
        PDF."""
        return all((self.path / name).is_file() for name in bundle_files(self.deck_json, self.keys))


@dataclass
class Skipped:
    """A folder with a deck.json that the server does not play: why, and what its deck.json says of
    itself as far as it can be read - for the deck list (GET /api/skipped) and texstage present."""
    path: Path
    owner: str | None           # an upload's lecturer; None: open to every lecturer, as its bundle would be
    error: str                  # why, without the folder in front
    deck: str | None = None
    name: str | None = None
    bundle: str | None = None


def skipped_folder(folder: Path, owner: str | None, err: BundleError) -> Skipped:
    try:
        deck = json.loads((folder / "deck.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        deck = {}

    def text(key: str) -> str | None:
        value = deck.get(key) if isinstance(deck, dict) else None
        return value if isinstance(value, str) and len(value) <= 200 else None
    return Skipped(folder, owner, str(err).removeprefix(f"{folder}: "), text("deck"), text("name"), text("bundle"))


def bundle_files(*parts: dict) -> set[str]:
    """The pictures, the media files, the stage PDF and the content types' files (types.py:
    FILES) that deck.json and keys.json name."""
    kinds = [r"(?:slides|phone)/[0-9a-f]{16}\.png", r"stage/[0-9a-f]{16}\.pdf", r"media/[0-9a-f]{16}\.[a-z0-9]{2,4}",
             *stage_types.FILES]
    return set(re.findall(f'"((?:{"|".join(kinds)}))"', json.dumps(parts)))


def holds(b: Bundle) -> bool:
    """Whether the bundle's folder still holds this build (a rebuild replaces it)."""
    try:
        return json.loads((b.path / "deck.json").read_text(encoding="utf-8")).get("bundle") == b.id
    except (OSError, ValueError):
        return False


def load_bundle(path: Path, plays: bool = True) -> Bundle:
    """The bundle in this folder, checked: its format and ID, the content types it needs - and, with `plays`,
    whether this server can play its activities (types.refuses: the kinds installed here). texstage publish
    asks without: the server it sends a deck to judges that itself (until 2026-11-19 publish skipped a deck
    whose kinds its own machine lacked, or had older - nothing sent)."""
    try:
        with (path / "deck.json").open(encoding="utf-8") as f:
            deck = json.loads(f.read())
            built = int(os.fstat(f.fileno()).st_mtime * 1000)     # (the file read: a rebuild may replace the folder)
        keys = json.loads((path / "keys.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise BundleError(f"{path}: {err}") from None
    built = built_time(path) or built
    fmt = deck.get("format")
    if fmt not in READS or keys.get("format") != fmt:
        raise BundleError(f"{path}: bundle format {fmt}, this server reads {' and '.join(map(str, READS))}")
    bid = deck.get("bundle")
    unsigned = ({k: v for k, v in deck.items() if k != "bundle"}, {k: v for k, v in keys.items() if k != "bundle"})
    if not bid or keys.get("bundle") != bid or bundle_id(*unsigned) != bid:
        raise BundleError(f"{path}: deck.json and keys.json do not match their bundle ID")
    if fmt == 1:
        public, private, view, items = deck["quizzes"], keys["quizzes"], deck, {"quiz": deck["quizzes"]}
    else:
        items = deck.get("items", {})
        unknown = sorted(set(deck.get("types", [])) - KNOWN_TYPES)
        if unknown:
            raise BundleError(f"{path}: the deck needs {', '.join(unknown)}, which this server does not know - "
                              f"update texstage")
        why = stage_types.refuses(deck) if plays else None      # (the core's type: a kind this server lacks)
        if why:
            raise BundleError(f"{path}: {why}")
        public, private = deck.get("items", {}).get("quiz", {}), keys.get("items", {}).get("quiz", {})
        view = client_view(deck)
    quizzes = {}
    for qid, q in public.items():
        quizzes[qid] = QuizDef(
            id=qid, type=q["type"], time=int(q["time"]), points=q["points"], scored=bool(q["scored"]),
            leaderboard=bool(q["leaderboard"]), reveal=q["reveal"], select=q.get("select", "single"),
            ids=[a["id"] for a in q.get("answers", [])], numeric=q.get("numeric", {}),
            open=q.get("open", {}), public=q, keys=private.get(qid, {}))
    slides = {}
    for i, s in enumerate(view["slides"], 1):
        if s.get("quiz") and s["quiz"] not in quizzes:
            raise BundleError(f"{path}: slide {i} names an unknown quiz {s['quiz']}")
        shows: dict[str, list[str]] = {}
        marks: dict[str, dict[str, str]] = {}
        for box in s.get("live", []):
            if box.get("type") in stage_types.TYPES:
                if box.get("item") not in items.get(box["type"], {}):
                    raise BundleError(f"{path}: slide {i} names an unknown {box['type']} {box.get('item')}")
                shows.setdefault(box["type"], []).append(box["item"])
                if isinstance(box.get("phase"), str):
                    marks.setdefault(box["type"], {})[box["item"]] = box["phase"]
        slides[s["id"]] = SlideInfo(s["id"], i, s.get("phase"), s.get("quiz"), {k: tuple(v) for k, v in shows.items()},
                                    marks)
    return Bundle(bid, deck["deck"], deck.get("name", deck["deck"]), path, slides, quizzes, view, keys,
                  items=items, built=built)


EARLIEST = 946_684_800_000                # 2000-01-01: no build of texstage was made before it (ms)


def built_time(path: Path) -> int | None:
    """When the build in this folder was made (ms), as its built.json says (build/bundle.py:
    write_bundle); None where it has none, or one that cannot be read or cannot be so: before 2000, or
    more than a day ahead of this clock (a laptop's clock gone wrong, microseconds for milliseconds - such
    a build would stay the newest, and its deck could not be taken off the list)."""
    try:
        value = json.loads((path / BUILT).read_text(encoding="utf-8")).get("built")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if EARLIEST <= value <= time.time() * 1000 + 86_400_000 else None


def changes(new: Bundle, old: Bundle) -> dict:
    """What changed from build `old` to build `new` of a deck, for the deck page's Builds: its slides - their
    pictures, named by their content's hash, in order: added, removed, changed (one picture for another at its
    place) - and per content type its items (quizzes, activities, videos ...) by ID: added, removed, changed
    (their definition or their keys - a reference, a right answer)."""
    from difflib import SequenceMatcher

    def pictures(b: Bundle) -> list[str]:
        slides = b.deck_json.get("slides")
        return [str(s.get("image")) for s in slides if isinstance(s, dict)] if isinstance(slides, list) else []

    def keys(b: Bundle, kind: str) -> dict:
        found = (b.keys.get("items") or {}).get(kind) if isinstance(b.keys.get("items"), dict) else None
        found = found if found is not None else (b.keys.get("quizzes") if kind == "quiz" else None)
        return found if isinstance(found, dict) else {}

    was, now = pictures(old), pictures(new)
    slides = {"added": 0, "removed": 0, "changed": 0}
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, was, now, autojunk=False).get_opcodes():
        if tag == "replace":
            slides["changed"] += min(i2 - i1, j2 - j1)
            slides["added"] += max(0, (j2 - j1) - (i2 - i1))
            slides["removed"] += max(0, (i2 - i1) - (j2 - j1))
        elif tag == "insert":
            slides["added"] += j2 - j1
        elif tag == "delete":
            slides["removed"] += i2 - i1
    items = {}
    for kind in sorted(set(new.items) | set(old.items)):
        a, b = old.items.get(kind) or {}, new.items.get(kind) or {}
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        ka, kb = keys(old, kind), keys(new, kind)
        counted = {"added": len(set(b) - set(a)), "removed": len(set(a) - set(b)),
                   "changed": sum(1 for i in set(a) & set(b) if a[i] != b[i] or ka.get(i) != kb.get(i))}
        if any(counted.values()):
            items[kind] = counted
    return {"slides": slides, "items": items}


def client_view(deck: dict) -> dict:
    """A format-2 deck.json as the windows read it (until they read the live boxes
    themselves): the quiz's items also as "quizzes", and a slide's quiz box also as its
    "phase", "quiz" and "rects" - what format 1 had. The rest is kept as it is."""
    view = dict(deck, quizzes=deck.get("items", {}).get("quiz", {}))
    slides = []
    for s in deck.get("slides", []):
        box = next((b for b in s.get("live", []) if b.get("type") == "quiz"), None)
        if box is not None:
            s = dict(s, phase=box.get("phase"))
            for key, name in (("item", "quiz"), ("rects", "rects")):
                if key in box:
                    s[name] = box[key]
        slides.append(s)
    view["slides"] = slides
    return view


@dataclass(frozen=True)
class Seen:
    """A folder as a look found it: the stamp of its files (deck.json, keys.json, built.json: their
    times and sizes), and what loading it gave - its build, whether every file of it was there, or
    why it is skipped. A folder whose stamp is the same is not read again."""
    stamp: tuple | None
    bundle: Bundle | None = None
    complete: bool = False
    skipped: Skipped | None = None
    error: str | None = None


def stamp(folder: Path) -> tuple | None:
    """What a folder's files are now, as far as a build changes them: deck.json's, keys.json's and
    built.json's identity (a build writes its folder anew: new files - two builds with the same size
    and a time this machine's coarse clock gave both are told apart by it), time and size - None where
    deck.json or keys.json cannot be looked at."""
    out = []
    for name in ("deck.json", "keys.json", BUILT):
        try:
            s = (folder / name).stat()
        except OSError:
            if name != BUILT:
                return None
            out.append(None)
            continue
        out.append((s.st_dev, s.st_ino, s.st_mtime_ns, s.st_size))
    return tuple(out)


def key(path: Path) -> str:
    """A folder as the store keys it: its absolute path, as this system compares names (no Path.resolve -
    a file system call per folder, most of a look's time on Windows)."""
    return os.path.normcase(os.path.abspath(path))


class BundleStore:
    RESCAN_S = 2.0           # an unknown ID rescans the folders at most this often

    def __init__(self, roots: list[Path], published: Path | None = None, more=None, plays: bool = True):
        """published: the folder of uploaded bundles, <lecturer>/<deck>/<bundle id>/ - they
        belong to their lecturer; the bundles in the other folders are open to every lecturer.
        more: further folders, asked at every scan (the builds of this machine, builds.py).
        plays=False: a deck this server could not play is found too (load_bundle; texstage publish)."""
        self.roots = [Path(r) for r in roots]
        self.more = more or (lambda: [])
        self.plays = plays
        self.published = key(published) if published else None
        self.bundles: dict[str, Bundle] = {}
        self.dropped: set[str] = set()     # (keys) a cleanup can still be removing files asynchronously
        self.problems: list[str] = []      # the folders skipped by the last scan, each with why
        self.skipped: list[Skipped] = []   # ... the same, for the deck list
        self.told: set[str] | None = None  # the problems said already (None: before the first scan)
        self.scanned = 0.0
        self.seen: dict[str, Seen] = {}    # per folder (key), as the last look found it - replaced whole
        self.looking = threading.Lock()    # one look at a time (collect: also in a worker thread)
        self.scan()

    def drop(self, path: Path):
        """Forget this copy, preserving other lecturers' copies of the same build.

        Called before removing the folder. Scans must not rediscover it during that
        removal - a look under way when it was dropped included (apply) -; a later explicit upload
        (add) makes the path available again. Its other copies are those the record knows (add
        records an upload at once).
        """
        here = key(path)
        self.dropped.add(here)
        seen = dict(self.seen)                           # (a look in a worker thread may replace it)
        known = seen.pop(here, None)
        self.seen = seen
        if known is not None and known.bundle is not None:
            bid = known.bundle.id
        else:
            try:
                bid = self.load(path).id
            except BundleError:
                bid = next((bid for bid, b in self.bundles.items() if key(b.path) == here), None)
        if bid is None:
            return
        self.bundles.pop(bid, None)
        for folder, s in seen.items():                   # its other copies, as the record has them
            if folder not in self.dropped and s.bundle is not None and s.bundle.id == bid and os.path.isdir(folder):
                self._merge(s.bundle, self.owner(Path(folder)))

    def load(self, path: Path) -> Bundle:
        """load_bundle, judging the deck as this store does (plays) - called as before where it judges."""
        return load_bundle(path) if self.plays else load_bundle(path, plays=False)

    def owner(self, folder: Path) -> str | None:
        if self.published is None:
            return None
        here = key(folder)
        if not here.startswith(self.published + os.sep):
            return None
        parts = here[len(self.published) + 1:].split(os.sep)
        return parts[0] if len(parts) >= 2 else None

    def _seen_of(self, b: Bundle) -> Seen | None:
        """What the last look found in b's folder, if that is b's build still."""
        s = self.seen.get(key(b.path))
        return s if s is not None and s.bundle is not None and s.bundle.id == b.id else None

    def holds(self, b: Bundle) -> bool:
        """Whether b's folder holds its build still (holds), as the last look found it - read again where
        that look did not find the folder (a copy made since)."""
        s = self.seen.get(key(b.path))
        if s is None:
            return holds(b)
        return s.bundle is not None and s.bundle.id == b.id

    def complete(self, b: Bundle) -> bool:
        """Whether every file of b is there (Bundle.complete), as the last look found its folder."""
        s = self._seen_of(b)
        return s.complete if s is not None else b.complete()

    def _merge(self, b: Bundle, owner: str | None) -> Bundle:
        known = self.bundles.get(b.id)
        if known is None:
            known = copy.copy(b)                         # (its own: a look's record of the folder stays as it is)
            known.owners = None if owner is None else {owner}
            self.bundles[b.id] = known
            return known
        known.built = max(known.built, b.built)          # (built again unchanged - a change undone: the newest build)
        if owner is None:
            known.owners = None                          # (also) in a served folder: open
        elif known.owners is not None:
            known.owners.add(owner)                      # the same build, uploaded by another lecturer too
        if known.path != b.path and (not self.holds(known) or (not self.complete(known) and self.complete(b))):
            known.path = b.path                          # its folder holds another build now, or less
        return known

    def folders(self):
        """Every folder with a deck.json in the roots and the recorded build folders, each once."""
        given = set()
        for root in [*self.roots, *self.more()]:
            candidates = [root] if (root / "deck.json").exists() else \
                [p.parent for depth in ("*", "*/*", "*/*/*") for p in root.glob(f"{depth}/deck.json")]
            for folder in candidates:
                here = key(folder)
                if here not in self.dropped and here not in given:
                    given.add(here)
                    yield folder

    def collect(self) -> list[tuple[Path, str | None, Seen]]:
        """Every folder looked at: read again only where its files' stamp changed since the last look
        (Seen) - a folder that could not be read is read again at every look (a file held open a moment
        must not keep a deck off the list). It changes nothing that the server reads but `seen`, which it
        replaces whole: the server runs it in a worker thread (app.py: Server.rescan), and `apply` merges
        what it found. One look at a time."""
        with self.looking:
            return self._look()

    def _look(self) -> list[tuple[Path, str | None, Seen]]:
        """collect(), the lock held."""
        found, seen = [], {}
        for folder in self.folders():
            here = key(folder)
            now = stamp(folder)
            s = self.seen.get(here)
            owner = self.owner(folder)
            if s is None or now is None or s.stamp != now:
                try:
                    b = self.load(folder)
                    s = Seen(now, b, b.complete())
                except BundleError as err:
                    s = Seen(None, skipped=skipped_folder(folder, owner, err), error=str(err))
            seen[here] = s
            found.append((folder, owner, s))
        self.seen = seen                                 # (a folder gone is forgotten)
        return found

    def apply(self, found: list[tuple[Path, str | None, Seen]]):
        """Merges what a look found (collect) - the server does it on its event loop, where it reads the
        bundles. A folder dropped meanwhile stays out: the look may have read it before it went. A folder
        skipped that the last look had not skipped is said in the server's log (the first look's: texstage
        serve prints them)."""
        self.scanned = time.monotonic()
        gone = set(self.dropped)                         # (dropped while it was looked at: as dropped as before)
        self.dropped = {p for p in self.dropped if os.path.exists(p)}
        if gone & set(self.seen):
            self.seen = {k: v for k, v in self.seen.items() if k not in gone}
        problems, skipped = [], []
        for folder, owner, s in found:
            if key(folder) in gone:
                continue
            if s.bundle is None:
                problems.append(s.error or "")
                if s.skipped is not None:
                    skipped.append(s.skipped)
                continue
            self._merge(s.bundle, owner)
        self.problems, self.skipped = problems, skipped
        for problem in problems if self.told is not None else ():
            if problem not in self.told:
                log.warning("skipped: %s", problem)
        self.told = set(problems)

    def scan(self):
        """Every folder looked at again, here (collect, then apply)."""
        self.apply(self.collect())

    def current(self) -> list[Bundle]:
        """The bundles still on disk: a rebuilt deck replaces its build folder, and the old
        build stays known (a running game may play it) but is no longer offered."""
        return [b for b in self.bundles.values() if self.holds(b)]

    def add(self, path: Path) -> Bundle:
        """A bundle that has just arrived (texstage publish, a PPTX's join slide) - in the record at once, so
        that drop() finds it as a copy of its build."""
        b = self.load(path)
        here = key(path)
        self.dropped.discard(here)
        self.seen = {**self.seen, here: Seen(stamp(path), b, b.complete())}
        return self._merge(b, self.owner(path))

    def get(self, bid: str) -> Bundle | None:
        """The bundle of this ID - an unknown one looked for again, at most every RESCAN_S, but not while a
        look runs in a worker thread (its merge comes soon: no wait on the event loop)."""
        if bid not in self.bundles and time.monotonic() - self.scanned > self.RESCAN_S \
                and self.looking.acquire(blocking=False):
            try:
                found = self._look()
            finally:
                self.looking.release()
            self.apply(found)
        return self.bundles.get(bid)
