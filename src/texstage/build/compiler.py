# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""LaTeX engine execution, independent of deck modes and course structure."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess

RERUN_PATTERN = r"Rerun to get|Label\(s\) may have changed|^No file \S+\.(?:aux|nav)\.$"


@dataclass(frozen=True)
class LatexResult:
    """The last engine invocation and its output locations, also on failure.

    A nonzero returncode means the caller must not use the PDF as a new build.
    Output paths can name missing or older files when the engine failed.
    passes_run counts invocations here, not latexmk's internal engine passes.
    """
    pdf: Path
    log: Path
    returncode: int
    stdout: str
    stderr: str
    log_text: str
    passes_run: int

    @property
    def aux(self) -> Path:
        return self.pdf.with_suffix(".aux")

    @property
    def nav(self) -> Path:
        return self.pdf.with_suffix(".nav")


def compile_latex(
    tex: str | Path, *, engine: str = "pdflatex", output_dir: str | Path | None = None,
    jobname: str | None = None, preamble: str = "", passes: int = 1, extra_passes: int = 0,
    rerun_pattern: str | None = None, halt_on_error: bool = True, file_line_error: bool = False,
    texinputs: tuple[str | Path, ...] = (), env: Mapping[str, str] | None = None,
    log_encoding: str = "utf-8", output_encoding: str | None = None,
    on_pass: Callable[[int, int], None] | None = None,
) -> LatexResult:
    """Compile beside the source, leaving relative includes and local styles intact.

    Explicit relative output_dir/texinputs paths resolve from the caller's CWD.
    Without output_dir all artifacts stay beside the source. No course discovery,
    source rewriting, cleanup, style injection or PDF interpretation takes place.
    pdflatex runs passes times, then up to extra_passes while the log matches
    rerun_pattern. latexmk manages its own passes and rejects preamble/pass overrides.
    Preamble code is passed directly to pdflatex without an intervening shell.

    Engine failures are returned for the caller's diagnostics. Invalid options
    raise ValueError; missing sources/tools and filesystem failures raise OSError.
    """
    if engine not in ("pdflatex", "latexmk"):
        raise ValueError("engine must be 'pdflatex' or 'latexmk'")
    if not isinstance(passes, int) or passes < 1 or not isinstance(extra_passes, int) or extra_passes < 0:
        raise ValueError("passes must be positive and extra_passes nonnegative integers")
    if engine == "latexmk" and (preamble or passes != 1 or extra_passes):
        raise ValueError("latexmk manages its own passes; use pdflatex for preamble/pass overrides")
    if jobname is not None and (not jobname or jobname in (".", "..") or
                               any(char in jobname for char in '/\\<>:"|?*\r\n')):
        raise ValueError("jobname must be a filename without a directory or reserved characters")
    rerun = re.compile(RERUN_PATTERN if rerun_pattern is None else rerun_pattern, re.MULTILINE)
    source = Path(tex).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"LaTeX source not found: {source}")
    if shutil.which(engine) is None:
        raise FileNotFoundError(f"{engine} is not on PATH")
    output = Path(output_dir).resolve() if output_dir is not None else source.parent
    name = jobname if jobname is not None else source.stem
    command = [engine]
    if engine == "latexmk":
        command.append("-pdf")
    command.append("-interaction=nonstopmode")
    if halt_on_error:
        command.append("-halt-on-error")
    if file_line_error:
        command.append("-file-line-error")
    if output_dir is not None:
        flag = "-outdir" if engine == "latexmk" else "-output-directory"
        command.append(f"{flag}={output}")
    if jobname is not None:
        command.append(f"-jobname={jobname}")
    command.append(preamble + rf"\input{{{source.name}}}" if preamble else source.name)
    environment = dict(os.environ)
    if env is not None:
        # os.environ normalizes keys on Windows; a plain dict otherwise permits
        # duplicate PATH/Path keys instead of overriding the inherited setting.
        environment.update({key.upper() if os.name == "nt" else key: value for key, value in env.items()})
    if texinputs:
        environment["TEXINPUTS"] = os.pathsep.join(str(Path(path).resolve()) for path in texinputs) \
            + os.pathsep + environment.get("TEXINPUTS", "")
    output.mkdir(parents=True, exist_ok=True)
    log = output / f"{name}.log"
    log_text = ""
    for index in range(passes + extra_passes):
        if index >= passes and not rerun.search(log_text):
            break
        if on_pass is not None:
            on_pass(index + 1, passes + extra_passes)
        process = subprocess.run(command, cwd=source.parent, env=environment,
                                 capture_output=True, text=True, encoding=output_encoding, errors="replace")
        log_text = log.read_text(encoding=log_encoding, errors="replace") if log.exists() else ""
        result = LatexResult(output / f"{name}.pdf", log, process.returncode, process.stdout,
                             process.stderr, log_text, index + 1)
        if process.returncode:
            break
    return result
