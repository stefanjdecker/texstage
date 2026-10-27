# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage present: what starts a lecture - the deck built if needed, the quiz server of this
machine used or started, texstage's presenter window or the live PowerPoint file opened
(cli.cmd_present; texstage is the same)."""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fake_bundle import make_bundle
from texstage import cli

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def touch(path: Path, t: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("x", encoding="utf-8")
    os.utime(path, (t, t))


def built(tmp_path: Path):
    """A deck and its up-to-date build (with the stage PDF and the live PowerPoint file)."""
    out = tmp_path / "talk" / "texquiz-out"
    fb = make_bundle(out, stage=True)
    (out / "Test-deck.pptx").write_bytes(b"pptx")
    tex = tmp_path / "talk" / "talk.tex"
    touch(tex, (fb.path / "deck.json").stat().st_mtime - 60)
    return tex, out, fb


@pytest.fixture
def opened(monkeypatch):
    seen = []
    monkeypatch.setattr("webbrowser.open", lambda url: seen.append(("browser", url)))
    monkeypatch.setattr(cli, "open_file", lambda p: seen.append(("file", Path(p).name)))
    return seen


def test_when_a_deck_needs_a_build(tmp_path):
    deck, out = tmp_path / "talk", tmp_path / "talk" / "texquiz-out"
    touch(deck / "talk.tex", 1_000_000)
    assert cli.needs_build(deck, out) == "not built yet"
    fb = make_bundle(out)
    assert cli.needs_build(deck, out) == "built without the stage PDF"
    shutil.rmtree(fb.path)
    fb = make_bundle(out, stage=True)
    t = (fb.path / "deck.json").stat().st_mtime
    touch(deck / "talk.tex", t - 60)
    touch(deck / "figures" / "plot.pdf", t - 60)
    assert cli.needs_build(deck, out) is None
    touch(deck / "talk.pdf", t + 60)                       # the compiled deck: not a source
    touch(deck / "build" / "frame.tex", t + 60)            # nor what a build writes
    touch(deck / "talk.log", t + 60)
    assert cli.needs_build(deck, out) is None
    touch(deck / "figures" / "plot.pdf", t + 60)           # a picture: a source
    assert cli.needs_build(deck, out) == "figures/plot.pdf changed since the build"
    touch(deck / "figures" / "plot.pdf", t - 60)
    touch(deck / "slides.tex", t + 60)
    assert cli.needs_build(deck, out) == "slides.tex changed since the build"
    assert cli.needs_build(deck, out, ignore=("slides.tex",)) is None   # a chapter's: written from its frames


def test_present_on_the_server_that_runs(tmp_path, monkeypatch, opened):
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("the build is up to date"))
    monkeypatch.setattr(cli, "cmd_serve", lambda args: pytest.fail("a server runs already"))
    assert cli.main(["present", str(tex)]) == 0
    assert opened == [("browser", f"http://localhost:8470/stage?bundle={fb.id}")]   # this deck, at once
    assert cli.main(["present", str(out), "--powerpoint"]) == 0            # a build folder, with PowerPoint
    assert opened[-1] == ("file", "Test-deck.pptx")


def test_present_starts_the_server(tmp_path, monkeypatch, opened):
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: False)
    started = []
    monkeypatch.setattr(cli, "cmd_serve", lambda args: started.append(args) or 0)
    assert cli.main(["present", str(tex), str(tmp_path / "more"), "--port", "8475", "--no-tunnel"]) == 0
    (args,) = started
    assert args.bundles == [str(out), str(tmp_path / "more")] and args.port == 8475 and args.no_tunnel
    assert opened == []                                     # not before the server answers
    args.opener()
    assert opened == [("browser", f"http://localhost:8475/stage?bundle={fb.id}")]


def test_present_builds_first(tmp_path, monkeypatch, opened):
    tex, out, fb = built(tmp_path)
    t = (fb.path / "deck.json").stat().st_mtime
    touch(tex, t + 60)                                     # edited since the build
    builds = []

    def build(args):
        builds.append(args)
        os.utime(fb.path / "deck.json", (t + 120, t + 120))   # built now
        return 0
    monkeypatch.setattr(cli, "cmd_build", build)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    assert cli.main(["present", str(tex)]) == 0
    (b,) = builds
    assert (b.tex, b.output_dir, b.no_stage, b.server) == (str(tex), str(out), False, "http://localhost:8470")
    assert opened == [("browser", f"http://localhost:8470/stage?bundle={fb.id}")]
    touch(tex, t + 300)

    def checked(args):                                     # built, but the layout check failed: presented
        os.utime(fb.path / "deck.json", (t + 400, t + 400))
        return 1
    monkeypatch.setattr(cli, "cmd_build", checked)
    assert cli.main(["present", str(tex)]) == 0 and len(opened) == 2
    touch(tex, t + 500)                                    # a build that fails: nothing new to present
    monkeypatch.setattr(cli, "cmd_build", lambda args: 1)
    assert cli.main(["present", str(tex)]) == 1 and len(opened) == 2
    assert cli.main(["present", str(tex), "--no-build"]) == 0 and len(opened) == 3   # the build as it is


def test_present_without_a_powerpoint_file(tmp_path, monkeypatch, opened, capsys):
    tex, out, fb = built(tmp_path)
    (out / "Test-deck.pptx").unlink()
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    assert cli.main(["present", str(tex), "--powerpoint"]) == 2 and opened == []
    assert "no live PowerPoint file" in capsys.readouterr().err


def test_a_deck_without_a_command_is_presented(tmp_path, monkeypatch, opened):
    """texstage deck.tex - as the command texstage did before 2026-10-10 - is texstage present
    deck.tex; options may come first."""
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    assert cli.main([str(tex)]) == 0 and cli.main(["--port", "8475", str(tex)]) == 0
    assert opened == [("browser", f"http://localhost:{port}/stage?bundle={fb.id}") for port in (8470, 8475)]
    with pytest.raises(SystemExit):
        cli.main(["--help"])                                         # the commands' help, not present's


def test_a_build_has_the_stage_pdf_by_default(tmp_path, monkeypatch):
    import texstage.build.builder as builder
    seen = []

    def build(tex, out, opts):
        seen.append(opts.stage)
        raise builder.BuildError("stop here")
    monkeypatch.setattr(builder, "build", build)
    (tmp_path / "d.tex").write_text("x", encoding="utf-8")
    assert cli.main(["build", str(tmp_path / "d.tex")]) == 1
    assert cli.main(["build", str(tmp_path / "d.tex"), "--no-stage"]) == 1
    assert cli.main(["build", str(tmp_path / "d.tex"), "--stage"]) == 1     # (as before: still taken)
    assert seen == [True, False, True]


@pytest.fixture
def chapter_script(tmp_path, monkeypatch):
    """texstage-present.py, loaded here, in a lecture with the chapters 01-Test and 02-More."""
    lec = tmp_path / "lecture"
    for chapter in ("01-Test", "02-More"):
        touch(lec / chapter / "001.tex", 1_000_000)
    (lec / "notes").mkdir()                                        # not a chapter: no frames
    (lec / "dbis-style.sty").write_text("% the lecture's style", encoding="utf-8")
    monkeypatch.setenv("LECTURE_ROOT", str(lec))
    monkeypatch.syspath_prepend(str(SCRIPTS))                       # its lecture.py; sys.path back afterwards
    monkeypatch.delitem(sys.modules, "lecture", raising=False)
    spec = importlib.util.spec_from_file_location("texstage_present", SCRIPTS / "texstage-present.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return lec, script


def test_present_a_chapter(chapter_script, monkeypatch):
    """texstage-present.py <chapter>: the chapter built first if needed (texstage-build.py), then
    texstage present on its build/texquiz - every other chapter's served too."""
    lec, script = chapter_script
    out, more = (lec / c / "build" / "texquiz" for c in ("01-Test", "02-More"))
    builds, presented = [], []

    def build(cmd):
        builds.append([Path(cmd[1]).name, *cmd[2:]])
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(script, "subprocess", SimpleNamespace(run=build))
    monkeypatch.setattr(script, "texstage", lambda argv: presented.append(argv) or 0)

    def present(*args):
        monkeypatch.setattr(sys, "argv", ["texstage-present.py", *args])
        return script.main()
    assert present("01-Test", "--powerpoint", "--port", "8475") == 0         # not built yet
    assert builds == [["texstage-build.py", "01-Test", "--server", "http://localhost:8475"]]
    assert presented == [["present", str(out), str(more), "--no-build", "--powerpoint", "--port", "8475"]]
    fb = make_bundle(out, stage=True)
    os.utime(fb.path / "deck.json", (2_000_000, 2_000_000))
    touch(lec / "01-Test" / "slides.tex", 3_000_000)                         # written from the frames
    assert present("01-Test") == 0 and len(builds) == 1                      # up to date
    assert presented[-1] == ["present", str(out), str(more), "--no-build"]
    assert present("01-Test", "--build", "--no-check") == 0                  # built anyway
    assert builds[-1] == ["texstage-build.py", "01-Test", "--no-check"]
    touch(lec / "01-Test" / "001.tex", 3_000_000)                            # a frame edited, and LaTeX fails
    monkeypatch.setattr(script, "subprocess", SimpleNamespace(run=lambda cmd: SimpleNamespace(returncode=1)))
    assert present("01-Test") == 1 and len(presented) == 3                  # nothing new to present
    assert present("01-Test", "--no-build") == 0 and len(presented) == 4     # the build as it is
