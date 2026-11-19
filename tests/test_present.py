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



def touch(path: Path, t: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("x", encoding="utf-8")
    os.utime(path, (t, t))


def built(tmp_path: Path, name: str = "talk"):
    """A deck and its up-to-date build (with the stage PDF and the live PowerPoint file), named as the
    build names them: <out>/<name>.bundle and <name>.pptx for <name>.tex."""
    out = tmp_path / "talk" / "texquiz-out"
    fb = make_bundle(out, deck=name, stage=True, title=name)
    (out / f"{name}.pptx").write_bytes(b"pptx")
    tex = tmp_path / "talk" / f"{name}.tex"
    touch(tex, (fb.path / "deck.json").stat().st_mtime - 60)
    return tex, out, fb


@pytest.fixture(autouse=True)
def no_server(monkeypatch):
    """No test asks a real server on this machine's port (the one a lecture may run): a server that runs
    is the test's own, through cli.local_api."""
    monkeypatch.setattr(cli, "local_api", lambda *args, **kwargs: (None, None))


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


def test_present_on_a_server_that_runs_says_its_checks_options_are_for_a_server_it_starts(tmp_path, monkeypatch,
                                                                                          opened, capsys):
    """--checks (and --workers, --max-players) while a server runs that checks otherwise: present says which
    mode the running one has, and that those options are for a server it starts (the package 4 review: they
    went unsaid)."""
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    monkeypatch.setattr(cli, "server_checks", lambda port: "browser")
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("the build is up to date"))
    monkeypatch.setattr(cli, "cmd_serve", lambda args: pytest.fail("a server runs already"))
    assert cli.main(["present", str(tex), "--checks", "server"]) == 0
    assert "it checks with --checks browser: --checks, --workers and --max-players" in capsys.readouterr().out
    assert cli.main(["present", str(tex), "--checks", "browser"]) == 0
    assert "--checks" not in capsys.readouterr().out
    assert cli.main(["present", str(tex), "--workers", "2"]) == 0
    assert "it checks with --checks browser" in capsys.readouterr().out


def test_present_on_the_server_that_runs(tmp_path, monkeypatch, opened):
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("the build is up to date"))
    monkeypatch.setattr(cli, "cmd_serve", lambda args: pytest.fail("a server runs already"))
    assert cli.main(["present", str(tex)]) == 0
    assert opened == [("browser", f"http://localhost:8470/stage?bundle={fb.id}")]   # this deck, at once
    assert cli.main(["present", str(out), "--powerpoint"]) == 0            # a build folder, with PowerPoint
    assert opened[-1] == ("file", "talk.pptx")


def test_present_takes_a_build_folder_itself_an_older_build_too(tmp_path, monkeypatch, opened):
    """A rollback from the command line: texstage present names a build folder itself - <name>.bundle, an older
    build kept elsewhere, a server's kept copy - and that build is presented (?bundle=), not its output
    folder's newest. A running server finds a folder outside its data folder by builds.json; a server's own
    copies and uploads are never recorded there (a build folder is open to every lecturer)."""
    import json
    tex, out, fb = built(tmp_path)
    data = tmp_path / "data"
    old = make_bundle(tmp_path / "kept", deck="talk", time=30, title="talk")     # an older build, kept elsewhere
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("a build folder is presented as it is"))
    monkeypatch.setattr(cli, "cmd_serve", lambda args: pytest.fail("a server runs already"))
    assert cli.main(["present", str(old.path), "--data", str(data)]) == 0
    assert opened[-1] == ("browser", f"http://localhost:8470/stage?bundle={old.id}")
    assert json.loads((data / "builds.json").read_text(encoding="utf-8")) == [str(old.path.resolve())]
    assert cli.main(["present", str(fb.path), "--powerpoint", "--data", str(data)]) == 0     # its PowerPoint file
    assert opened[-1] == ("file", "talk.pptx")
    copy = data / "served" / "talk" / old.id                                        # a server's kept copy
    shutil.copytree(old.path, copy)
    assert cli.main(["present", str(copy), "--data", str(data)]) == 0
    assert opened[-1] == ("browser", f"http://localhost:8470/stage?bundle={old.id}")
    assert str(copy.resolve()) not in json.loads((data / "builds.json").read_text(encoding="utf-8"))
    assert cli.main(["present", str(copy), "--powerpoint", "--data", str(data)]) == 2       # (a copy has no PPTX)
    started = []
    monkeypatch.setattr(cli, "server_up", lambda port: False)
    monkeypatch.setattr(cli, "cmd_serve", lambda args: started.append(args) or 0)
    assert cli.main(["present", str(old.path), "--no-tunnel", "--data", str(data)]) == 0
    assert started[-1].bundles == [str(old.path)]                                   # served: that folder
    started[-1].opener()
    assert opened[-1] == ("browser", f"http://localhost:8470/stage?bundle={old.id}")


def test_present_starts_the_server(tmp_path, monkeypatch, opened):
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: False)
    started = []
    monkeypatch.setattr(cli, "cmd_serve", lambda args: started.append(args) or 0)
    assert cli.main(["present", str(tex), str(tmp_path / "more"), "--port", "8475", "--no-tunnel"]) == 0
    (args,) = started
    assert args.bundles == [str(out), str(tmp_path / "more")] and args.port == 8475 and args.no_tunnel
    assert args.activities is None                          # (serve: the default, the core's)
    assert opened == []                                     # not before the server answers
    args.opener()
    assert opened == [("browser", f"http://localhost:8475/stage?bundle={fb.id}")]
    assert cli.main(["present", str(tex), "--no-tunnel", "--activities", "core"]) == 0
    assert started[-1].activities == "core"                 # handed on to serve
    assert cli.main(["present", str(tex), "--no-tunnel", "--activities", "f1"]) == 0
    assert started[-1].activities == "f1"


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


def test_present_says_what_its_build_warned_of(tmp_path, monkeypatch, opened, capsys):
    """A build records what it warned of (built.json), and texstage present says it again, whichever build it
    presents - the deck's newest, a build folder's, a build folder itself, one built just now - before it opens
    the deck or starts a server. Until 2026-11-19 only the build's own output said it: a lecturer who had not
    read that, or presented a build made days before, presented ?? on the slides unwarned."""
    import json
    import time
    tex, out, fb = built(tmp_path)
    data = str(tmp_path / "data")                            # (a build folder itself is recorded there)
    said = ["the slides (talk-present.pdf): 1 reference undefined, ?? on the pages: sl:intro:goals",
            "video clip: clip.webm plays in the browser, but PowerPoint wants MP4 (H.264, AAC)"]
    made = 1_700_000_000_000
    (fb.path / "built.json").write_text(json.dumps({"built": made, "warnings": said}), encoding="utf-8")
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(made / 1000))
    warned = f"texstage present: this build ({when}) warned when it was made:\n" + "".join(f"  warning: {w}\n"
                                                                                          for w in said)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("the build is up to date"))
    assert cli.main(["present", str(tex)]) == 0
    assert capsys.readouterr().out.startswith(warned + "texstage present: the quiz server on this machine runs")
    assert cli.main(["present", str(out), "--powerpoint"]) == 0                  # a build folder: its newest
    assert capsys.readouterr().out.startswith(warned)
    assert cli.main(["present", str(fb.path), "--data", data]) == 0              # a build folder itself
    assert capsys.readouterr().out.startswith(warned)
    assert len(opened) == 3

    t = (fb.path / "deck.json").stat().st_mtime
    touch(tex, t + 60)                                                           # built again: its own warnings

    def build(args):
        print("  warning: (the build's own output)")
        (fb.path / "built.json").write_text(json.dumps({"built": "soon", "warnings": said[:1]}), encoding="utf-8")
        os.utime(fb.path / "deck.json", (t + 120, t + 120))
        return 0
    monkeypatch.setattr(cli, "cmd_build", build)
    assert cli.main(["present", str(tex)]) == 0
    out_now = capsys.readouterr().out                        # (said again below the build's: its last word)
    assert ("(the build's own output)\ntexstage present: this build warned when it was made:\n"   # (no time: none
            f"  warning: {said[0]}\ntexstage present: the quiz server") in out_now                # that reads)

    (fb.path / "built.json").write_text(json.dumps({"built": made}), encoding="utf-8")   # one that warned of nothing
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("the build is up to date"))
    assert cli.main(["present", str(tex)]) == 0
    assert "warn" not in capsys.readouterr().out
    (fb.path / "built.json").unlink()                                            # one made before the record
    assert cli.main(["present", str(tex)]) == 0
    assert "warn" not in capsys.readouterr().out

    (fb.path / "built.json").write_text(json.dumps({"built": made, "warnings": said}), encoding="utf-8")
    monkeypatch.setattr(cli, "server_up", lambda port: False)                    # a server present starts: said
    started = []                                                                 # before it starts
    monkeypatch.setattr(cli, "cmd_serve", lambda args: started.append(capsys.readouterr().out) or 0)
    assert cli.main(["present", str(tex), "--no-tunnel"]) == 0
    assert started == [warned]


def test_present_without_a_powerpoint_file(tmp_path, monkeypatch, opened, capsys):
    tex, out, fb = built(tmp_path)
    (out / "talk.pptx").unlink()
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






def test_present_opens_its_own_deck_where_decks_share_a_build_folder(tmp_path, monkeypatch, opened):
    """The decks of one folder share its texquiz-out: present of the one never built builds it - another
    deck's build there is not its own - and each opens its own build, not the folder's newest (the review
    of 2026-11-14: present week01.tex built nothing and opened week02)."""
    tex2, out, week2 = built(tmp_path, "week02")
    tex1 = tmp_path / "talk" / "week01.tex"
    t = (week2.path / "deck.json").stat().st_mtime
    touch(tex1, t - 60)
    assert cli.needs_build(tex1.parent, out, name="week01") == "not built yet"
    assert cli.needs_build(tex1.parent, out) is None                    # (the folder's newest build: week02's)
    made = []

    def build(args):
        week1 = make_bundle(out, deck="week01", stage=True, title="week01")
        os.utime(week1.path / "deck.json", (t + 60, t + 60))            # built after week02
        made.append((Path(args.tex).name, week1.id))
        return 0
    monkeypatch.setattr(cli, "cmd_build", build)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    assert cli.main(["present", str(tex1)]) == 0
    ((name, week1),) = made
    assert name == "week01.tex" and opened[-1] == ("browser", f"http://localhost:8470/stage?bundle={week1}")
    assert cli.main(["present", str(tex2)]) == 0 and len(made) == 1      # week02: its own build, as it is
    assert opened[-1] == ("browser", f"http://localhost:8470/stage?bundle={week2.id}")
    assert cli.built_deck(out)[0] == week1                               # (a build folder alone: its newest)


class Running:
    """The quiz server that runs on this machine's port, as cli.local_api asks it: path -> (status, JSON)."""

    def __init__(self, answers: dict):
        self.answers = answers

    def __call__(self, port, path, key=None, timeout=10.0):
        return self.answers.get(path, (None, None))


def test_present_on_a_running_server_says_what_it_cannot_apply_and_why_the_deck_is_not_there(
        tmp_path, monkeypatch, opened, capsys):
    """The server that runs already is used as it is: present says which of its options that server does not
    take (--activities, the tunnel's, the addresses', further folders), asks it with this machine's key
    whether it lists the deck's build - or why not: a deck it does not play (its reason), a build it has
    and does not list, one it does not have -, and says when the build would end a game of another build
    with players (the review of 2026-11-14: --activities and the rest went unsaid, and the deck page opened
    without the deck)."""
    tex, out, fb = built(tmp_path)
    monkeypatch.setattr(cli, "server_up", lambda port: True)
    monkeypatch.setattr(cli, "cmd_build", lambda args: pytest.fail("the build is up to date"))
    why = "the activity a1 is of the kind choice, which F1's activity type does not run"
    running = Running({"/api/status": (200, {"server": "texstage", "activities": "f1", "checks": "browser"}),
                       "/api/presenter-key": (200, {"key": "local-key"}), "/api/decks": (200, []),
                       "/api/skipped": (200, [{"bundle": fb.id, "deck": "talk", "error": why}])})
    monkeypatch.setattr(cli, "local_api", running)
    more = str(tmp_path / "more")
    assert cli.main(["present", str(tex), more, "--activities", "core", "--tunnel", "hall"]) == 0
    said = capsys.readouterr().out
    assert "it runs the activity type f1: --activities core is for a server that present starts" in said
    assert "--tunnel: for a server that present starts" in said and f"not {more}" in said
    assert f"it does not play this deck: {why}" in said
    assert opened == [("browser", f"http://localhost:8470/stage?bundle={fb.id}")]    # its window says why, too
    running.answers["/api/skipped"] = (200, [])
    running.answers[f"/api/deck/{fb.id}"] = (200, {"bundle": fb.id})
    assert cli.main(["present", str(tex), "--activities", "f1"]) == 0                # the type it runs: unsaid
    said = capsys.readouterr().out
    assert "activity type" not in said and "it has this build but does not list it" in said
    running.answers[f"/api/deck/{fb.id}"] = (404, None)
    assert cli.main(["present", str(tex)]) == 0                # no type asked for: F1's is not the default
    said = capsys.readouterr().out
    assert "it does not have this build" in said
    assert ("it runs the activity type f1, not the default, core - for the default, stop the running server "
            "(Ctrl+C in its window), then present again") in said
    running.answers["/api/status"] = (200, {"server": "texstage", "activities": "core", "checks": "server"})
    assert cli.main(["present", str(tex)]) == 0                # the default's: unsaid
    assert "activity type" not in capsys.readouterr().out
    running.answers["/api/decks"] = (200, [                                          # listed - and the deck's game
        {"bundle": fb.id, "deck": "talk", "built": 0, "game": None},                  # on the build before
        {"bundle": "0123456789abcdef", "deck": "talk", "built": 1_800_000_000_000,
         "game": {"pin": "123456", "players": 87, "session": "s"}}])
    assert cli.main(["present", str(tex)]) == 0
    said = capsys.readouterr().out
    assert "does not" not in said and "(PIN 123456, 87 players): the presenter window asks before" in said
    assert cli.main(["present", str(tex), "--powerpoint"]) == 0
    assert "the live slides of this PowerPoint file end it" in capsys.readouterr().out
    running.answers["/api/presenter-key"] = (403, None)                               # no key for present: not asked
    assert cli.main(["present", str(tex)]) == 0
    assert "PIN" not in capsys.readouterr().out
