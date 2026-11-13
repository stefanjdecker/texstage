# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Quiz bundles on the server: loading, checking, finding them by ID.

A bundle is the folder `texstage build` writes (<name>.bundle/: deck.json, keys.json,
slides/, phone/, with --stage stage/; see texstage/build/bundle.py). The server never changes it. Bundles are
found in the folders given to `texstage serve`: a folder is a bundle itself, or holds
bundles (searched three levels deep, e.g. a lecture chapter's build/texquiz/), and in the
data folder: bundles/<lecturer>/<deck>/<id>/ (uploads, the lecturer's) and served/<deck>/<id>/
(copies of served decks being played). An unknown bundle ID makes the store look again, so
a rebuilt deck is picked up without a restart.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from texstage.build.bundle import LANGUAGES, READS, bundle_id
from texstage.server import types as stage_types

FILE = re.compile(r"^((slides|phone)/[0-9a-f]{16}\.png|media/[0-9a-f]{16}\.(jpg|png))$")   # pictures, posters
STAGE_PDF = re.compile(r"^stage/[0-9a-f]{16}\.pdf$")
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
    built: int = 0                       # when it was built (ms): its deck.json's time - an upload and a
    #                                      served copy keep the build's (app.py); the newest of its copies

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


def load_bundle(path: Path) -> Bundle:
    try:
        with (path / "deck.json").open(encoding="utf-8") as f:
            deck = json.loads(f.read())
            built = int(os.fstat(f.fileno()).st_mtime * 1000)     # (the file read: a rebuild may replace the folder)
        keys = json.loads((path / "keys.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise BundleError(f"{path}: {err}") from None
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
        why = stage_types.refuses(deck)                  # (the core's type: a kind this server lacks)
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


class BundleStore:
    RESCAN_S = 2.0           # an unknown ID rescans the folders at most this often

    def __init__(self, roots: list[Path], published: Path | None = None, more=None):
        """published: the folder of uploaded bundles, <lecturer>/<deck>/<bundle id>/ - they
        belong to their lecturer; the bundles in the other folders are open to every lecturer.
        more: further folders, asked at every scan (the builds of this machine, builds.py)."""
        self.roots = [Path(r) for r in roots]
        self.more = more or (lambda: [])
        self.published = published.resolve() if published else None
        self.bundles: dict[str, Bundle] = {}
        self.dropped: set[Path] = set()    # a cleanup can still be removing files asynchronously
        self.problems: list[str] = []
        self.scanned = 0.0
        self.scan()

    def drop(self, path: Path):
        """Forget this copy, preserving other lecturers' copies of the same build.

        Called before removing the folder. Scans must not rediscover it during that
        removal; a later explicit upload (add) makes the path available again.
        """
        path = path.resolve()
        self.dropped.add(path)
        try:
            bid = load_bundle(path).id
        except BundleError:
            bid = next((bid for bid, b in self.bundles.items() if b.path.resolve() == path), None)
        if bid is None:
            return
        self.bundles.pop(bid, None)
        for folder in self.folders():
            try:
                b = load_bundle(folder)
            except BundleError:
                continue
            if b.id == bid:
                self._merge(b, self.owner(folder))

    def owner(self, folder: Path) -> str | None:
        if self.published is None:
            return None
        try:
            rel = folder.resolve().relative_to(self.published)
        except ValueError:
            return None
        return rel.parts[0] if len(rel.parts) >= 2 else None

    def _merge(self, b: Bundle, owner: str | None) -> Bundle:
        known = self.bundles.get(b.id)
        if known is None:
            b.owners = None if owner is None else {owner}
            self.bundles[b.id] = b
            return b
        known.built = max(known.built, b.built)          # (built again unchanged - a change undone: the newest build)
        if owner is None:
            known.owners = None                          # (also) in a served folder: open
        elif known.owners is not None:
            known.owners.add(owner)                      # the same build, uploaded by another lecturer too
        if not holds(known) or (not known.complete() and b.complete()):
            known.path = b.path                          # its folder holds another build now, or less
        return known

    def folders(self):
        for root in [*self.roots, *self.more()]:
            candidates = [root] if (root / "deck.json").exists() else \
                [p.parent for depth in ("*", "*/*", "*/*/*") for p in root.glob(f"{depth}/deck.json")]
            for folder in candidates:
                if folder.resolve() not in self.dropped:
                    yield folder

    def scan(self):
        self.scanned = time.monotonic()
        self.problems = []
        self.dropped = {p for p in self.dropped if p.exists()}
        for folder in self.folders():
            try:
                b = load_bundle(folder)
            except BundleError as err:
                self.problems.append(str(err))
                continue
            self._merge(b, self.owner(folder))

    def current(self) -> list[Bundle]:
        """The bundles still on disk: a rebuilt deck replaces its build folder, and the old
        build stays known (a running game may play it) but is no longer offered."""
        return [b for b in self.bundles.values() if holds(b)]

    def add(self, path: Path) -> Bundle:
        """A bundle that has just arrived (texstage publish, a PPTX's join slide)."""
        b = load_bundle(path)
        self.dropped.discard(path.resolve())
        return self._merge(b, self.owner(path))

    def get(self, bid: str) -> Bundle | None:
        if bid not in self.bundles and time.monotonic() - self.scanned > self.RESCAN_S:
            self.scan()
        return self.bundles.get(bid)
