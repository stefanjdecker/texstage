# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage build: PowerPoint file, quiz bundle, layout check (docs/design.md, section 4)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation

from texstage import DEFAULT_SERVER
from texstage.build.pdf import Pdf
from texstage.build.builder import BuildError, BuildOptions, build
from texstage.build.powerpoint import NS_WE, addin_id, origin, retarget

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo" / "demo.tex"
PREAMBLE = "\\documentclass[aspectratio=169]{beamer}\n\\usepackage{texquiz}\n\\begin{document}\n"


def deck(tmp: Path, name: str, body: str) -> Path:
    tex = tmp / f"{name}.tex"
    tex.write_text(PREAMBLE + textwrap.dedent(body) + "\n\\end{document}\n", encoding="utf-8")
    return tex


@pytest.fixture
def demo(demo_build):
    return demo_build                      # built once per run (conftest.py)


def addin_properties(slide, server: str = "https://quiz.example.org") -> dict | None:
    """The add-in object's properties; it must reference the add-in of `server`."""
    for rel in slide.part.rels.values():
        if rel.reltype.endswith("/webextension"):
            root = etree.fromstring(rel.target_part.blob)
            ref = root.find(f"{{{NS_WE}}}reference")
            assert ref.get("id") == addin_id(server) and ref.get("storeType") == "Registry"
            return {p.get("name"): json.loads(p.get("value")) for p in root.iter(f"{{{NS_WE}}}property")}
    return None


def test_server_addresses():
    assert origin("HTTPS://Quiz.Example.org:443/addin/") == "https://quiz.example.org"
    assert origin("http://localhost:8470/") == "http://localhost:8470"
    assert origin("http://[::1]:8470") == "http://[::1]:8470"
    for bad in ("quiz.example.org", "ftp://x", "http://"):
        with pytest.raises(ValueError):
            origin(bad)
    assert addin_id("http://localhost:8470/") == addin_id("http://LOCALHOST:8470") != addin_id("http://localhost:8471")


# ------------------------------------------------------------------ the demo deck

def test_slide_sequence_with_leaderboards(demo):
    """One slide per page; a leaderboard after every scored quiz's reveal - not after the
    poll, the open question (unscored) or a quiz with leaderboard=false."""
    result, _, _ = demo
    seq = [(s.phase, s.quiz) for s in result.slides]
    assert seq[:6] == [(None, None), ("join", None), ("read", "rdf-triple"), ("question", "rdf-triple"),
                       ("reveal", "rdf-triple"), ("leaderboard", "rdf-triple")]
    boards = [q for p, q in seq if p == "leaderboard"]
    assert boards == ["rdf-triple", "iri-terms", "owl-dl", "triples-count", "rdf-acronym", "sparql-order"]
    assert seq[-2:] == [("podium", None), (None, None)]
    assert len(seq) == 28 + len(boards)                     # 28 pages in the present PDF
    lb = seq.index(("leaderboard", "rdf-triple"))
    assert result.slides[lb].image == result.slides[lb - 1].image   # the reveal picture


def test_pptx_pictures_notes_and_addins(demo):
    from io import BytesIO

    from PIL import Image
    result, deck, _ = demo
    prs = Presentation(result.pptx)
    slides = list(prs.slides)
    # before the deck's slides a first one that prepares the live slides when the slideshow
    # starts there - PowerPoint's alone, not one of the deck's
    assert len(slides) == len(result.slides) + 1 == len(deck["slides"]) + 1
    assert slides[0].slide_id == result.first and result.first not in {s["id"] for s in deck["slides"]}
    assert addin_properties(slides[0]) == {"server": "https://quiz.example.org", "deck": "demo",
                                           "bundle": result.bundle_id, "quiz": None, "phase": "prepare",
                                           "slideId": result.first, "key": "demo-presenter-key"}
    assert "Start the slideshow here" in slides[0].notes_slide.notes_text_frame.text
    with Image.open(BytesIO(slides[0].shapes[0].image.blob)) as im:
        assert im.size == (deck["image"]["width"], deck["image"]["height"])
    assert (prs.slide_width, prs.slide_height) == (12192000, 6858000)     # 16:9
    for slide, planned, entry in zip(slides[1:], result.slides, deck["slides"]):
        assert slide.shapes[0].shape_type == 13 and slide.shapes[0].width == prs.slide_width
        assert entry["id"] == slide.slide_id
        props = addin_properties(slide)
        if planned.phase is None:
            assert props is None
        else:
            assert props == {"server": "https://quiz.example.org", "deck": "demo",   # no bundle: the build
                             "bundle": result.bundle_id, "quiz": planned.quiz,        # delivers it (cli.deliver)
                             "phase": planned.phase, "slideId": slide.slide_id,
                             "key": "demo-presenter-key"}          # every live slide pairs by itself
    notes = [s.notes_slide.notes_text_frame.text if s.has_notes_slide else "" for s in slides[1:]]
    assert notes[0] == "Welcome everyone."
    assert notes[1] == "Phones out: scan the code, enter the PIN and a nickname."   # join, note=
    assert notes[2] == notes[3] == "Ask for an example after the reveal."   # rdf-triple: reading, question
    podium = next(i for i, s in enumerate(result.slides) if s.phase == "podium")
    assert notes[podium] == "Congratulate the top three."


def test_static_pptx(demo):
    """The same slides and notes, without add-in objects - for presenting without a server.
    The live deck stores answer-free pictures for reveal and leaderboard slides (PowerPoint
    shows the stored picture for a moment before a slide's add-in has started): their quiz's
    question picture, also as the add-in's snapshot. The static deck has the real ones."""
    result, _, _ = demo
    live, static = Presentation(result.pptx), Presentation(result.static)
    assert result.static.name == "demo-static.pptx"
    assert len(static.slides) == len(live.slides) - 1                  # no first slide: nothing to prepare
    question = {s.quiz: i for i, s in enumerate(result.slides) if s.phase == "question"}

    def blob(deck, i):
        return deck.slides[i].shapes[0].image.blob
    for i, (planned, a, b) in enumerate(zip(result.slides, list(live.slides)[1:], static.slides)):
        assert not any(r.reltype.endswith("/webextension") for r in b.part.rels.values())
        assert len(b.shapes) == 1
        if planned.phase in ("reveal", "leaderboard"):
            assert blob(live, i + 1) == blob(static, question[planned.quiz]), i      # a poll's are the same
        else:
            assert blob(live, i + 1) == blob(static, i), i
        if planned.phase:
            we = next(r.target_part for r in a.part.rels.values() if r.reltype.endswith("/webextension"))
            snapshot = next(r.target_part for r in we.rels.values() if r.reltype.endswith("/image"))
            assert snapshot.blob == blob(live, i + 1), i
        assert (b.notes_slide.notes_text_frame.text if b.has_notes_slide else "") == \
               (a.notes_slide.notes_text_frame.text if a.has_notes_slide else "")


def test_retarget(demo, tmp_path):
    """Another server for a built deck: the add-in reference and the server property of every
    live slide change, nothing else."""
    result, _, _ = demo
    pptx = tmp_path / "deck.pptx"
    shutil.copy(result.pptx, pptx)
    live = sum(1 for s in result.slides if s.phase) + 1                   # and the first slide's
    assert retarget(pptx, "http://localhost:8470/", "laptop-key") == live
    before, after = Presentation(result.pptx), Presentation(pptx)
    for a, b in zip(before.slides, after.slides):
        pa, pb = addin_properties(a), addin_properties(b, "http://localhost:8470")
        if pa is None:
            assert pb is None
        else:
            assert pb == pa | {"server": "http://localhost:8470", "key": "laptop-key"}
    assert retarget(pptx, "https://other.example.org") == live          # key unknown: none carried
    assert all("key" not in (addin_properties(s, "https://other.example.org") or {})
               for s in Presentation(pptx).slides)
    with pytest.raises(ValueError):
        retarget(pptx, "localhost")


def test_the_build_delivers_its_deck(tmp_path, monkeypatch):
    """The PowerPoint file carries no bundle (PowerPoint keeps at most 2 MB for an add-in, too
    little for a lecture's chapter): every deck reaches its server through its build - recorded
    for the quiz server on this machine, which finds it by itself, and uploaded complete to any
    other server (cli.deliver)."""
    import urllib.request
    import zipfile

    from starlette.testclient import TestClient
    from test_publish import running
    from test_server import KEY, config
    from texstage import cli
    from texstage.builds import build_folders
    from texstage.server.app import create_app
    tex = deck(tmp_path, "delivered", r"""
        \quizjoinframe
        \begin{frame}[t,quiz]{Which?}\begin{quiz}[id=which]{Which?}\choice*{A}\choice{B}\end{quiz}\end{frame}""")
    data, out = tmp_path / "data", tmp_path / "out"
    assert cli.main(["build", str(tex), "-o", str(out), "--key", "laptop-key", "--data", str(data), "--no-check"]) == 0
    assert build_folders(data) == [out.resolve()]                               # the laptop's server: no upload
    props = [p for p in (addin_properties(s, "http://localhost:8470") for s in Presentation(out / "delivered.pptx").slides) if p]
    assert props and not any("texquizBundle" in p for p in props)
    folder = out / "delivered.bundle"                                           # and as one file, to upload by hand
    with zipfile.ZipFile(out / "delivered.bundle.zip") as z:
        assert sorted(z.namelist()) == sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
        for n in z.namelist():                     # (the folder's JSON has the system's line ends)
            same = json.loads(z.read(n)) == json.loads((folder / n).read_bytes()) if n.endswith(".json") \
                else z.read(n) == (folder / n).read_bytes()
            assert same, n
    (tmp_path / "other").mkdir()
    with TestClient(create_app(config(tmp_path / "other"))) as client:          # a deck list's Upload
        r = client.post("/api/bundles", content=(out / "delivered.bundle.zip").read_bytes(), headers={"X-Texquiz-Key": KEY})
        assert r.status_code == 201 and r.json()["deck"] == "delivered"
        assert client.get("/api/decks", headers={"X-Texquiz-Key": KEY}).json()[0]["complete"] is True
    (tmp_path / "hosted").mkdir()
    with running(create_app(config(tmp_path / "hosted"))) as url:
        monkeypatch.setattr(cli, "on_this_machine", lambda server: False)     # (it runs here: as if elsewhere)
        assert cli.main(["build", str(tex), "-o", str(tmp_path / "out2"), "--server", url, "--key", KEY,
                         "--data", str(data), "--no-check"]) == 0
        req = urllib.request.Request(f"{url}/api/decks", headers={"X-Texquiz-Key": KEY})
        with urllib.request.urlopen(req, timeout=10) as r:
            (d,) = json.loads(r.read())
    assert d["deck"] == "delivered" and d["complete"] is True                  # uploaded, complete


def test_a_build_for_a_second_server_carries_its_key(tmp_path, monkeypatch):
    """--data names the data folder of the quiz server on this machine that the deck is for - a
    second one, say a dry run's on another port: the live slides carry the key in that folder
    (made there if need be), not the default folder's, which is the other server's."""
    from texstage import cli
    for name in ("TEXSTAGE_KEY", "TEXQUIZ_KEY"):
        monkeypatch.delenv(name, raising=False)
    tex = deck(tmp_path, "second", r"""
        \quizjoinframe
        \begin{frame}[t,quiz]{Which?}\begin{quiz}[id=which]{Which?}\choice*{A}\choice{B}\end{quiz}\end{frame}""")
    data, out = tmp_path / "dry-run", tmp_path / "out"
    assert cli.main(["build", str(tex), "-o", str(out), "--server", "http://localhost:8479", "--data", str(data),
                     "--no-check"]) == 0
    key = (data / "presenter-key").read_text(encoding="ascii").strip()
    props = [p for p in (addin_properties(s, "http://localhost:8479") for s in Presentation(out / "second.pptx").slides) if p]
    assert props and all(p["key"] == key for p in props)


def test_bundle_images_are_content_addressed(demo):
    result, deck, _ = demo
    names = {s["image"] for s in deck["slides"]}
    for q in deck["items"]["quiz"].values():
        names |= {q["prompt"]["image"]} | {a["image"] for a in q.get("answers", [])}
    for name in names:
        data = (result.bundle / name).read_bytes()
        assert name.endswith(hashlib.sha256(data).hexdigest()[:16] + ".png")
    assert deck["image"] == {"width": 1920, "height": 1080}
    # phone pictures are cropped to what is drawn: a short answer is narrower than its
    # 5.4 cm box (204 CSS px), and the picture keeps 3 device pixels per CSS pixel
    pick = deck["items"]["quiz"]["rdf-triple"]
    assert all(a["width"] < 180 for a in pick["answers"]) and pick["prompt"]["width"] < 260
    from PIL import Image
    with Image.open(result.bundle / pick["prompt"]["image"]) as im:
        assert im.width == pytest.approx(3 * pick["prompt"]["width"], abs=1)


def test_public_quizzes_hold_no_answers(demo):
    """deck.json's quiz items are what phones get: no correctness, no explanation, no
    accepted texts, no numeric answer, no solved order - and answers are named by their
    position on the slide (A, B, ...), not by authored id or step number."""
    _, deck, keys = demo

    def keys_of(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys_of(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys_of(v)
    used = set(keys_of(deck["items"]["quiz"]))
    assert not used & {"correct", "explanation", "accept", "answer", "tolerance", "order", "source", "partial"}
    for text in ("subject, a predicate", "Resource Description Framework", "OWL~2~DL"):
        assert text not in json.dumps(deck)
    q = deck["items"]["quiz"]["sparql-order"]
    assert [a["id"] for a in q["answers"]] == ["A", "B", "C", "D"]
    assert deck["items"]["quiz"]["triples-count"]["numeric"] == {"min": 0, "max": 12, "step": 1, "unit": ""}
    assert deck["items"]["quiz"]["favourite-format"]["scored"] is False


def test_keys(demo):
    _, deck, keys = demo
    k = keys["items"]["quiz"]
    assert k["rdf-triple"]["correct"] == ["B"]
    assert k["owl-dl"]["answers"][k["owl-dl"]["correct"][0]]["id"] == "false"
    # the order, mapped back through the public ids, is the authored (correct) order
    order = k["sparql-order"]["order"]
    assert [k["sparql-order"]["answers"][pid]["source"][:5] for pid in order] == \
        ["Parse", "Trans", "Evalu", "Apply"]
    assert order != ["A", "B", "C", "D"]                      # shown shuffled
    assert k["triples-count"]["answer"] == 6 and k["triples-count"]["tolerance"] == 0
    assert k["rdf-acronym"]["accept"] == ["Resource Description Framework", "Resource Description Format"]
    # shuffled choices: the public id is the position on the slide, the authored id stays here
    iri = k["iri-terms"]
    assert {iri["answers"][pid]["id"] for pid in iri["correct"]} == {"A", "D"}
    assert keys["bundle"] == deck["bundle"]


def test_rectangles_are_fractions_and_keyed_by_position(demo):
    _, deck, _ = demo
    box = next(b for s in deck["slides"] for b in s.get("live", [])
               if b.get("item") == "sparql-order" and b["phase"] == "question")
    cells = box["rects"]["cells"]
    assert list(cells) == ["A", "B", "C", "D"]
    for r in list(cells.values()) + [box["rects"]["prompt"]]:
        assert 0 <= r["x"] < 1 and 0 <= r["y"] < 1 and 0 < r["w"] <= 1 and 0 < r["h"] <= 1
    first_row = sorted(cells.values(), key=lambda r: (r["y"], r["x"]))[:2]
    assert [cells["A"], cells["B"]] == first_row               # A, B: the top row, left to right


def test_the_bundle_has_format_2(demo):
    """deck.json and keys.json of format 2 (since 2026-10-10): the content types the deck uses,
    their items, and per slide its live boxes. The server gives the windows a view with the
    names of format 1 as well (server/bundles.py, client_view), which they read until they
    read the boxes themselves."""
    from texstage.server.bundles import client_view
    _, deck, keys = demo
    assert deck["format"] == keys["format"] == 2 and deck["types"] == ["quiz"]
    assert set(deck["items"]) == set(keys["items"]) == {"quiz"} and "quizzes" not in deck
    boxes = [b for s in deck["slides"] for b in s.get("live", [])]
    assert boxes and {b["type"] for b in boxes} == {"quiz"} and not any("phase" in s for s in deck["slides"])
    view = client_view(deck)
    assert view["quizzes"] == deck["items"]["quiz"] and view["types"] == ["quiz"]
    for s, v in zip(deck["slides"], view["slides"]):
        box = (s.get("live") or [{}])[0]
        assert (v.get("phase"), v.get("quiz"), v.get("rects")) == (box.get("phase"), box.get("item"), box.get("rects"))


def test_bundle_id_is_reproducible(demo, tmp_path):
    result, _, _ = demo
    again = build(DEMO, tmp_path, BuildOptions(server="https://quiz.example.org", key="demo-presenter-key",
                                               check=False))
    assert again.bundle_id == result.bundle_id


def test_check_passes_on_the_demo(demo):
    result, _, _ = demo
    assert result.problems == [] and result.warnings == []


# ------------------------------------------------------------------ the stage PDF (texstage)

STAGE_FIELDS = ("frame", "step", "page", "note", "notes")


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    """The demo deck built with --stage: (BuildResult, deck.json)."""
    r = build(DEMO, tmp_path_factory.mktemp("staged"),
              BuildOptions(server="https://quiz.example.org", key="demo-presenter-key", stage=True))
    return r, json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))


def test_a_stage_build_adds_the_stage_pdf(demo, staged, tmp_path):
    """--stage keeps slides and quizzes as they are and adds the stage PDF (content-addressed)
    and per slide its frame, step, pages and note text. A build without --stage has none of it."""
    result, deck, _ = demo
    r, sdeck = staged
    assert "pdf" not in deck and not any(k in s for s in deck["slides"] for k in STAGE_FIELDS)
    assert [{k: v for k, v in s.items() if k not in STAGE_FIELDS} for s in sdeck["slides"]] == deck["slides"]
    assert sdeck["items"] == deck["items"] and r.problems == []
    pdf = (r.bundle / sdeck["pdf"]["file"]).read_bytes()
    assert pdf == r.stage.pdf.read_bytes() and r.stage.pdf.name == "demo-stage.pdf"
    assert sdeck["pdf"] == {"file": f"stage/{hashlib.sha256(pdf).hexdigest()[:16]}.pdf",
                            "width": pytest.approx(453.543, abs=0.01), "height": pytest.approx(255.118, abs=0.01)}
    first = sdeck["slides"][0]
    assert (first["frame"], first["step"], first["page"], first["notes"]) == (1, 1, 1, "Welcome everyone.")
    quiz = [s for s in sdeck["slides"] if any(b.get("item") == "rdf-triple" for b in s.get("live", []))]
    assert [(s["live"][0]["phase"], s["step"]) for s in quiz] == [("read", 1), ("question", 2), ("reveal", 3), ("leaderboard", 3)]
    assert len({s["frame"] for s in quiz}) == 1 and quiz[3]["page"] == quiz[2]["page"]
    assert all("Ask for an example" in s["notes"] for s in quiz[:3]) and "notes" not in quiz[3]


def test_stage_slide_pages_are_the_slides(staged):
    """Every slide page of the stage PDF is the slide half of the present compile's page,
    pixel for pixel - the live rectangles, measured there, fit it - and the note pages
    hold the notes, which the slide pages never show."""
    r, sdeck = staged
    present = r.stage.pdf.with_name("demo-present.pdf")
    with Pdf(present) as pd, Pdf(r.stage.pdf) as sd:
        assert len(sd) == len(r.stage.pages) + sum(p.note is not None for p in r.stage.pages)
        for n, p in enumerate(r.stage.pages, 1):
            page = sd[p.page - 1]
            slide = (0, 0, page.width, page.height)
            assert page.render(1).tobytes() == pd[n - 1].render(1, clip=slide).tobytes(), n
            assert "Welcome everyone" not in page.text(), n
        welcome = r.stage.pages[0].note
        assert welcome and "Welcome everyone" in sd[welcome - 1].text()


def test_stage_frames_steps_and_note_pages(tmp_path):
    """Overlay steps are steps of one frame, each with its own note page; a frame broken
    by allowframebreaks is a frame per page, as Beamer numbers them."""
    items = " ".join(f"\\item Line {i}" for i in range(1, 25))
    r = build(deck(tmp_path, "steps", rf"""
        \begin{{frame}}{{Steps}}
        \begin{{itemize}}\item A \pause \item B \pause \item C\end{{itemize}}
        \note{{The steps.}}
        \end{{frame}}
        \begin{{frame}}{{Silent}}
        Nothing.
        \end{{frame}}
        \begin{{frame}}[allowframebreaks]{{Long}}
        \begin{{itemize}}{items}\end{{itemize}}
        \end{{frame}}"""), tmp_path / "out", BuildOptions(check=False, stage=True, key="test-key"))
    slides = json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))["slides"]
    assert [(s["frame"], s["step"], s["page"], s.get("note")) for s in slides] == [
        (1, 1, 1, 2), (1, 2, 3, 4), (1, 3, 5, 6), (2, 1, 7, None), (3, 1, 8, None), (4, 1, 9, None)]
    assert [s.get("notes") for s in slides][:4] == ["The steps."] * 3 + [None]
    assert r.first is None and len(Presentation(r.pptx).slides) == len(slides)    # no quiz: no first slide


def test_a_note_template_without_the_note(tmp_path):
    """The note pages are found by the mark the note's text leaves; a deck whose note page
    template does not show the note is refused, not paired wrongly."""
    tex = deck(tmp_path, "blank", r"""
        \setbeamertemplate{note page}{A note page without its note.}
        \begin{frame}{One}One.\note{Hidden.}\end{frame}
        \begin{frame}{Two}Two.\end{frame}""")
    with pytest.raises(BuildError, match="insertnote"):
        build(tex, tmp_path / "out", BuildOptions(check=False, stage=True, key="test-key"))


# ------------------------------------------------------------------ predict-then-see, checks

ANSWERED_LATER = r"""
\quizjoinframe
\begin{frame}[t,quiz]{Question: How Many?}
Material.
\begin{quiz}[id=cities, reveal=none]{How many solution mappings?}
  \choice{2}\choice{3}\choice{4}\choice*{5}
\end{quiz}
\end{frame}
\begin{frame}{Meanwhile}
A slide between question and answer.
\end{frame}
\begin{frame}[t,answer=cities]{Answer: Five}
The answer.
\end{frame}
"""


def test_reveal_on_an_answer_frame(tmp_path):
    """reveal=none: a reading and a question slide; the answer frame is live (it reveals
    the quiz) and the leaderboard follows it."""
    r = build(deck(tmp_path, "later", ANSWERED_LATER), tmp_path / "out", BuildOptions(key="test-key"))
    assert [(s.phase, s.quiz) for s in r.slides] == [
        ("join", None), ("read", "cities"), ("question", "cities"), (None, None), ("answer", "cities"),
        ("leaderboard", "cities")]
    assert r.problems == []


def test_reveal_none_without_answer_frame_warns(tmp_path):
    body = ANSWERED_LATER.replace("[t,answer=cities]", "[t,answer]")
    r = build(deck(tmp_path, "unanswered", body), tmp_path / "out", BuildOptions(check=False, key="test-key"))
    assert any("never sees" in w for w in r.warnings)
    assert [s.phase for s in r.slides][:4] == ["join", "read", "question", "leaderboard"]


def test_answer_frame_naming_an_unknown_quiz(tmp_path):
    body = ANSWERED_LATER.replace("answer=cities", "answer=towns")
    with pytest.raises(BuildError, match="answer=towns"):
        build(deck(tmp_path, "unknown", body), tmp_path / "out", BuildOptions(key="test-key"))


def test_check_finds_a_quiz_frame_that_runs_into_the_footline(tmp_path):
    """The handout shows quiz frames as placeholders; only the present and solutions builds
    show that the answer boxes push the author's material off the slide. With the markers
    of combine-slides.py the finding names the frame's file."""
    material = "\n\n".join(f"Material line {i} of a long table." for i in range(14))
    body = (f"%%% --- Start of 001.tex --- %%%\n\\begin{{frame}}{{Fine}}Fine.\\end{{frame}}\n"
            f"%%% --- Start of 002.tex --- %%%\n\\begin{{frame}}[t,quiz]{{Too Much}}\n{material}\n"
            r"\begin{quiz}[id=crowded]{Which?}\choice{A}\choice*{B}\end{quiz}" "\n\\end{frame}\n")
    r = build(deck(tmp_path, "crowded", body), tmp_path / "out", BuildOptions(key="test-key"))
    assert r.problems, r.findings
    assert {(f.where, f.what) for f in r.problems} == {("002.tex", "quiz crowded")}
    assert {f.build for f in r.problems} == {"present", "solutions"}
    assert all("too high" in f.message for f in r.problems)


# ------------------------------------------------------------------ a course chapter



def test_latex_runs_again_while_the_log_asks(tmp_path, monkeypatch):
    """A pass that could not read the .aux or .nav the pass before wrote (on Windows a virus
    scanner may hold a file just written) typesets as a first one - frame totals 1, references ??,
    a new bundle ID: compile_deck runs again while the log asks for it, two passes more at most,
    and not after a single pass asked for."""
    from texstage.build import latex
    logs, calls = [], []

    def pdflatex(cmd, **kw):
        calls.append(cmd)
        out = Path(next(a.split("=", 1)[1] for a in cmd if a.startswith("-output-directory=")))
        job = next(a.split("=", 1)[1] for a in cmd if a.startswith("-jobname="))
        (out / f"{job}.log").write_text(logs[min(len(calls), len(logs)) - 1], encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(latex.shutil, "which", lambda name: name)
    monkeypatch.setattr(latex.subprocess, "run", pdflatex)
    tex = tmp_path / "deck.tex"
    tex.write_text("x", encoding="utf-8")
    first = "No file deck-present.aux.\nNo file deck-present.nav.\n"
    settled = "(./deck-present.aux) (./deck-present.nav)\n"
    moved = "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.\n"
    for passes, those, runs in ((2, [first, settled], 2),            # as usual
                                (2, [first, first, settled], 3),     # the second pass missed the .aux
                                (2, [first, moved, settled], 3),     # the references moved
                                (2, [first] * 5, 4),                 # never settled: two more at most
                                (1, [first], 1)):                    # one pass asked for: one
        logs[:], calls[:] = those, []
        latex.compile_deck(tex, "present", tmp_path / "out", passes=passes)
        assert len(calls) == runs, (passes, those)


# ------------------------------------------------------------------ a video (texvideo)

VIDEO_DECK = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texvideo}
\begin{document}
\begin{frame}{Before}Hello.\end{frame}
\begin{frame}[label=clip]{A video}
\video[poster=clip.png, width=0.6\textwidth, start=1, end=5]{clip.mp4}
\pause The next step: the same video.
\end{frame}
\begin{frame}{Online}\video[poster=clip.png, width=4cm, id=talk]{https://example.org/talk.mp4}\end{frame}
\begin{frame}{Later}Text.\only<2>{\video[poster=clip.png, width=3cm, id=later, autoplay]{clip.mp4}}\end{frame}
\againframe<1>{clip}
\end{document}
"""


def test_a_video_deck(tmp_path):
    r"""A video (docs/architecture/content-types-design.md, section 7): its file and poster in the bundle's
    media/, content-addressed; its box on its slides - the steps of its frame, the second only
    (\only<2>), the frame again (\againframe) -; in both PowerPoint files a native video at the
    box - an online one as its poster, with a link - and no add-in, so no first slide."""
    from PIL import Image
    Image.new("RGB", (320, 180), (20, 120, 200)).save(tmp_path / "clip.png")
    movie = b"\x00\x00\x00\x18ftypmp42" + bytes(4096)            # the build reads it, never plays it
    (tmp_path / "clip.mp4").write_bytes(movie)
    tex = tmp_path / "talk.tex"
    tex.write_text(VIDEO_DECK, encoding="utf-8")
    r = build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))
    deck = json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))
    assert deck["types"] == ["video"] and r.first is None and r.warnings == []
    assert sorted(deck["items"]["video"]) == ["clip", "later", "talk"]
    clip, talk, later = (deck["items"]["video"][k] for k in ("clip", "talk", "later"))
    assert (r.bundle / clip["media"]).read_bytes() == movie and clip["media"].endswith(".mp4")
    assert (clip["start"], clip["end"]) == (1.0, 5.0) and talk["src"] == "https://example.org/talk.mp4"
    assert clip["poster"] == talk["poster"] and (r.bundle / clip["poster"]).is_file()
    assert later["media"] == clip["media"] and later["autoplay"] is True and "autoplay" not in clip
    assert talk["player"] == {"file": "https://example.org/talk.mp4"} and "player" not in clip
    shown = [[b["item"] for b in s.get("live", [])] for s in deck["slides"]]
    assert shown == [[], ["clip"], ["clip"], ["talk"], [], ["later"], ["clip"]]
    box = deck["slides"][1]["live"][0]
    assert box["type"] == "video" and box["item"] == "clip" and 0.5 < box["rects"]["box"]["w"] < 0.55
    for path in (r.pptx, r.static):
        slides = list(Presentation(path).slides)
        assert len(slides) == 7
        for i in (1, 2, 5, 6):
            (media,) = [s for s in slides[i].shapes if s.name.startswith("texstage video")]
            assert media.shape_type == 16                             # MSO_SHAPE_TYPE.MEDIA
        (link,) = [s for s in slides[3].shapes if s.name == "texstage video talk"]
        assert link.click_action.hyperlink.address == "https://example.org/talk.mp4"
        assert all(addin_properties(s, DEFAULT_SERVER) is None for s in slides)


# ------------------------------------------------------------------ live activities (texactivity)

ACTIVITY_DECK = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texactivity}
\begin{document}
\begin{frame}{Before}Hello.\end{frame}
\begin{frame}[t]{Graph}
\begin{activity}[id=crowd, suggest={:KG}, min=2, review]\prompt{Add triples.}\end{activity}
\end{frame}
\begin{frame}[t,fragile]{Query}
\begin{activity}[id=join, input=code, engine=sparql, seed=uni.ttl, tokens={SELECT, \{}, reference=alt.rq]
  \prompt{The professors with their lectures.}
  \reference{SELECT ?n WHERE {
  ?p :name ?n .
}}
\end{activity}
\pause Then.
\end{frame}
\end{document}
"""


def test_an_activity_deck(tmp_path):
    """Live activities (docs/live-activities-design.md, section 6): their items in deck.json - a
    tuple's fields, suggestions and minimum, a query's engine, its tokens (the engine's added) and
    its seed, a file in data/ -, the references in keys.json only, the prompt as the phones'
    picture; the box on the slides that show it; PowerPoint gets the slide pictures alone - no
    add-in, no first slide."""
    seed = "@prefix : <http://example.org/> .\n:kant :name \"Kant\" .\n"
    (tmp_path / "uni.ttl").write_text(seed, encoding="utf-8")
    (tmp_path / "alt.rq").write_text("SELECT ?n\nWHERE { ?p :name ?n }\n", encoding="utf-8")
    tex = tmp_path / "talk.tex"
    tex.write_text(ACTIVITY_DECK, encoding="utf-8")
    r = build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))
    deck = json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))
    keys = json.loads((r.bundle / "keys.json").read_text(encoding="utf-8"))
    assert deck["types"] == ["activity"] and r.first is None and r.warnings == []
    crowd, join = deck["items"]["activity"]["crowd"], deck["items"]["activity"]["join"]
    assert {k: v for k, v in crowd.items() if k != "prompt"} == {
        "input": "tuple", "limit": 10, "fields": ["Subject", "Predicate", "Object"], "suggest": [":KG"], "min": 2,
        "review": True, "terms": "exact"}
    assert join["engine"] == "sparql" and join["limit"] == 5 and "fields" not in join and "terms" not in join
    assert join["tokens"] == ["SELECT", "{", "}", "?", ".", ";", ":"]
    assert join["seed"].startswith("data/") and (r.bundle / join["seed"]).read_text(encoding="utf-8") == seed
    for item in (crowd, join):
        assert (r.bundle / item["prompt"]["image"]).is_file() and item["prompt"]["image"].startswith("phone/")
    assert keys["items"]["activity"] == {"join": {"reference": ["SELECT ?n WHERE {\n  ?p :name ?n .\n}",
                                                               "SELECT ?n\nWHERE { ?p :name ?n }"]}}
    assert "?p :name" not in json.dumps(deck)
    shown = [[b["item"] for b in s.get("live", [])] for s in deck["slides"]]
    assert shown == [[], ["crowd"], ["join"], ["join"]]
    box = deck["slides"][1]["live"][0]
    assert box["type"] == "activity" and set(box["rects"]) == {"box"} and 0.7 < box["rects"]["box"]["w"] < 0.9
    for path in (r.pptx, r.static):
        slides = list(Presentation(path).slides)
        assert len(slides) == 4 and all(addin_properties(s, DEFAULT_SERVER) is None for s in slides)


TERMS_DECK = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texactivity}
\begin{document}
\begin{frame}[t]{An ER sketch}
\begin{activity}[id=words, fields={Entity, Relationship, Entity}, terms=loose]\prompt{Entities.}\end{activity}
\end{frame}
\begin{frame}[t,fragile]{A query}
\begin{activity}[id=q, input=code, engine=sql, terms=exact]\seed{CREATE TABLE t (x);}\end{activity}
\end{frame}
\end{document}
"""


def test_an_activity_takes_its_terms(tmp_path):
    """terms=loose for plain words - case, accents and spacing do not count, as the word cloud
    groups answers; exact, the default, is RDF's; a query activity has no terms: the build says so."""
    tex = tmp_path / "talk.tex"
    tex.write_text(TERMS_DECK, encoding="utf-8")
    r = build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))
    items = json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))["items"]["activity"]
    assert items["words"]["terms"] == "loose" and "terms" not in items["q"]
    assert "activity q: terms - not for input=code" in r.warnings


SQL_DECK = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texactivity}
\begin{document}
\begin{frame}[t,fragile]{Query}
\begin{activity}[id=names, input=code, engine=sql, tokens={SELECT, FROM}]
  \prompt{The professors whose name starts with K.}
  \seed{CREATE TABLE professor (id INTEGER PRIMARY KEY, name TEXT);
INSERT INTO professor VALUES (1, 'Kant'), (2, 'Socrates');}
  \reference{SELECT name FROM professor WHERE name LIKE 'K%';}
\end{activity}
\end{frame}
\end{document}
"""


def test_an_sql_activity(tmp_path):
    """An activity of engine=sql (texstage/engines.py): its seed - here in the frame, read verbatim
    with SQL's quotes, semicolons and percent signs - a file data/<hash>.sql in the bundle, SQL's
    tokens added to the deck's, the reference as written."""
    tex = tmp_path / "talk.tex"
    tex.write_text(SQL_DECK, encoding="utf-8")
    r = build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))
    item = json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))["items"]["activity"]["names"]
    keys = json.loads((r.bundle / "keys.json").read_text(encoding="utf-8"))
    assert item["engine"] == "sql" and item["tokens"] == ["SELECT", "FROM", "*", ",", "(", ")", "=", "'", "."]
    assert item["seed"].startswith("data/") and item["seed"].endswith(".sql")
    assert (r.bundle / item["seed"]).read_text(encoding="utf-8") == (
        "CREATE TABLE professor (id INTEGER PRIMARY KEY, name TEXT);\nINSERT INTO professor VALUES (1, 'Kant'), (2, 'Socrates');\n")
    assert keys["items"]["activity"] == {"names": {"reference": ["SELECT name FROM professor WHERE name LIKE 'K%';"]}}


TURTLE_DECK = r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texactivity}
\begin{document}
\begin{frame}[t,fragile]{Berlin in Turtle}
\begin{activity}[id=berlin, input=code, engine=turtle, seed=prefixes.ttl,
                 tokens={dbr:Berlin, rdfs:label, \^\^xsd:integer, @de}]
  \prompt{The four triples about Berlin, in Turtle.}
  \reference{dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;
  dbo:populationTotal 3596999 ;
  geo:lat 52.52 .}
  \reference{<http://dbpedia.org/resource/Berlin> <http://www.w3.org/2000/01/rdf-schema#label> "Berlin"@de, "Berlino"@it ;
  <http://dbpedia.org/ontology/populationTotal> "3596999"^^xsd:integer ;
  <http://www.w3.org/2003/01/geo/wgs84_pos#lat> 52.52 .  # 100% the same graph}
\end{activity}
\end{frame}
\end{document}
"""
TURTLE_PREFIXES = """@prefix dbr: <http://dbpedia.org/resource/> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix geo: <http://www.w3.org/2003/01/geo/wgs84_pos#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""


def test_a_turtle_activity(tmp_path):
    """An activity of engine=turtle (texstage/engines.py): its seed - the prefixes the students'
    Turtle may use - a file data/<hash>.ttl in the bundle, Turtle's tokens added to the deck's (\\^
    for ^, which TeX would read as a character code), two references read verbatim with Turtle's
    # and % and ^^ - two spellings of one graph, each of whose clusters counts as the reference's."""
    (tmp_path / "prefixes.ttl").write_text(TURTLE_PREFIXES, encoding="utf-8")
    tex = tmp_path / "talk.tex"
    tex.write_text(TURTLE_DECK, encoding="utf-8")
    r = build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))
    assert r.warnings == []
    item = json.loads((r.bundle / "deck.json").read_text(encoding="utf-8"))["items"]["activity"]["berlin"]
    keys = json.loads((r.bundle / "keys.json").read_text(encoding="utf-8"))
    assert item["engine"] == "turtle" and item["limit"] == 5
    assert item["tokens"] == ["dbr:Berlin", "rdfs:label", "^^xsd:integer", "@de",
                              ":", ".", ";", ",", '"', "@", "^^", "<", ">", "_:", "[", "]", "(", ")"]
    assert item["seed"].startswith("data/") and item["seed"].endswith(".ttl")
    assert (r.bundle / item["seed"]).read_text(encoding="utf-8") == TURTLE_PREFIXES
    assert keys["items"]["activity"] == {"berlin": {"reference": [
        'dbr:Berlin rdfs:label "Berlin"@de , "Berlino"@it ;\n  dbo:populationTotal 3596999 ;\n  geo:lat 52.52 .',
        '<http://dbpedia.org/resource/Berlin> <http://www.w3.org/2000/01/rdf-schema#label> "Berlin"@de, "Berlino"@it ;\n'
        '  <http://dbpedia.org/ontology/populationTotal> "3596999"^^xsd:integer ;\n'
        '  <http://www.w3.org/2003/01/geo/wgs84_pos#lat> 52.52 .  # 100% the same graph']}}


@pytest.mark.parametrize("change, message", [
    (("engine=sparql", "engine=prolog"), "engine=prolog - texstage runs sparql"),
    (("seed=uni.ttl", "seed=gone.ttl"), "the seed gone.ttl is not there"),
    (("seed=uni.ttl", "seed=uni.nt"), "sparql takes .ttl files"),
    (("engine=sparql", "engine=sql"), "the seed uni.ttl - sql takes .sql files"),
    (("engine=sparql, seed=uni.ttl", "engine=turtle, seed=uni.nt"), "the seed uni.nt - turtle takes .ttl files"),
    (("min=2, review]", "min=2, review, limit=99]"), "limit=99 - a number from 1 to 50"),
    (("suggest={:KG}", "suggest={:KG}, fields={Only}"), "1 fields - an activity of input=tuple has 2 or 3"),
    (("suggest={:KG}", "suggest={:KG}, fields={Who, Does, What, Where}"), "4 fields - an activity of input=tuple has 2 or 3"),
])
def test_activity_build_errors(tmp_path, change, message):
    """What the build refuses: an engine texstage does not run, a seed that is not there or not
    the engine's, numbers out of range, a tuple of one field or of four (the box draws a graph:
    the first and the last field a node, a middle one the edge's label)."""
    (tmp_path / "uni.ttl").write_text("@prefix : <http://example.org/> .\n", encoding="utf-8")
    (tmp_path / "uni.nt").write_text("", encoding="utf-8")
    (tmp_path / "alt.rq").write_text("ASK {}\n", encoding="utf-8")
    tex = tmp_path / "talk.tex"
    tex.write_text(ACTIVITY_DECK.replace(*change), encoding="utf-8")
    with pytest.raises(BuildError) as err:
        build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))
    assert message in str(err.value), str(err.value)


@pytest.mark.parametrize("src, how", [
    ("https://www.youtube.com/watch?v=aqz-KE-bpKQ", {"youtube": "aqz-KE-bpKQ"}),
    ("https://www.youtube.com/watch?feature=share&v=aqz-KE-bpKQ&t=42", {"youtube": "aqz-KE-bpKQ"}),
    ("https://youtu.be/aqz-KE-bpKQ?si=x", {"youtube": "aqz-KE-bpKQ"}),
    ("https://www.youtube-nocookie.com/embed/aqz-KE-bpKQ", {"youtube": "aqz-KE-bpKQ"}),
    ("https://m.youtube.com/shorts/aqz-KE-bpKQ", {"youtube": "aqz-KE-bpKQ"}),
    ("https://vimeo.com/1084537", {"vimeo": "1084537"}),
    ("https://vimeo.com/channels/staffpicks/1084537", {"vimeo": "1084537"}),
    ("https://player.vimeo.com/video/1084537?h=0a1b2c3d", {"vimeo": "1084537", "hash": "0a1b2c3d"}),
    ("https://vimeo.com/1084537/0a1b2c3d", {"vimeo": "1084537", "hash": "0a1b2c3d"}),
    ("https://example.org/talk.MP4?x=1", {"file": "https://example.org/talk.MP4?x=1"}),
    ("https://www.youtube.com/channel/UC123", None),
    ("https://vimeo.com/showcase/123", None),
    ("https://example.org/talk", None),
])
def test_how_an_online_video_plays(src, how):
    """build/video.py's player(): YouTube's and Vimeo's addresses as they are shared, and
    addresses of files; anything else keeps its poster (the build warns)."""
    from texstage.build.video import player
    assert player(src) == how


def test_a_video_and_a_quiz_on_one_slide_are_refused(tmp_path):
    from PIL import Image
    Image.new("RGB", (32, 18)).save(tmp_path / "clip.png")
    (tmp_path / "clip.mp4").write_bytes(b"x")
    tex = deck(tmp_path, "both", r"""
        \begin{frame}[t,quiz]{Both}
        \video[poster=clip.png, width=3cm]{clip.mp4}
        \begin{quiz}[id=q]{Which?}\choice*{A}\choice{B}\end{quiz}
        \end{frame}""")
    tex.write_text(tex.read_text(encoding="utf-8").replace("\\usepackage{texquiz}", "\\usepackage{texquiz}\n\\usepackage{texvideo}"),
                   encoding="utf-8")
    with pytest.raises(BuildError, match="a quiz and a video on one slide"):
        build(tex, tmp_path / "out", BuildOptions(check=False, key="test-key"))