# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Compile a Beamer deck with texquiz.sty in one of its three modes."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .compiler import RERUN_PATTERN, compile_latex, plain

def latex_dir() -> Path:
    """Where texquiz.sty is: in an installed package texstage/latex/ (pyproject.toml maps the
    repository's latex/ there), or the Texstage checkout's latex/ folder."""
    packaged = Path(__file__).resolve().parents[1] / "latex"
    return packaged if (packaged / "texquiz.sty").is_file() else Path(__file__).resolve().parents[3] / "latex"


LATEX_DIR = latex_dir()
MODES = ("handout", "solutions", "present")
EXTRA_PASSES = 2                 # at most, after the passes asked for, while the log asks for one
RERUN = re.compile(RERUN_PATTERN, re.MULTILINE)
UNDEFINED = re.compile(r"^LaTeX Warning: (?:Reference|Citation) [`'](.*?)' on page", re.MULTILINE)   # (... undefined)


class LatexError(RuntimeError):
    """pdflatex failed; the message carries the first error of the log."""


@dataclass
class CompileResult:
    pdf: Path
    log: Path
    tqz: Path | None
    overfull: int
    unsettled: str | None = None        # the last pass's line that asks for another, when none was left
    undefined: tuple[str, ...] = ()     # the references (and citations) the last pass left ??


def compile_deck(tex: Path, mode: str, out_dir: Path, *, notes: bool | str = False,
                 jobname: str | None = None, passes: int = 2,
                 explicit_mode: bool = True) -> CompileResult:
    """Run pdflatex `passes` times next to the source (so relative paths keep
    working) and write all output to `out_dir`.  Returns the PDF and, in present
    mode, the .tqz metadata file.  notes=True: every page holds the slide and its
    note page, typeset for text extraction (notes.py); notes="stage": the deck's own
    note pages, each a page of its own after its slide (texstage).  explicit_mode=False
    compiles like a plain pdflatex run (the package then picks its default mode itself). The result says
    what the last pass left unsettled, which a build must not ship silently: its line that still asks for
    another pass (wants_rerun) when no pass was left, and the references it left undefined."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if notes not in (False, True, "stage"):
        raise ValueError(f"notes must be False, True or 'stage', not {notes!r}")
    if shutil.which("pdflatex") is None:
        raise LatexError("pdflatex is not on PATH")
    tex = plain(tex)
    out_dir = plain(out_dir)                # (not \\?\C:\..., which a compile beside this one can make it)
    out_dir.mkdir(parents=True, exist_ok=True)
    jobname = jobname or f"{tex.stem}-{mode}"
    flags = (rf"\def\texquizmode{{{mode}}}" if explicit_mode else "") \
        + (r"\def\texquiznotes{stage}" if notes == "stage" else r"\def\texquiznotes{}" if notes else "")
    result = compile_latex(
        tex, output_dir=out_dir, jobname=jobname, preamble=flags,
        passes=passes, extra_passes=EXTRA_PASSES if passes > 1 else 0,
        file_line_error=True, texinputs=(LATEX_DIR,), output_encoding="utf-8",
        env={"max_print_line": os.environ.get("max_print_line", "10000")},
    )
    log = result.log
    if result.returncode:
        raise LatexError(first_error(log) or result.stdout[-2000:])
    tqz = out_dir / f"{jobname}.tqz"
    return CompileResult(out_dir / f"{jobname}.pdf", log, tqz if mode == "present" else None,
                         count_overfull(log),
                         wants_rerun(result.log_text) if passes > 1 else None,    # (one pass asked for: a draft)
                         tuple(dict.fromkeys(UNDEFINED.findall(result.log_text))))


def wants_rerun(log: str) -> str | None:
    r"""The line of a pass's log (its text) that asks for another pass, None if none does: cross-references
    or Beamer's navigation not settled, or the .aux or .nav the pass before wrote not read - on Windows a
    virus scanner may still hold a file just written, or pdflatex was given its output folder as \\?\C:\...
    (compiler.plain), and the pass then typesets as a first one (frame totals 1, references ??, and a new
    bundle ID for the same source)."""
    found = RERUN.search(log)
    if found is None:
        return None
    start = log.rfind("\n", 0, found.start()) + 1
    end = log.find("\n", found.end())
    return log[start:end if end >= 0 else len(log)].strip()


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
