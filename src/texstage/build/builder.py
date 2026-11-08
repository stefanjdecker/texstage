# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage build: deck.tex -> PowerPoint file + quiz bundle (+ layout check).

    <out>/<name>.pptx          slide pictures and notes; add-in objects on live slides (no
                               bundle: the build hands the deck to its server, cli.deliver);
                               with live slides, a first slide before the deck's that prepares
                               them when the slideshow starts (first_slide)
    <out>/<name>-static.pptx   the same slides without add-in objects (no quiz server)
    <out>/<name>.bundle/       deck.json, keys.json, slides/, phone/   (see bundle.py)
                               with --stage also stage/: the stage PDF for texstage
    <out>/<name>.bundle.zip    the same as one file, to upload by hand (a server's deck list)
    <out>/build/               LaTeX output: <stem>-present.pdf, <stem>-solutions.pdf, logs
                               (with --stage also <stem>-stage.pdf)

<name> is the file name of the deck - for a course chapter's slides.tex, the chapter
folder's name. Steps (docs/design.md, section 4): compile in present mode with
second-screen notes (with --stage, alongside it the stage compile: stage.py); read the
.tqz; render the slide halves and the phone images; plan the PowerPoint slides with their
live boxes (a leaderboard slide after every scored quiz's reveal); write the bundle and the
PowerPoint file; check the quiz and answer frames in the present and solutions builds
(check.py). What is a content type's - the quiz's - its module does (types.py, quiz.py).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from texstage import DEFAULT_SERVER
from texstage.build import activity, quiz, video
from texstage.build import bundle as bnd
from texstage.build.check import Finding, check_log, locator, shipped_pages
from texstage.build.latex import compile_deck
from texstage.build.pdf import Pdf
from texstage.build.powerpoint import PptxDeck, origin
from texstage.keys import find_key
from texstage.build.raster import render_pages, render_slides
from texstage.build.stage import Stage, StageError, plan_stage
from texstage.build.tqz import Tqz
from texstage.build.types import TYPES, of_kind


class BuildError(RuntimeError):
    """The deck cannot be turned into a live deck (the message says why)."""


@dataclass
class BuildOptions:
    server: str = DEFAULT_SERVER
    key: str | None = None       # the server's presenter key (default: keys.find_key)
    deck_id: str | None = None
    height: int = 1080           # slide pictures, pixels
    check: bool = True
    max_shrink: float = 15.0
    passes: int = 2
    stage: bool = False          # also the stage PDF for texstage (stage.py)


@dataclass
class Slide:
    page: int                    # PDF page of the picture
    image: str                   # bundle path
    notes: str
    live: list[dict] = field(default_factory=list)   # its live boxes: {type, phase?, item?, rects?}

    # A live slide's quiz box (the quiz's phases: join read question reveal answer leaderboard podium)
    @property
    def phase(self) -> str | None:
        return next((b.get("phase") for b in self.live if b["type"] == quiz.NAME), None)

    @property
    def quiz(self) -> str | None:
        return next((b.get("item") for b in self.live if b["type"] == quiz.NAME), None)

    @property
    def rects(self) -> dict | None:
        return next((b.get("rects") for b in self.live if b["type"] == quiz.NAME), None)

    def boxes(self, uses_addin: bool) -> list[dict]:
        """Its boxes of the types that do (or do not) use PowerPoint's add-in."""
        return [b for b in self.live if TYPES[b["type"]].USES_ADDIN == uses_addin]


@dataclass
class BuildResult:
    pptx: Path
    static: Path                 # the same slides without the live add-in objects
    bundle: Path
    bundle_id: str
    deck_id: str
    slides: list[Slide]
    quizzes: int
    warnings: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    stage: Stage | None = None   # with --stage: the stage PDF, its pages and frames
    first: int | None = None     # the live PPTX's first slide (its ID), which prepares the live slides

    @property
    def zip(self) -> Path:
        """The bundle as one file, to upload by hand (bundle.write_zip)."""
        return self.bundle.with_name(self.bundle.name + ".zip")

    @property
    def problems(self) -> list[Finding]:
        return [f for f in self.findings if f.problem]


def deck_name(tex: Path) -> str:
    """slides.tex of a course chapter is named after its folder."""
    return tex.resolve().parent.name if tex.stem == "slides" else tex.stem


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def plan_slides(tqz: Tqz, pictures, warnings: list[str]) -> list[Slide]:
    """One slide per slide page with its live boxes, and the slides the types add (the
    quiz's leaderboards, quiz.plan). A page's items of a type this build does not know stop
    the build."""
    images = {p.page: bnd.content_name("slides", p.png) for p in pictures}
    notes = {p.page: p.notes for p in pictures}
    for page in tqz.pages.values():
        for item in page.items:
            if of_kind(item.kind) is None:
                raise BuildError(f"page {page.page}: an item of kind {item.kind!r}, which no content type of "
                                 f"this build knows - update texstage (the lecture's tools/)")
    try:
        planned = quiz.plan(tqz, list(images), warnings)
    except quiz.QuizError as err:
        raise BuildError(str(err)) from None
    slides = []
    for page, item, added in planned:
        live = [quiz.box(tqz, item)] if item is not None else []
        if not added:                                 # the page's items of the other types
            live += [of_kind(i.kind).box(tqz, i) for i in (tqz.pages[page].items if page in tqz.pages else [])
                     if i.kind not in quiz.KINDS]
        slides.append(Slide(page, images[page], "" if added else notes[page], live))
    return slides


FIRST_NOTES = ("Start the slideshow here, before the lecture: this slide prepares the quiz slides - PowerPoint "
               "starts each one's add-in once (a few seconds each; the projector shows \"Preparing the quiz "
               "slides\"). When it says ready, go on to the first slide.")


def first_slide(name: str, size: tuple[int, int]) -> bytes:
    """The live PPTX's first slide as PowerPoint shows it until its add-in has started (and in
    the editing view): what it is for. Its add-in then shows how far the preparing is."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    im = Image.new("RGB", size, (30, 15, 60))                 # the add-in's "Preparing" colours
    draw = ImageDraw.Draw(im)

    def line(y: float, text: str, px: float, fill):
        px = round(px)
        while True:                                            # a long deck name: smaller
            font = ImageFont.load_default(size=px)
            x0, _, x1, _ = draw.textbbox((0, 0), text, font=font)
            if x1 - x0 <= 0.9 * w or px <= 12:
                break
            px = round(px * 0.9)
        draw.text(((w - (x1 - x0)) / 2 - x0, y), text, font=font, fill=fill)

    line(0.27 * h, "texstage", 0.045 * h, (199, 179, 245))
    line(0.36 * h, name, 0.085 * h, (255, 255, 255))
    line(0.57 * h, "Start the slideshow here: this slide prepares the quiz slides.", 0.037 * h, (255, 255, 255))
    line(0.64 * h, "When it says ready, go on to the first slide.", 0.037 * h, (199, 179, 245))
    out = BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def build(tex: Path, out_dir: Path, opts: BuildOptions | None = None) -> BuildResult:
    opts = opts or BuildOptions()
    try:
        server = origin(opts.server)             # the add-in the live slides reference (powerpoint.py)
    except ValueError as err:
        raise BuildError(str(err)) from None
    tex = tex.resolve()
    out_dir = out_dir.resolve()
    name = deck_name(tex)
    deck_id = opts.deck_id or slug(name)
    work = out_dir / "build"
    present, staged = compile_present(tex, work, opts)
    tqz = Tqz.read(present.tqz)
    with Pdf(present.pdf) as doc:
        total = len(doc)
    count = total - len(tqz.assets)
    marked = shipped_pages(present.log)
    if marked == 0 and count > 0:
        raise BuildError("the log has no texquiz page marks: the deck loads an older texquiz.sty "
                         "than this builder - update the lecture's tools/ (git submodule update "
                         "--remote tools) or build with the texstage of the lecture's tools/")
    if count < 1 or marked != count:
        raise BuildError(f"{present.pdf.name}: {total} pages, {len(tqz.assets)} phone images and "
                         f"{marked} slide pages in the log - they do not add up")
    stage, stage_pdf = None, b""
    if staged is not None:
        try:
            stage, stage_pdf = plan_stage(staged, present.log.with_suffix(".nav"), tqz, count)
        except StageError as err:
            raise BuildError(f"{staged.pdf.name}: {err}") from None
    pictures = render_slides(present.pdf, count, tqz.paper, opts.height)
    phone, phone_files = quiz.files(tqz, render_pages(present.pdf, range(count + 1, total + 1)))
    warnings: list[str] = []
    slides = plan_slides(tqz, pictures, warnings)
    for s in slides:
        if s.boxes(uses_addin=True) and s.boxes(uses_addin=False):
            raise BuildError(f"page {s.page}: a quiz and a {s.boxes(uses_addin=False)[0]['type']} on one slide - "
                             f"the quiz's add-in covers the whole slide in PowerPoint; give each a frame of its own")
    try:
        videos, video_files, media = video.entries(tqz, tex.parent, warnings)
        activity.check_slides(slides)
        activities, activity_keys, activity_files = activity.entries(tqz, tex.parent, phone, warnings)
    except (video.VideoError, activity.ActivityError) as err:
        raise BuildError(str(err)) from None

    ppt = PptxDeck(tqz.paper, server)
    pngs = {p.page: p.png for p in pictures}
    question = quiz.question_pages(tqz)                # an answer slide keeps its question's picture
    stored = [pngs[next((quiz.stored(b, s.page, question) for b in s.live if b["type"] == quiz.NAME), s.page)]
              for s in slides]
    size = (round(opts.height * tqz.paper[0] / tqz.paper[1]), opts.height)
    addin_slides = any(s.boxes(uses_addin=True) for s in slides)
    first = ppt.add_slide(first_slide(name, size), FIRST_NOTES) if addin_slides else None
    ids = [ppt.add_slide(png, s.notes) for png, s in zip(stored, slides)]
    public, private = quiz.entries(tqz, phone)
    items, secret = ({quiz.NAME: public}, {quiz.NAME: private}) if public else ({}, {})
    if videos:
        items[video.NAME] = videos
    if activities:
        items[activity.NAME] = activities
    if activity_keys:
        secret[activity.NAME] = activity_keys
    used = sorted({b["type"] for s in slides for b in s.live} | set(items))
    language = bnd.language_tag(tqz.language)           # what the live views speak (English without it)
    deck = {"format": bnd.FORMAT, "deck": deck_id, "name": name, **({"language": language} if language else {}),
            "types": used, "image": {"width": size[0], "height": size[1]},
            "slides": [], "items": items}
    keys = {"format": bnd.FORMAT, "deck": deck_id, "items": secret}
    for s, sid in zip(slides, ids):
        entry = {"id": sid, "image": s.image}
        if s.live:
            entry["live"] = s.live
        if stage is not None:
            entry |= stage.entry(s.page, s.notes)
        deck["slides"].append(entry)
    if stage is not None:
        deck["pdf"] = stage.deck_entry()
    bid = bnd.bundle_id(deck, keys)
    deck["bundle"] = keys["bundle"] = bid
    files = {s.image: pngs[s.page] for s in slides} | phone_files | video_files | activity_files
    if stage is not None:
        files[stage.file] = stage_pdf
    bundle_dir = out_dir / f"{name}.bundle"
    bnd.write_bundle(bundle_dir, deck, keys, files)
    bnd.write_zip(out_dir / f"{name}.bundle.zip", deck, keys, files)      # to upload by hand

    # The PowerPoint file carries no bundle: every deck reaches its server through its build
    # (texstage build: recorded for this machine's quiz server, uploaded to any other one -
    # cli.deliver). Until 2026-10-09 the join slide's add-in carried it, but PowerPoint keeps
    # at most 2 MB for an add-in - too little for a lecture's chapter (bundle.carried).
    # Every live slide carries the server's presenter key: the slides pair by themselves,
    # nothing to type in the lecture hall. (The PPTX is the lecturer's file - its reveal
    # slides hold the answers anyway.)
    key = opts.key or find_key(server)
    if addin_slides and not key:
        warnings.append(f"no presenter key for {server}: the live slides will ask for it once - "
                        f"give it with --key (texstage publish --url {server} --key K --remember keeps it)")
    shift = 0 if first is None else 1                   # the deck's slides come after the first one
    for i, (s, sid) in enumerate(zip(slides, ids)):
        for b in s.boxes(uses_addin=True)[:1]:          # one add-in object over the whole slide
            part, label = TYPES[b["type"]].addin(b)
            props = {"server": server, "deck": deck_id, "bundle": bid, **part, "slideId": sid}
            if key:
                props["key"] = key
            ppt.add_addin(i + shift, props, label)
    if first is not None:
        # The first slide prepares the live slides when the slideshow starts there, before the
        # lecture (the join slide did it until 2026-10-10; it still does what is left when the
        # slideshow starts later). Not in deck.json: it is PowerPoint's alone - the server takes
        # its ID as an ordinary slide's.
        props = {"server": server, "deck": deck_id, "bundle": bid, "quiz": None, "phase": "prepare", "slideId": first}
        if key:
            props["key"] = key
        ppt.add_addin(0, props, "texstage prepare")
    # The same slides without add-in objects: for presenting without a quiz server. A live
    # slide whose add-in cannot load shows PowerPoint's error bar, or nothing at all on a PC
    # where the add-in is not registered (M6).
    static = PptxDeck(tqz.paper, server)
    for s in slides:
        static.add_slide(pngs[s.page], s.notes)
    # The types with native objects (a video) put them into both decks: they need no add-in. (An
    # activity has none: the slide picture shows its static form.)
    for i, s in enumerate(slides):
        for b in s.boxes(uses_addin=False):
            if b["type"] != video.NAME:
                continue
            for deck_file, index in ((ppt, i + shift), (static, i)):
                video.pptx(deck_file, index, b, media[b["item"]])
    pptx, static_pptx = out_dir / f"{name}.pptx", out_dir / f"{name}-static.pptx"
    for deck_file, path in ((ppt, pptx), (static, static_pptx)):
        try:
            deck_file.save(path)
        except PermissionError:
            raise BuildError(f"{path} is locked - probably open in PowerPoint; close it and build again")

    result = BuildResult(pptx, static_pptx, bundle_dir, bid, deck_id, slides, len(tqz.questions), warnings,
                         stage=stage, first=first)
    if opts.check:
        result.findings = check(tex, present, pictures, work, opts, stage)
    return result


def compile_present(tex: Path, work: Path, opts: BuildOptions):
    """The present compile, and with --stage the stage compile alongside it: two pdflatex
    runs side by side, each with its own job name (stage.py)."""
    if not opts.stage:
        return compile_deck(tex, "present", work, notes=True, passes=opts.passes), None
    with ThreadPoolExecutor(max_workers=2) as pool:
        present = pool.submit(compile_deck, tex, "present", work, notes=True, passes=opts.passes)
        staged = pool.submit(compile_deck, tex, "present", work, notes="stage", jobname=f"{tex.stem}-stage",
                             passes=opts.passes)
        return present.result(), staged.result()


def check(tex: Path, present, pictures, work: Path, opts: BuildOptions,
          stage: Stage | None = None) -> list[Finding]:
    """The quiz and answer frames in the present build (just made) and the solutions build,
    and notes that do not fit their page (they would be cut off in the PowerPoint notes, or
    on the stage PDF's note pages)."""
    where = locator(tex, present.log.with_suffix(".nav"))
    findings = check_log(present.log, "present", where, opts.max_shrink)
    log = present.log.read_text(encoding="latin-1", errors="replace")
    if quiz.solutions(log):
        solutions = compile_deck(tex, "solutions", work, passes=opts.passes)
        where_s = locator(tex, solutions.log.with_suffix(".nav"))
        findings += check_log(solutions.log, "solutions", where_s, opts.max_shrink)
    for p in pictures:
        if p.notes_cut_off:
            findings.append(Finding(where(p.page), "notes", "present", "the note fills its page - "
                                    "its end is cut off in the PowerPoint notes; shorten it", True))
    for page in stage.cut_off if stage is not None else []:
        findings.append(Finding(where(page), "notes", "stage", "the note runs down to the bottom of its "
                                "note page - its end is cut off in texstage's presenter view; shorten it", True))
    return findings
