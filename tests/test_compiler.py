# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Shared engine contracts, independent of course assembly and live deck modes."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from texstage.api import LatexResult, compile_latex
from texstage.build import compiler
from texstage.build.pdf import Pdf


def test_compilation_api_stays_lightweight():
    result = subprocess.run([sys.executable, "-c", "import sys; "
                            "from texstage.api import compile_latex, LatexResult; "
                            "assert not any(m.startswith(('pypdfium2', 'texstage.server', 'pptx', 'PIL')) for m in sys.modules)"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("engine", ["pdflatex", "latexmk"])
def test_real_compilation_keeps_paths_styles_and_source(tmp_path, monkeypatch, engine):
    if shutil.which(engine) is None or shutil.which("pdflatex") is None:
        pytest.skip(f"needs {engine}/pdflatex")
    source_dir = tmp_path / "source folder"
    source_dir.mkdir()
    source = source_dir / "a document.tex"
    source.write_text(r"\documentclass{article}\usepackage{fixture}\begin{document}\input{body.tex}\end{document}")
    (source_dir / "body.tex").write_text("Relative include. \\fixtureword")
    styles = tmp_path / "style folder"
    styles.mkdir()
    (styles / "fixture.sty").write_text(r"\ProvidesPackage{fixture}\newcommand{\fixtureword}{Provided style.}")
    original = source.read_bytes()
    elsewhere = tmp_path / "caller"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    before_env = os.environ.copy()
    result = compile_latex(source, engine=engine, output_dir="outputs", jobname="custom name",
                           texinputs=(styles,))
    assert isinstance(result, LatexResult) and result.returncode == 0, result.stdout + result.stderr
    assert result.passes_run == 1
    assert result.pdf == elsewhere / "outputs/custom name.pdf"
    assert result.aux.is_file() and result.log.is_file()
    assert result.nav == elsewhere / "outputs/custom name.nav"
    assert result.log_text
    with Pdf(result.pdf) as doc:
        assert "Relative include. Provided style." in doc[0].text()
    assert source.read_bytes() == original
    assert set(p.name for p in source_dir.iterdir()) == {source.name, "body.tex"}
    assert os.environ == before_env


def fake_engine(monkeypatch, tmp_path, logs, *, returncodes=None):
    source = tmp_path / "plain.tex"
    source.write_text(r"\documentclass{article}\begin{document}Hello.\end{document}")
    calls = []
    monkeypatch.setattr(compiler.shutil, "which", lambda name: name)
    def run(command, **kwargs):
        calls.append((command, kwargs))
        index = len(calls) - 1
        (tmp_path / "plain.log").write_text(logs[min(index, len(logs) - 1)])
        return SimpleNamespace(returncode=returncodes[index] if returncodes else 0,
                               stdout=f"pass {index + 1}", stderr="engine diagnostic")
    monkeypatch.setattr(compiler.subprocess, "run", run)
    return source, calls


def test_bounded_passes_stop_when_references_settle(tmp_path, monkeypatch):
    source, calls = fake_engine(monkeypatch, tmp_path, ["Rerun to get cross-references right.",
                                                      "Label(s) may have changed", "settled"])
    progress = []
    result = compile_latex(source, passes=2, extra_passes=2,
                           on_pass=lambda index, total: progress.append((index, total)))
    assert result.passes_run == len(calls) == 3
    assert progress == [(1, 4), (2, 4), (3, 4)]
    assert result.log_text == "settled" and result.stdout == "pass 3"


def test_reruns_are_bounded_and_failures_stop_immediately(tmp_path, monkeypatch):
    source, calls = fake_engine(monkeypatch, tmp_path, ["Rerun to get references"])
    assert compile_latex(source, extra_passes=2).passes_run == len(calls) == 3
    source, calls = fake_engine(monkeypatch, tmp_path, ["Rerun to get references", "! Broken."], returncodes=[0, 1])
    result = compile_latex(source, passes=2, extra_passes=2)
    assert result.returncode == 1 and result.passes_run == len(calls) == 2
    assert result.log_text == "! Broken." and result.stderr == "engine diagnostic"


def test_notes_policy_does_not_force_extra_passes(tmp_path, monkeypatch):
    source, calls = fake_engine(monkeypatch, tmp_path, ["Label(s) may have changed"])
    result = compile_latex(source, preamble=r"\def\exampleNotes{}", extra_passes=2,
                           rerun_pattern="Rerun to get")
    assert result.passes_run == len(calls) == 1
    assert calls[0][0][-1] == r"\def\exampleNotes{}\input{plain.tex}"
    assert "shell" not in calls[0][1]


def test_defaults_preserve_environment_without_injecting_styles(tmp_path, monkeypatch):
    source, calls = fake_engine(monkeypatch, tmp_path, ["settled"])
    monkeypatch.setenv("TEXINPUTS", "existing-search-path")
    monkeypatch.setenv("max_print_line", "79")
    compile_latex(source)
    command, options = calls[0]
    assert command[-1] == source.name and not any("jobname=" in word for word in command)
    assert options["cwd"] == source.parent
    assert options["env"]["TEXINPUTS"] == "existing-search-path"
    assert {k.casefold(): v for k, v in options["env"].items()}["max_print_line"] == "79"
    compile_latex(source, env={"max_print_line": "10000"})
    assert {k.casefold(): v for k, v in calls[-1][1]["env"].items()}["max_print_line"] == "10000"
    assert os.environ["max_print_line"] == "79"


@pytest.mark.parametrize("options", [{"engine": "unknown"}, {"passes": 0}, {"extra_passes": -1},
                                     {"jobname": "../escape"}, {"engine": "latexmk", "preamble": r"\def\x{}"},
                                     {"engine": "latexmk", "extra_passes": 1}])
def test_bad_options_fail_before_creating_outputs(tmp_path, options):
    with pytest.raises(ValueError):
        compile_latex(tmp_path / "absent.tex", output_dir=tmp_path / "output", **options)
    assert not list(tmp_path.iterdir())


def test_missing_source_and_tool_are_actionable(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError, match="source not found"):
        compile_latex(tmp_path / "absent.tex", output_dir=tmp_path / "output")
    source = tmp_path / "present.tex"
    source.touch()
    monkeypatch.setattr(compiler.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError, match="latexmk is not on PATH"):
        compile_latex(source, engine="latexmk", output_dir=tmp_path / "output")
    assert not (tmp_path / "output").exists()
