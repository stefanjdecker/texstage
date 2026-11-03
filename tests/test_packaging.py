# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The release (texstage M7, docs/texstage-design.md, section 22): what pyproject.toml packs,
the licence notices, no AGPL code (PyMuPDF), and a server that loads nothing of the build."""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "texstage"
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
# the LaTeX packages the wheel carries (latex/dbis-slides.sty is the lectures', not texstage's)
STYLES = ["texstage.sty", "texquiz.sty", "texvideo.sty", "texactivity.sty"]
# Moving the pre-existing course converter does not grant it an Apache license.
# NOTICE preserves its original unresolved status until the rights holders decide.
LEGACY_CONVERTER = SRC / "build" / "beamer.py"


def own_sources():
    """The files the Apache-2.0 notice covers that carry a header (NOTICE)."""
    for p in sorted(SRC.rglob("*")):
        if p.is_file() and p.suffix in (".py", ".js", ".css", ".html") and "vendor" not in p.parts \
                and "__pycache__" not in p.parts and p != LEGACY_CONVERTER:
            yield p
    yield from (ROOT / "latex" / n for n in STYLES)
    yield from sorted((ROOT / "scripts").glob("texstage-*.py"))
    yield from sorted((ROOT / "tests").glob("*.py"))


def test_the_packages_are_all_listed():
    """pyproject.toml lists its packages (the LaTeX files are mapped in as texstage.latex) and the
    web pages' folders that Python could import: a new one must be added there, or the wheel
    lacks it (setuptools warns, and will stop packing unlisted folders)."""
    tool = PROJECT["tool"]["setuptools"]
    code = {".".join(p.parent.relative_to(SRC.parent).parts) for p in SRC.rglob("__init__.py")}
    web = {".".join(p.relative_to(SRC.parent).parts) for p in [SRC / "web", *(SRC / "web").rglob("*")]
           if p.is_dir() and "__pycache__" not in p.parts
           and all(part.isidentifier() for part in p.relative_to(SRC.parent).parts)}
    assert set(tool["packages"]) == code | web | {"texstage.latex"}
    assert tool["package-dir"]["texstage.latex"] == "latex"
    assert PROJECT["tool"]["setuptools"]["package-data"]["texstage.latex"] == STYLES


def test_licence_and_headers():
    meta = PROJECT["project"]
    assert meta["license"] == "Apache-2.0" and {"LICENSE", "NOTICE"} <= set(meta["license-files"])
    assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")[:200]
    missing = [p.relative_to(ROOT).as_posix() for p in own_sources()
               if "SPDX-License-Identifier: Apache-2.0" not in p.read_text(encoding="utf-8")[:400]]
    assert not missing
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert LEGACY_CONVERTER.is_file()
    assert LEGACY_CONVERTER.relative_to(ROOT).as_posix() in notice
    assert "moving it does not relicense it" in notice
    assert "original license was not" in notice
    assert "see NOTICE" in LEGACY_CONVERTER.read_text(encoding="utf-8")[:400]
    for folder in (SRC / "web" / "vendor").iterdir():
        if folder.is_dir():
            assert list(folder.glob("LICENSE*")), folder.name               # each vendored library's licence
    for name in ("PDF.js", "perfect-freehand", "pdf-lib", "KaTeX", "Oxigraph", "sql.js"):
        assert name in notice


def test_no_pymupdf():
    """PyMuPDF is AGPL: neither a dependency nor imported anywhere (PDFium does its work)."""
    assert not [d for d in PROJECT["project"]["dependencies"] if d.lower().startswith(("pymupdf", "fitz"))]
    pattern = re.compile(r"^\s*(import|from)\s+(pymupdf|fitz)\b", re.MULTILINE)
    users = [p.relative_to(ROOT).as_posix() for folder in ("src", "scripts", "tools", "tests")
             for p in (ROOT / folder).rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert not users


def test_the_commands():
    """texstage (texstage <deck> without a command presents it: tests/test_present.py). The
    package is texstage; its old name texquiz - the command, the scripts - went on 2026-10-11."""
    assert PROJECT["project"]["name"] == "texstage"
    assert PROJECT["project"]["scripts"] == {"texstage": "texstage.cli:main"}
    assert not (ROOT / "src" / "texquiz").exists() and not list((ROOT / "scripts").glob("texquiz-*.py"))


def test_the_docker_image_packs_the_latex_files():
    """deploy/Dockerfile builds the package from the files it copies: every LaTeX package the
    wheel carries (pyproject.toml) is among them."""
    docker = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    copied = re.search(r"^COPY (.*) \./latex/$", docker, re.MULTILINE)[1].split()
    assert sorted(Path(c).name for c in copied) == sorted(STYLES)


def test_one_place_for_port_and_data_folder(tmp_path, monkeypatch):
    """The commands, the presenter keys and the build take the laptop server's port and data
    folder from texstage/__init__.py: 8470 and ~/.texstage - or ~/.texquiz, its name until
    2026-10-10, where only that one exists (nothing is moved). The database in it keeps its name."""
    import texstage
    from texstage import cli, keys
    assert texstage.DEFAULT_PORT == 8470 and texstage.DEFAULT_DATA == texstage.data_folder(Path.home())
    assert texstage.DEFAULT_SERVER == "http://localhost:8470" and keys.DATA == texstage.DEFAULT_DATA
    home = tmp_path / "home"
    assert texstage.data_folder(home) == home / ".texstage"                    # a new machine
    (home / ".texquiz").mkdir(parents=True)
    assert texstage.data_folder(home) == home / ".texquiz"                     # a laptop of before
    (home / ".texstage").mkdir()
    assert texstage.data_folder(home) == home / ".texstage"
    assert 'data_dir / "texquiz.sqlite3"' in (SRC / "server" / "app.py").read_text(encoding="utf-8")
    served, built = [], []
    monkeypatch.setattr(cli, "server_up", lambda port: False)            # (not the server that may run here)
    monkeypatch.setattr(cli, "cmd_serve", lambda args: served.append(args.port) or 0)
    monkeypatch.setattr(cli, "cmd_build", lambda args: built.append(args.server) or 1)
    assert cli.main(["serve"]) == 0 and cli.main(["present", str(tmp_path)]) == 0 and cli.main([str(tmp_path)]) == 0
    assert served == [8470] * 3
    (tmp_path / "deck.tex").write_text("x", encoding="utf-8")
    cli.main(["present", str(tmp_path / "deck.tex")])
    assert built == ["http://localhost:8470"]
    literal = re.compile(r"""["']\.texquiz["']|\b8470\b""")
    assert not [p.name for p in (SRC / "cli.py", SRC / "keys.py") if literal.search(p.read_text(encoding="utf-8"))]


def test_the_server_loads_nothing_of_the_build():
    """texstage serve (and the Docker image) never needs LaTeX, PDFium, Pillow or python-pptx -
    only the bundle format (texstage.build.bundle and the .tqz reader it names, plain Python)."""
    code = ("import sys, texstage.cli, texstage.server.app; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('pypdfium2', 'pptx', 'PIL', 'lxml') "
            "or (m.startswith('texstage.build.') and m not in ('texstage.build.bundle', 'texstage.build.tqz'))))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"
