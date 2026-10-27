# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Compile a Beamer deck with texquiz.sty in one of its three modes."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

def latex_dir() -> Path:
    """Where texquiz.sty is: in an installed package texstage/latex/ (pyproject.toml maps the
    repository's latex/ there), in a checkout of lecture-tools its latex/ folder."""
    packaged = Path(__file__).resolve().parents[1] / "latex"
    return packaged if (packaged / "texquiz.sty").is_file() else Path(__file__).resolve().parents[3] / "latex"


LATEX_DIR = latex_dir()
MODES = ("handout", "solutions", "present")
EXTRA_PASSES = 2                 # at most, after the passes asked for, while the log asks for one
RERUN = re.compile(r"Rerun to get|Label\(s\) may have changed|^No file \S+\.(?:aux|nav)\.$", re.MULTILINE)


class LatexError(RuntimeError):
    """pdflatex failed; the message carries the first error of the log."""


@dataclass
class CompileResult:
    pdf: Path
    log: Path
    tqz: Path | None
    overfull: int


def compile_deck(tex: Path, mode: str, out_dir: Path, *, notes: bool | str = False,
                 jobname: str | None = None, passes: int = 2,
                 explicit_mode: bool = True) -> CompileResult:
    """Run pdflatex `passes` times next to the source (so relative paths keep
    working) and write all output to `out_dir`.  Returns the PDF and, in present
    mode, the .tqz metadata file.  notes=True: every page holds the slide and its
    note page, typeset for text extraction (notes.py); notes="stage": the deck's own
    note pages, each a page of its own after its slide (texstage).  explicit_mode=False
    compiles like a plain pdflatex run (the package then picks its default mode itself)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if notes not in (False, True, "stage"):
        raise ValueError(f"notes must be False, True or 'stage', not {notes!r}")
    if shutil.which("pdflatex") is None:
        raise LatexError("pdflatex is not on PATH")
    tex = tex.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    jobname = jobname or f"{tex.stem}-{mode}"
    flags = (rf"\def\texquizmode{{{mode}}}" if explicit_mode else "") \
        + (r"\def\texquiznotes{stage}" if notes == "stage" else r"\def\texquiznotes{}" if notes else "")
    cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
           f"-output-directory={out_dir}", f"-jobname={jobname}", flags + rf"\input{{{tex.name}}}"]
    env = dict(os.environ)
    env["TEXINPUTS"] = str(LATEX_DIR) + os.pathsep + env.get("TEXINPUTS", "")
    env.setdefault("max_print_line", "10000")   # unwrapped log lines
    log = out_dir / f"{jobname}.log"

    def run():
        r = subprocess.run(cmd, cwd=tex.parent, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise LatexError(first_error(log) or r.stdout[-2000:])
    for _ in range(passes):
        run()
    for _ in range(EXTRA_PASSES if passes > 1 else 0):     # a settled document was asked for
        if not wants_rerun(log):
            break
        run()
    tqz = out_dir / f"{jobname}.tqz"
    return CompileResult(out_dir / f"{jobname}.pdf", log, tqz if mode == "present" else None,
                         count_overfull(log))


def wants_rerun(log: Path) -> bool:
    """The last pass's log asks for another one: cross-references or Beamer's navigation not
    settled, or the .aux or .nav the pass before wrote not read - on Windows a virus scanner may
    still hold a file just written, and the pass then typesets as a first one (frame totals 1,
    references ??, and a new bundle ID for the same source)."""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(RERUN.search(text))


def first_error(log: Path) -> str:
    """The first error of a LaTeX log with a few lines of context."""
    if not log.exists():
        return ""
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!") or re.match(r"^[^:]+:\d+: ", line):
            return "\n".join(lines[i:i + 8])
    return ""


def count_overfull(log: Path) -> int:
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    return len(re.findall(r"^Overfull \\[hv]box", text, re.M))
