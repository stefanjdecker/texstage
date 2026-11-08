# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The lecture archive (texstage, docs/texstage-design.md, sections 9, 11, 19 to 21): per game
a folder

    <data>/archive/<deck>/<date>-<pin>/   annotated.pdf, <deck>-<date>-<pin>.csv (the results),
                                          polls.csv, questions.csv (the audience's),
                                          sketch-<question>-<n>.svg, recording-<take>.webm (or .mp4)

with what the lecture left. A recording - a take - comes from the presenter window in parts
while it is made (MediaRecorder hands one out every 10 s) and stays in the folder of the game
it started in, also when the lecture goes on with a new game or another deck. It grows in
recording-<take>.<ext>.part, and recording-<take>.json knows whose it is and how far it got:
a part sent twice is taken once, one that comes too early is refused, one the server was
writing when it stopped is written again, and a restarted server goes on where it was. When
the recording stops it becomes recording-<take>.<ext>, then remuxed by ffmpeg if installed
(in the background): MediaRecorder's WebM has no duration and no seek index, which players
then have to guess.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from texstage.server import types as stage_types

log = logging.getLogger("texstage.server")
TAKE = re.compile(r"^[0-9a-f]{12}$")
EXTS = ("webm", "mp4")
FILE = re.compile(r"^(annotated\.pdf|[a-z0-9-]+\.csv|sketch-[a-z0-9-]+-[0-9]+\.svg"
                  r"|recording-([0-9a-f]{12})\.(?:webm|mp4)"
                  + "".join(f"|{p}" for p in stage_types.ARCHIVE) + r")$")    # (the content types' files)
PENS = ("#1d1d1f", "#e21b3c", "#1368ce", "#26890c")      # a sketch's colours (web/shared/sketch.js)
PART_MAX = 64 * 1024 * 1024             # a part: 10 s of video, a few MB
RECORDING_MAX = 16 * 1024 ** 3          # a take: hours of video
REMUX_S = 3600                          # ffmpeg copies, it does not encode: minutes at most


class ArchiveError(ValueError):
    """What the archive does not take; status: the HTTP status to answer with, code: the window's
    (web/i18n: errors) - a recording too large, or a part it does not take."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
        self.code = "recording-too-large" if status == 413 else "recording-part"


def folder(data_dir: Path, s, make: bool = True) -> Path:
    """A game's folder in the archive (made if need be)."""
    day = time.strftime("%Y-%m-%d", time.localtime(s.created / 1000))
    deck = re.sub(r"[^a-z0-9-]+", "-", s.deck.lower()) or "deck"
    path = data_dir / "archive" / deck / f"{day}-{s.pin}"
    if make:
        path.mkdir(parents=True, exist_ok=True)
    return path


def sketch_svg(strokes: list) -> str:
    """A sketch (scoring.py: strokes on a 1000 x 750 canvas) as an SVG picture."""
    lines = []
    for s in strokes:
        p = s["p"] if len(s["p"]) > 2 else s["p"] * 2          # a dot: a line of no length
        points = " ".join(f"{p[i]},{p[i + 1]}" for i in range(0, len(p), 2))
        lines.append(f'<polyline points="{points}" stroke="{PENS[s.get("c", 0)]}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 750" width="1000" height="750">'
            '<rect width="1000" height="750" fill="#fff"/><g fill="none" stroke-width="8" stroke-linecap="round" '
            f'stroke-linejoin="round">{"".join(lines)}</g></svg>\n')


def files(path: Path) -> list[dict]:
    """What a game's folder holds: {name, size}, a recording with its take - unfinished while
    it is recorded (or if it never was finished)."""
    out = []
    for p in sorted(path.iterdir()) if path.is_dir() else []:
        name = p.name[:-5] if p.name.endswith(".part") else p.name
        m = FILE.match(name)
        if m is None or not p.is_file():
            continue
        entry = {"name": name, "size": p.stat().st_size}
        if m.group(2):
            entry["take"] = m.group(2)
            if name != p.name:
                entry["unfinished"] = True
        out.append(entry)
    return out


@dataclass
class Take:
    """A recording (texstage, M5) and how far it got."""
    id: str
    owner: str
    ext: str
    started: int
    parts: int = 0                      # the parts written
    size: int = 0                       # their bytes
    finished: int | None = None
    folder: Path = field(default=Path("."), compare=False)    # where its files are (not saved)

    @property
    def file(self) -> Path:
        return self.folder / f"recording-{self.id}.{self.ext}"

    @property
    def growing(self) -> Path:
        return self.folder / f"recording-{self.id}.{self.ext}.part"

    @property
    def meta(self) -> Path:
        return self.folder / f"recording-{self.id}.json"

    def save(self):
        data = {k: v for k, v in asdict(self).items() if k != "folder"}
        tmp = self.folder / f"recording-{self.id}.json.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(self.meta)

    def download_name(self) -> str:
        """What a download is called: <deck>-<date>-<time it started>.<ext>."""
        return f"{self.folder.parent.name}-{time.strftime('%Y-%m-%d-%H%M', time.localtime(self.started / 1000))}.{self.ext}"


class Recordings:
    """The takes by their id - also those a restarted server finds in the archive."""

    def __init__(self, root: Path):
        self.root = root                                # <data>/archive
        self.takes: dict[str, Take] = {}
        self.remuxing: dict[str, threading.Thread] = {}

    def start(self, path: Path, owner: str, ext, now: int) -> Take:
        if ext not in EXTS:
            raise ArchiveError("a recording is WebM or MP4")
        t = Take(secrets.token_hex(6), owner, ext, now, folder=path)
        t.save()
        self.takes[t.id] = t
        return t

    def get(self, take, owner: str) -> Take | None:
        """The take - to its owner only (anyone else learns nothing, not even that it exists)."""
        if not isinstance(take, str) or not TAKE.match(take):
            return None
        t = self.takes.get(take)
        if t is None:
            for meta in self.root.glob(f"*/*/recording-{take}.json"):
                try:
                    t = Take(**json.loads(meta.read_text(encoding="utf-8")), folder=meta.parent)
                except (OSError, ValueError, TypeError):
                    continue
                self.takes[take] = t
                break
        return t if t is not None and t.owner == owner else None

    def add(self, t: Take, part: int, data: bytes) -> int:
        """Part `part` (from 0) of a take; the number of the part that comes next."""
        if t.finished is not None:
            raise ArchiveError("this recording is finished", 409)
        if part < t.parts:
            return t.parts                              # sent again (its answer got lost): taken once
        if part > t.parts:
            raise ArchiveError(f"part {part} came before part {t.parts}", 409)
        if len(data) > PART_MAX or t.size + len(data) > RECORDING_MAX:
            raise ArchiveError("the recording is too large", 413)
        with t.growing.open("r+b" if t.growing.exists() else "wb") as f:
            f.truncate(t.size)                          # what a stopped server wrote of a part it did not count
            f.seek(t.size)
            f.write(data)
        t.parts, t.size = t.parts + 1, t.size + len(data)
        t.save()
        return t.parts

    def finish(self, t: Take, now: int) -> Path | None:
        """The take's file once the recording stopped (again: the same) - None if nothing was
        recorded -, remuxed in the background when ffmpeg is installed."""
        if t.finished is None:
            if t.parts == 0:
                t.meta.unlink(missing_ok=True)
                t.growing.unlink(missing_ok=True)
                self.takes.pop(t.id, None)
                return None
            with t.growing.open("r+b") as f:
                f.truncate(t.size)
            t.growing.replace(t.file)
            t.finished = now
            t.save()
            if shutil.which("ffmpeg"):
                job = threading.Thread(target=self._remux, args=(t,), name=f"remux-{t.id}")
                self.remuxing[t.id] = job
                job.start()
        return t.file

    def _remux(self, t: Take):
        try:
            ok = remux(t.file)
            log.info("recording %s: %s", t.file, "remuxed" if ok else "ffmpeg failed, kept as recorded")
        finally:
            self.remuxing.pop(t.id, None)


def remux(file: Path) -> bool:
    """The file copied once through ffmpeg - no new encoding - for its duration and seek index."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    tmp = file.with_name(f"remux-{file.name}")
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(file), "-map", "0", "-c", "copy"]
    if file.suffix == ".mp4":
        args += ["-movflags", "+faststart"]
    try:
        r = subprocess.run([*args, str(tmp)], capture_output=True, timeout=REMUX_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))     # Windows: no console
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            return False
        tmp.replace(file)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        tmp.unlink(missing_ok=True)
