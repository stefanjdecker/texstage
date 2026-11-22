# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The release (texstage M7, docs/architecture/texstage-design.md, section 22): what pyproject.toml packs,
the licence notices, no AGPL code (PyMuPDF), and a server that loads nothing of the build."""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

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
    """pyproject.toml lists its packages (the LaTeX files are mapped in as texstage.latex) and every
    folder of data that Python could import - the web pages' folders, the words and fixtures of
    texstage's own kinds: a new one must be added there, or the wheel lacks it (setuptools warns, and
    will stop packing unlisted folders)."""
    tool = PROJECT["tool"]["setuptools"]
    code = {".".join(p.parent.relative_to(SRC.parent).parts) for p in SRC.rglob("__init__.py")}
    folders = {".".join(p.relative_to(SRC.parent).parts) for p in [SRC, *SRC.rglob("*")]
               if p.is_dir() and "__pycache__" not in p.parts
               and all(part.isidentifier() for part in p.relative_to(SRC.parent).parts)}
    assert code <= folders and {"texstage.web", "texstage.activities.kinds.texts"} <= folders
    assert set(tool["packages"]) == folders | {"texstage.latex"}
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


def test_the_kinds_dependencies_are_locked_with_texstages(tmp_path, monkeypatch):
    """The kinds are installed with --no-deps - a local package has no hash to lock -: what they need but
    texstage and one another is among texstage's locked inputs, and their metadata among the files of the
    lock's manifest, so that an edit of a kind's pyproject.toml fails lock_dependencies.py --check (the plan of
    F2, package 11). The packages of kinds/ are on no index: a lock would look for them there."""
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("lock_dependencies", ROOT / "maintenance" / "lock_dependencies.py")
    lock = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lock)
    kinds = sorted((ROOT / "kinds").glob("*/pyproject.toml"))
    assert [p.parent.name for p in kinds] == ["texstage-kinds-rdf", "texstage-kinds-sql"] == [p.parent.name for p in lock.kinds()]
    runtime = (ROOT / "requirements" / "runtime.in").read_text(encoding="utf-8").splitlines()
    assert lock.kinds_dependencies() == ["pyoxigraph>=0.5.13,<0.6"] and set(lock.kinds_dependencies()) <= set(runtime)
    assert lock.inputs()["runtime"].splitlines() == runtime
    ours = {"kinds/texstage-kinds-rdf/pyproject.toml", "kinds/texstage-kinds-sql/pyproject.toml"}
    manifest = json.loads((ROOT / "requirements" / "lock-manifest.json").read_text(encoding="utf-8"))
    assert ours <= set(manifest["files"]) and ours <= set(lock.snapshot())
    # texstage itself and the kinds' own packages - however a kind writes their names - are not locked; any other
    # package is, as written (its markers too); a kind's optional dependencies are not, nor a folder deeper down
    (tmp_path / "kinds" / "a" / "deeper").mkdir(parents=True)
    (tmp_path / "kinds" / "a" / "pyproject.toml").write_text(
        '[project]\nname = "texstage-kinds-a"\ndependencies = ["texstage>=0.2.1.dev4", "TexStage", "texstage[docs]", '
        '"texstage ; python_version >= \'3.12\'", "texstage-kinds-b>=1", "rdflib>=7 ; python_version >= \'3.12\'", '
        '"texstage_extra"]\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n', encoding="utf-8")
    (tmp_path / "kinds" / "a" / "deeper" / "pyproject.toml").write_text(
        '[project]\nname = "deeper"\ndependencies = ["deep-package"]\n', encoding="utf-8")
    (tmp_path / "kinds" / "b").mkdir()
    (tmp_path / "kinds" / "b" / "pyproject.toml").write_text('[project]\nname = "Texstage_Kinds.B"\n'
                                                            'dependencies = ["TEXSTAGE-KINDS-A", "sqlparse>=0.5"]\n',
                                                            encoding="utf-8")
    monkeypatch.setattr(lock, "ROOT", tmp_path)
    assert lock.kinds_dependencies() == ["rdflib>=7 ; python_version >= '3.12'", "texstage_extra", "sqlparse>=0.5"]
    assert [p.relative_to(tmp_path).as_posix() for p in lock.kinds()] == ["kinds/a/pyproject.toml", "kinds/b/pyproject.toml"]
    # what a kind needs and texstage does not is locked too
    (tmp_path / "pyproject.toml").write_text('[build-system]\nrequires = ["setuptools>=77"]\n[project]\nname = "texstage"\n'
                                             'dependencies = ["lxml>=5"]\n[project.optional-dependencies]\ndev = ["pytest>=8"]\n',
                                             encoding="utf-8")
    assert lock.inputs()["runtime"] == "lxml>=5\nrdflib>=7 ; python_version >= '3.12'\nsqlparse>=0.5\ntexstage_extra\n"


def test_a_distributions_build_takes_away_what_it_left_and_nothing_else(tmp_path):
    """maintenance/check_distributions.py builds in the source folders: what the build leaves there - build/, an
    *.egg-info, which hides an installed package's entry points where its folder comes first on sys.path - goes
    again, also when the build fails; what was there before stays (a developer's build/, an editable install's
    metadata)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_distributions", ROOT / "maintenance" / "check_distributions.py")
    dist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dist)
    assert dist.packages() == [ROOT, ROOT / "kinds" / "texstage-kinds-rdf", ROOT / "kinds" / "texstage-kinds-sql"]
    old, new = tmp_path / "old", tmp_path / "new"
    for source in (old, new):
        (source / "src").mkdir(parents=True)
    (old / "build").mkdir()
    (old / "build" / "mine.txt").write_text("a developer's", encoding="utf-8")
    (old / "src" / "old.egg-info").mkdir()
    for source in (old, new):
        with dist.cleaned(source):
            for made in ("build/lib", "src/made.egg-info", "made.egg-info"):
                (source / made).mkdir(parents=True, exist_ok=True)
    assert (old / "build" / "mine.txt").is_file() and (old / "src" / "old.egg-info").is_dir()
    assert not any((source / made).exists() for source in (old, new) for made in ("src/made.egg-info", "made.egg-info"))
    assert not (new / "build").exists()
    with pytest.raises(RuntimeError), dist.cleaned(new):                   # a build that fails midway
        (new / "build").mkdir()
        raise RuntimeError("the build failed")
    assert not (new / "build").exists()


def test_the_installed_metadata_is_this_texstages():
    """An editable install keeps the version it was installed with: after a pull that changes texstage's
    version, `texstage kinds` and deck.json's kinds say the old one until it is installed anew. pip check does
    not notice - the kinds need 0.2.1.dev4 or later, which the old one still is -: this test does
    (docs/development.md)."""
    from importlib.metadata import version
    import texstage
    assert version("texstage") == texstage.__version__ == PROJECT["project"]["version"], \
        "the installed texstage's metadata is another version's: python -m pip install --no-deps --no-build-isolation -e ."


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
