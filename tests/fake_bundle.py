# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Synthetic quiz bundles for the server tests: deck.json and keys.json as `texstage build`
writes them (format, fields, bundle ID), made without LaTeX.

The deck: an ordinary slide, the join slide, then per quiz its reading slide (the
question alone), its question slide, its reveal slide (reveal=slide) or a later answer
slide (reveal=none), a leaderboard slide after scored quizzes, the podium and a last
ordinary slide. Slide IDs count from 256 as in PowerPoint; slide(phase, quiz) finds one.
stage=True: a --stage build's stand-in for the stage PDF (stage/, "pdf" in deck.json).
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from texstage.build.bundle import bundle_id

FORMAT = 1          # a bundle as builds wrote it until 2026-10-10: the server reads it still


def png(colour: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 9), colour).save(buf, "PNG")
    return buf.getvalue()


# id: (type, public extras, keys)
QUIZZES = {
    "pick": ("single", {"answers": 4}, {"correct": ["B"]}),
    "many": ("multiple", {"answers": 4}, {"correct": ["A", "C"], "partial": False}),
    "tf": ("truefalse", {"answers": 2}, {"correct": ["B"]}),
    "vote": ("poll", {"answers": 3, "select": "single", "scored": False, "points": "none"}, {}),
    "count": ("numeric", {"numeric": {"min": 0, "max": 12, "step": 1, "unit": ""}}, {"answer": 6, "tolerance": 0}),
    "name": ("text", {}, {"accept": ["Resource Description Framework"]}),
    "cloud": ("open", {"open": {"display": "wordcloud", "max_chars": 80}, "scored": False, "points": "none"}, {}),
    "steps": ("order", {"answers": 3}, {"order": ["C", "A", "B"], "partial": False}),
}


@dataclass
class FakeBundle:
    path: Path
    id: str
    deck: str
    slides: list[dict]
    pdf: bytes | None = None              # the stage PDF (stage=True)

    def slide(self, phase: str | None, quiz: str | None = None) -> int:
        return next(s["id"] for s in self.slides if s.get("phase") == phase and s.get("quiz") == quiz)


def make_bundle(folder: Path, deck: str = "test", quizzes: dict | None = None, time: int = 20,
                reveal: dict | None = None, title: str = "Test deck", stage: bool = False,
                language: str | None = None) -> FakeBundle:
    """quizzes: id -> (type, public extras, keys), default QUIZZES; reveal: id -> 'none' for
    quizzes answered on a later answer slide."""
    quizzes = QUIZZES if quizzes is None else quizzes
    reveal = reveal or {}
    images = {f"slides/{hashlib.sha256(png(c)).hexdigest()[:16]}.png": png(c) for c in ("white", "grey")}
    phone = png("black")
    phone_name = f"phone/{hashlib.sha256(phone).hexdigest()[:16]}.png"
    slide_img, other_img = list(images)
    picture = {"image": phone_name, "width": 270.0, "height": 18.0}
    deck_q, keys_q, slides = {}, {}, []

    def add(phase=None, quiz=None):
        entry = {"id": 256 + len(slides), "image": slide_img if phase else other_img}
        if phase:
            entry["phase"] = phase
        if quiz:
            entry["quiz"] = quiz
        slides.append(entry)

    add()
    add("join")
    later = []
    for qid, (kind, extra, keys) in quizzes.items():
        extra = dict(extra)
        n = extra.pop("answers", 0)
        public = {"type": kind, "title": f"Quiz {qid}", "time": time, "points": extra.pop("points", "standard"),
                  "scored": extra.pop("scored", True), "leaderboard": True, "reveal": reveal.get(qid, "slide"),
                  "prompt": picture, **extra}
        if n:
            public["answers"] = [{"id": chr(65 + i), "shape": i + 1, **picture} for i in range(n)]
        deck_q[qid] = public
        keys_q[qid] = {"prompt": f"Question {qid}?", **keys}
        add("read", qid)
        add("question", qid)
        if public["reveal"] == "slide":
            add("reveal", qid)
            if public["scored"]:
                add("leaderboard", qid)
        else:
            later.append(qid)
    add()
    for qid in later:                      # predict-then-see: the answers come later
        add("answer", qid)
        add("leaderboard", qid)
    add("podium")
    add()
    deck_json = {"format": FORMAT, "deck": deck, "name": title, "image": {"width": 1920, "height": 1080},
                 "slides": slides, "quizzes": deck_q}
    if language is not None:
        deck_json["language"] = language
    keys_json = {"format": FORMAT, "deck": deck, "quizzes": keys_q}
    files = {**images, phone_name: phone}
    pdf = f"%PDF-1.5\n% stage PDF of {title}\n%%EOF\n".encode() if stage else None
    if pdf is not None:
        pdf_name = f"stage/{hashlib.sha256(pdf).hexdigest()[:16]}.pdf"
        deck_json["pdf"] = {"file": pdf_name, "width": 453.543, "height": 255.118}
        files[pdf_name] = pdf
    bid = bundle_id(deck_json, keys_json)
    deck_json["bundle"] = keys_json["bundle"] = bid
    path = folder / f"{title.replace(' ', '-')}.bundle"
    for name, data in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(data)
    (path / "deck.json").write_text(json.dumps(deck_json, indent=1), encoding="utf-8")
    (path / "keys.json").write_text(json.dumps(keys_json, indent=1), encoding="utf-8")
    return FakeBundle(path, bid, deck, slides, pdf)
