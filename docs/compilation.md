# Shared LaTeX compilation

`compile_latex` was added in 0.2.1.dev2 and remains part of API version 1 in
the current 0.2.1.dev3 candidate. It is a Python API, not a separate CLI command.
It runs a LaTeX engine
and returns output locations and diagnostics. Texstage's live-deck and plain
PowerPoint builders use it, and lecture-tools uses it for chapter compilation.

Install Texstage using [installation.md](installation.md). The chosen engine
must be on PATH: `pdflatex`, or `latexmk` with pdflatex and its platform runtime
(including Perl where required by the TeX distribution). Python packages do not
install TeX. Plain TeX sources can continue to use the TeX distribution directly.

```python
from texstage.api import compile_latex

result = compile_latex("talk.tex", engine="latexmk", output_dir="build")
if result.returncode:
    raise RuntimeError(result.log_text or result.stdout or result.stderr)
print(result.pdf)
```

## Ownership and paths

The compiler runs with the source directory as its working directory, so relative
includes and local styles keep working. Without `output_dir`, artifacts are
written beside the source. Explicit relative `output_dir` and `texinputs` paths
resolve from the caller's working directory. A job name changes output basenames;
it must be a filename, not a directory. Returned paths are absolute.

The runner does not assemble frames, rewrite the source, select DBIS or other
themes, define quiz modes, clean artifacts, inspect a PDF or start a server.
It inherits the process environment and default TeX search paths. Extra styles
and environment overrides are supplied explicitly by callers without changing
the parent process. Texstage's live builder supplies its generic style directory
and mode flags. Lecture-tools supplies course notes flags and retains all course
assembly, frame numbering, checks and recovery policy.

## Options

| Parameter | Default and behavior |
|---|---|
| `engine` | `"pdflatex"`; also accepts `"latexmk"` in PDF mode |
| `output_dir` | `None`: source directory; otherwise create/use this directory |
| `jobname` | `None`: source stem; otherwise output basename |
| `preamble` | Empty; TeX code before the input, passed directly to pdflatex without a shell |
| `passes` | 1 mandatory pdflatex pass; stops immediately on failure |
| `extra_passes` | 0; maximum additional pdflatex passes while the log requests a rerun |
| `rerun_pattern` | `None`: standard reference/label and missing aux/nav messages; a custom regular expression can narrow the policy |
| `halt_on_error` | `True`; course auxiliary recovery can disable it |
| `file_line_error` | `False`; the live builder enables file/line diagnostics |
| `texinputs` | Empty tuple; directories prepended to inherited TEXINPUTS and TeX's default search |
| `env` | `None`; explicit overrides of inherited environment variables |
| `log_encoding` | `"utf-8"`, replacing undecodable characters; legacy course diagnostics use Latin-1 |
| `output_encoding` | `None`: platform default, with replacement for undecodable engine output |
| `on_pass` | `None`; optional callback receiving the 1-based invocation and maximum allowed count |

latexmk controls its own engine passes; use its default `passes=1`,
`extra_passes=0`, and empty `preamble`. For notes flags or a specific rerun policy,
choose pdflatex. Neither engine runs a shell command constructed from filenames.

## Result and errors

`LatexResult` contains `pdf`, `log`, `returncode`, `stdout`, `stderr`, `log_text`
and `passes_run`; `aux` and `nav` expose the corresponding output paths.
`passes_run` counts invocations by this runner, not passes inside latexmk.
The last engine result is returned even when compilation fails. Always inspect
`returncode`: a failed build can leave missing, partial or older output files.

Invalid options raise `ValueError`; malformed rerun expressions raise Python's
regular-expression error. Missing sources/tools and filesystem failures raise
`OSError` subclasses. Callers decide how these become CLI messages and exit codes.
Existing `texstage pdf`/`build` commands keep their `LatexError` handling, and
lecture-tools keeps its chapter-specific diagnostics.
