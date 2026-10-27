# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The video (texvideo) in the build (docs/content-types-design.md, section 7; the registry:
types.py).

    records   video|id|src|poster|start|end|loop|muted|autoplay|link|tex file|line
              (texvideo.sty; paths and addresses hex-encoded, paths the deck's)
    box       a slide's live box: {type: video, item, rects: {box}}
    entries   deck.json's items.video - {id: {media | src, player, poster, start, end, loop,
              muted, autoplay, link}}: a local file as media/<hash>.<ext> in the bundle, an
              online one by its address, with how texstage plays it (`player`: YouTube's or
              Vimeo's player, or a <video> for an address of a file); nothing for keys.json
    files     the local video files and every poster, content-addressed in media/
    pptx      a native video at the box (python-pptx add_movie), in the live and in the static
              deck - a video needs no add-in and no server; an online one: its poster, with a
              click that opens it
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from texstage.build.bundle import content_name, public_rects
from texstage.build.tqz import Item, Tqz, _hex

NAME = "video"
KINDS = {"video"}
USES_ADDIN = False
MEDIA = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
POSTERS = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png"}
LARGE = 100 * 2**20        # a video this large makes the bundle, its zip and both PPTX files heavy
YOUTUBE = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|embed/|shorts/|live/)"
                     r"|youtu\.be/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
VIMEO = re.compile(r"^https?://(?:www\.|player\.)?vimeo\.com/(?:video/|channels/[^/?#]+/|groups/[^/?#]+/videos/)?"
                   r"(\d+)(?:/([0-9a-f]+))?/?(?:[?#]|$)")
FILE_URL = re.compile(r"^https?://[^?#]+\.(?:mp4|m4v|webm|mov)(?:[?#]|$)", re.IGNORECASE)


class VideoError(ValueError):
    """A deck's videos cannot be built (the message says why)."""


@dataclass
class Video:
    id: str
    src: str               # the file, as the deck names it, or the address of an online video
    poster: str
    start: float | None
    end: float | None
    loop: bool
    muted: bool
    autoplay: bool
    link: str              # url=: an online copy, for the handout
    file: str              # the .tex file and line it is in
    line: int

    @property
    def online(self) -> bool:
        return "://" in self.src


def player(src: str) -> dict | None:
    """How texstage plays an online video: {"youtube": id}, {"vimeo": id} (with "hash": an
    unlisted one's), {"file": address} (a <video>, as for a local file); None: not at all - its
    poster stays."""
    if m := YOUTUBE.match(src):
        return {"youtube": m[1]}
    if m := VIMEO.match(src):
        found = {"vimeo": m[1]}
        unlisted = m[2] or (parse_qs(urlsplit(src).query).get("h") or [None])[0]
        if unlisted and re.fullmatch(r"[0-9a-f]+", unlisted):
            found["hash"] = unlisted
        return found
    if FILE_URL.match(src):
        return {"file": src}
    return None


def read(tqz: Tqz) -> dict[str, Video]:
    found = {}
    for f in tqz.records.get(NAME, []):
        seconds = [float(x) if x else None for x in f[3:5]]
        found[f[0]] = Video(f[0], _hex(f[1]), _hex(f[2]), *seconds, f[5] == "true", f[6] == "true", f[7] == "true",
                            _hex(f[8]), _hex(f[9]), int(f[10]))
    return found


def box(tqz: Tqz, item: Item) -> dict:
    return {"type": NAME, "item": item.id, "rects": public_rects(item.rects, {}, tqz.paper)}


def entries(tqz: Tqz, folder: Path, warnings: list[str]) -> tuple[dict, dict[str, bytes], dict[str, dict]]:
    """deck.json's items.video, the files, and per video what PowerPoint needs ({movie, mime,
    poster} or {url, poster}). Paths are the deck's: relative to its folder."""
    items: dict[str, dict] = {}
    files: dict[str, bytes] = {}
    pptx: dict[str, dict] = {}
    for v in read(tqz).values():
        poster_path = folder / v.poster
        suffix = POSTERS.get(poster_path.suffix.lower())
        if suffix is None or not poster_path.is_file():
            raise VideoError(f"video {v.id}: the poster {v.poster} is not there, or not a JPEG or PNG picture")
        poster = poster_path.read_bytes()
        entry: dict = {"poster": content_name("media", poster, suffix)}
        files[entry["poster"]] = poster
        if v.online:
            entry["src"] = v.src
            how = player(v.src)
            if how is None:
                warnings.append(f"video {v.id}: texstage plays YouTube's, Vimeo's and addresses of MP4 or WebM "
                                f"files - for {v.src} its poster stays (the handout and PowerPoint link it)")
            else:
                entry["player"] = how
            pptx[v.id] = {"url": v.src, "poster": poster}
        else:
            path = folder / v.src
            mime = MEDIA.get(path.suffix.lower())
            if mime is None:
                raise VideoError(f"video {v.id}: {v.src} - texstage plays MP4 (H.264, AAC) and WebM files")
            if mime != "video/mp4":
                warnings.append(f"video {v.id}: {v.src} plays in the browser, but PowerPoint wants MP4 (H.264, AAC)")
            data = path.read_bytes()
            if len(data) > LARGE:
                warnings.append(f"video {v.id}: {len(data) // 2**20} MB - the bundle, its zip and both PPTX files carry "
                                f"it; an upload to a hosted server takes 200 MB at most")
            entry["media"] = content_name("media", data, path.suffix.lower())
            files[entry["media"]] = data
            pptx[v.id] = {"movie": data, "mime": mime, "poster": poster}
        for key in ("start", "end"):
            if getattr(v, key) is not None:
                entry[key] = getattr(v, key)
        for key in ("loop", "muted", "autoplay"):
            if getattr(v, key):
                entry[key] = True
        if v.link:
            entry["link"] = v.link
        items[v.id] = entry
    return items, files, pptx


def pptx(deck, index: int, box: dict, media: dict):
    """The video of `box` on slide `index` of a PowerPoint deck (live or static)."""
    rect, name = box["rects"]["box"], f"texstage video {box['item']}"
    if "url" in media:
        deck.add_link(index, rect, media["poster"], media["url"], name)
    else:
        deck.add_movie(index, rect, media["movie"], media["mime"], media["poster"], name)
