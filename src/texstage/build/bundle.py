# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The bundle for the server: deck.json (public), keys.json (private), files.

    <name>.bundle/
      deck.json      format 2 (since 2026-10-10): "types", the content types the deck uses;
                     "items", per type its items as the phones may see them (the quiz's: no
                     correctness, no explanations, no keys); "slides": PowerPoint slide ID,
                     picture and live boxes ({type, phase?, item?, rects?}) of every slide,
                     for the host views only (reveal slides show the answers, by nature);
                     "language" (since 2026-10-24), the deck's as a BCP 47 tag - de, en
                     (language_tag) -, the language the live views on the slides speak
      keys.json      "items", per type what only the host gets (the quiz's correct answers,
                     accepted texts, numeric answers, explanations, LaTeX sources)
      slides/        slide pictures, phone/  the quiz's phone images (PNG, named by content hash)
      stage/         the stage PDF for texstage (stage.py; named by content hash too, and
                     listed in deck.json under "pdf"); deck.json's slides then also have their
                     frame and overlay step, their pages in the stage PDF ("page", "note") and
                     their note text ("notes"). Not with --no-stage.
    <name>.bundle.zip  the same as one file, to upload by hand (write_zip)

Format 1 (until 2026-10-10) had the quiz's items as "quizzes" and a slide's quiz box as its
"phase", "quiz" and "rects"; the server reads both (server/bundles.py). The bundle ID is a
hash of both JSON files; the files are covered through their content-hashed names.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from texstage.build.tqz import Rect

FORMAT = 2                     # what the build writes
READS = (1, 2)                 # what a server reads


def content_name(folder: str, data: bytes, suffix: str = ".png") -> str:
    return f"{folder}/{hashlib.sha256(data).hexdigest()[:16]}{suffix}"


def public_rects(rects: dict[str, Rect], ids: dict[str, str], paper: tuple[float, float]) -> dict:
    """Rectangles as fractions of the slide, measured from the top left corner; those named
    in `ids` (the quiz's answer boxes) under 'cells', by public id."""
    w, h = paper

    def frac(r: Rect) -> dict:
        return {"x": round(r.x / w, 5), "y": round((h - r.y - r.h) / h, 5),
                "w": round(r.w / w, 5), "h": round(r.h / h, 5)}
    out: dict = {}
    cells = {ids[key]: frac(r) for key, r in rects.items() if key in ids}
    if cells:
        out["cells"] = dict(sorted(cells.items()))
    out |= {key: frac(r) for key, r in sorted(rects.items()) if key not in ids}
    return out


# babel's (and polyglossia's) names of the languages the live views speak (web/shared/live.js,
# web/stage/activity.js) - English too, the one they speak for any other
LANGUAGES = {
    "de": ("german", "ngerman", "germanb", "ngermanb", "austrian", "naustrian", "swissgerman", "nswissgerman"),
    "en": ("english", "american", "usenglish", "british", "ukenglish", "canadian", "australian", "newzealand"),
}


def language_tag(name: str) -> str | None:
    """deck.json's "language": the BCP 47 tag of the deck's language, which the .tqz names as babel
    does (\\languagename: ngerman -> de, english -> en; a name babel takes as a tag, de-AT -> de, or
    with its region, german-austria -> de). None for one the live views do not speak - they speak
    English then, as for a deck built before 2026-10-24."""
    name = name.strip().lower()
    for tag, names in LANGUAGES.items():
        if name == tag or name.startswith(f"{tag}-") or name.split("-")[0] in names:
            return tag
    return None


def bundle_id(deck: dict, keys: dict) -> str:
    blob = json.dumps({"deck": deck, "keys": keys}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def write_bundle(folder: Path, deck: dict, keys: dict, files: dict[str, bytes]):
    """Write the bundle afresh. The folder is generated output; anything else there is
    refused rather than deleted."""
    if folder.exists():
        if any(folder.iterdir()) and not (folder / "deck.json").exists():
            raise FileExistsError(f"{folder} exists and is not a texstage bundle - not overwriting it")
        shutil.rmtree(folder)
    for sub in ("slides", "phone"):
        (folder / sub).mkdir(parents=True)
    for name, data in files.items():
        (folder / name).parent.mkdir(exist_ok=True)              # stage/: the stage PDF
        (folder / name).write_bytes(data)
    for name, data in (("deck.json", deck), ("keys.json", keys)):
        (folder / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def write_zip(path: Path, deck: dict, keys: dict, files: dict[str, bytes]):
    """The whole bundle as one file, <name>.bundle.zip next to the PowerPoint file: what a
    server takes as it is - the deck lists of texstage and of the host page upload it by hand
    (POST /api/bundles), `texstage publish` sends the same."""
    import zipfile
    tmp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        for name, data in (("deck.json", deck), ("keys.json", keys)):
            z.writestr(name, json.dumps(data, indent=1, ensure_ascii=False) + "\n", compress_type=zipfile.ZIP_DEFLATED)
        for name in sorted(files):                                 # PNGs are packed already
            z.writestr(name, files[name], compress_type=zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED)
    tmp.replace(path)


def carried(deck: dict, keys: dict, files: dict[str, bytes]) -> bytes:
    """The bundle the PowerPoint files built before 2026-10-09 carry on their join slide
    (docs/design.md, section 4): a zip of both JSON files, the phone images and the pictures of
    the live slides - what a server needs for presenting in PowerPoint. Their add-in uploads it
    to a server that does not have the bundle, and the server still takes it (marked
    incomplete). New builds carry none: the build hands the deck over (cli.deliver)."""
    import io
    import zipfile
    live = {s["image"] for s in deck["slides"] if s.get("phase") or s.get("live")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in (("deck.json", deck), ("keys.json", keys)):
            z.writestr(name, json.dumps(data, indent=1, ensure_ascii=False) + "\n", compress_type=zipfile.ZIP_DEFLATED)
        for name in sorted(files):
            if name.startswith("phone/") or name in live:
                z.writestr(name, files[name], compress_type=zipfile.ZIP_STORED)      # PNGs are packed
    return buf.getvalue()
