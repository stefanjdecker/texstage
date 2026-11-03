# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Plain Beamer export contracts shared by Texstage and lecture-tools."""
import hashlib
from io import BytesIO
from pathlib import Path
import shutil
import zipfile

from PIL import Image
from pptx import Presentation
from pptx.util import Inches
import pytest

from texstage import api, cli
from texstage.build import beamer
from texstage.build.powerpoint import PptxDeck

needs_tex = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdflatex")


def source(tmp_path, body):
    folder = tmp_path / "source files"
    folder.mkdir()
    (tmp_path / "theme.tex").write_text(r"\setbeamertemplate{navigation symbols}{}", encoding="utf-8")
    (folder / "body.tex").write_text(body, encoding="utf-8")
    path = folder / "a talk.tex"
    path.write_text(r"""\documentclass{beamer}
\usepackage{pgfpages}
\input{../theme.tex}
\begin{document}
\input{body.tex}
\end{document}
""", encoding="utf-8")
    return path


def assert_pptx(path, notes, *, standard=False):
    deck = Presentation(path)
    assert deck.slide_width == Inches(10 if standard else 13.333)
    assert deck.slide_height == Inches(7.5)
    assert [slide.notes_slide.notes_text_frame.text for slide in deck.slides] == notes
    assert all(len(slide.shapes) == 1 for slide in deck.slides)
    with zipfile.ZipFile(path) as archive:
        assert not any(name.startswith("ppt/webextensions/") for name in archive.namelist())
    return deck


@needs_tex
@pytest.mark.parametrize("note_side,standard,dpi", [("right", False, None), ("left", True, 72)])
def test_overlay_order_notes_relative_paths_and_resolution(tmp_path, monkeypatch, note_side, standard, dpi):
    path = source(tmp_path, r"""\begin{frame}{First}
One.\pause Two.
\note<1>{First step.}\note<2>{Second step.}
\end{frame}
\begin{frame}{Second}No notes here.\end{frame}
\begin{frame}{Third}Last.\note{Final note.}\end{frame}
""")
    before = {file: file.read_bytes() for file in tmp_path.rglob("*.tex")}
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    output = "custom.pptx" if standard else None
    result = api.convert_beamer_to_pptx(path, output, target_height=240, dpi=dpi,
                                      standard=standard, note_side=note_side)
    assert result == (elsewhere / "custom.pptx" if standard else path.with_suffix(".pptx"))
    deck = assert_pptx(result, ["First step.", "Second step.", "", "Final note."], standard=standard)
    images = [slide.shapes[0].image for slide in deck.slides]
    assert len({hashlib.sha256(image.blob).digest() for image in images}) == 4
    expected_height = 273 if dpi else 240  # Beamer's default 4:3 page is about 273 pt tall.
    assert abs(images[0].size[1] - expected_height) <= 2
    picture = deck.slides[0].shapes[0]
    assert picture.width <= deck.slide_width and picture.height <= deck.slide_height
    assert picture.left == int((deck.slide_width - picture.width) / 2)
    assert picture.top == int((deck.slide_height - picture.height) / 2)
    assert all(file.read_bytes() == contents for file, contents in before.items())
    assert not list(path.parent.glob("_b2p_*"))


@needs_tex
def test_legacy_notes_and_kept_artifacts(tmp_path):
    path = source(tmp_path, r"""\begin{frame}{One}One.\note{Alpha.}\end{frame}
\begin{frame}{Two}Two.\note{Beta.}\end{frame}""")
    result = api.convert_beamer_to_pptx(path, target_height=120, legacy_two_pass_notes=True,
                                      keep_artifacts=True)
    assert_pptx(result, ["Alpha.", "Beta."])
    artifacts = {file: file.read_bytes() for file in path.parent.glob("_b2p_*")}
    assert path.parent / "_b2p_a talk_slides.pdf" in artifacts
    assert path.parent / "_b2p_a talk_notes.pdf" in artifacts
    # A later conversion must never destroy the artifacts retained by the user.
    with pytest.raises(FileExistsError, match="artifact already exists"):
        api.convert_beamer_to_pptx(path, legacy_two_pass_notes=True)
    assert all(file.read_bytes() == content for file, content in artifacts.items())


@needs_tex
def test_legacy_mismatch_is_explicit_and_can_be_allowed(tmp_path):
    path = source(tmp_path, r"""\begin{frame}{One}One.\note{Alpha.}\end{frame}
\begin{frame}{Two}No note.\end{frame}""")
    with pytest.raises(RuntimeError, match="slide/note page mismatch"):
        api.convert_beamer_to_pptx(path, target_height=120, legacy_two_pass_notes=True)
    assert not path.with_suffix(".pptx").exists()
    assert not list(path.parent.glob("_b2p_*"))
    output = api.convert_beamer_to_pptx(path, target_height=120, legacy_two_pass_notes=True,
                                      allow_note_mismatch=True)
    assert_pptx(output, ["Alpha.", ""])


def test_shared_slide_writer_preserves_fill_and_can_fit_without_distortion(tmp_path):
    data = BytesIO()
    Image.new("RGB", (400, 300), "blue").save(data, format="PNG")
    for fit in ("stretch", "contain"):
        deck = PptxDeck((16, 9))
        deck.add_slide(data.getvalue(), "Two\nparagraphs.", fit=fit)
        path = tmp_path / f"{fit}.pptx"
        deck.save(path)
        result = Presentation(path)
        picture = result.slides[0].shapes[0]
        assert picture.height == result.slide_height
        if fit == "stretch":
            assert picture.width == result.slide_width and picture.left == 0
        else:
            assert picture.width == int(result.slide_height * 4 / 3)
            assert picture.left == int((result.slide_width - picture.width) / 2)
        assert result.slides[0].notes_slide.notes_text_frame.text == "Two\nparagraphs."


def test_cli_forwards_all_legacy_options(monkeypatch):
    seen = []
    monkeypatch.setattr(beamer, "convert_beamer_to_pptx", lambda *args, **kwargs: seen.append((args, kwargs)))
    assert cli.main(["pptx", "a talk.tex", "-o", "other.pptx", "--target-height", "720",
                     "--dpi", "144", "--standard", "--note-side", "left", "--legacy-two-pass-notes",
                     "--allow-note-mismatch", "--keep-artifacts"]) == 0
    assert seen == [(("a talk.tex", "other.pptx"), dict(target_height=720, dpi=144, standard=True,
                    note_side="left", legacy_two_pass_notes=True, allow_note_mismatch=True, keep_artifacts=True))]


@pytest.mark.parametrize("error,code", [(FileNotFoundError("missing source"), 2),
                                       (RuntimeError("pdflatex failed"), 1)])
def test_cli_reports_conversion_errors(monkeypatch, capsys, error, code):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(beamer, "convert_beamer_to_pptx", fail)
    assert cli.main(["pptx", "missing.tex"]) == code
    assert str(error) in capsys.readouterr().err


def test_failure_cleans_only_generated_files(tmp_path, monkeypatch):
    path = source(tmp_path, r"\begin{frame}Hello.\end{frame}")
    sentinel = path.parent / "unrelated.aux"
    sentinel.write_text("keep me")
    monkeypatch.setattr(beamer.shutil, "which", lambda name: name)
    def fail(*args, **kwargs):
        raise RuntimeError("compilation failed")
    monkeypatch.setattr(beamer, "run_pdflatex", fail)
    with pytest.raises(RuntimeError, match="compilation failed"):
        api.convert_beamer_to_pptx(path)
    assert not list(path.parent.glob("_b2p_*"))
    assert sentinel.read_text() == "keep me"
    assert path.is_file()


@pytest.mark.parametrize("options", [{"target_height": 0}, {"dpi": -1}, {"note_side": "top"}])
def test_invalid_options_do_not_write_files(tmp_path, options):
    path = source(tmp_path, r"\begin{frame}Hello.\end{frame}")
    with pytest.raises(ValueError):
        api.convert_beamer_to_pptx(path, **options)
    assert not list(path.parent.glob("_b2p_*"))
