# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Supported, lazy integration surface for course tools.

Keep paths returned by latex_resources() inside its context: resources in a zipped
installation can be temporary. PDF pages remain valid only while their Pdf is open.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator

API_VERSION = 1
LATEX_FILES = ("texstage.sty", "texquiz.sty", "texvideo.sty", "texactivity.sty")
__all__ = [
    "API_VERSION", "LATEX_FILES", "run_cli", "needs_build", "slug",
    "Pdf", "NOTE_TEMPLATE", "note_paragraphs", "latex_resources", "convert_beamer_to_pptx",
]


def run_cli(argv: list[str] | None = None) -> int:
    """Run a standalone texstage command, preserving its return code."""
    from .cli import main
    return main(argv)


def convert_beamer_to_pptx(
    tex: str | Path, output: str | Path | None = None, *,
    target_height: int = 1080, dpi: int | None = None, standard: bool = False,
    note_side: str = "right", legacy_two_pass_notes: bool = False,
    allow_note_mismatch: bool = False, keep_artifacts: bool = False,
) -> Path:
    """Convert a Beamer source to an image PPTX with notes; return its absolute path.

    Added in 0.2.1.dev1, within API version 1. Defaults and options match the
    legacy beamer2pptx command; see docs/powerpoint.md for the full contract.
    """
    from .build.beamer import convert_beamer_to_pptx as implementation
    return implementation(
        tex, output, target_height=target_height, dpi=dpi, standard=standard,
        note_side=note_side, legacy_two_pass_notes=legacy_two_pass_notes,
        allow_note_mismatch=allow_note_mismatch, keep_artifacts=keep_artifacts,
    )


def needs_build(folder: Path, out: Path, ignore: tuple[str, ...] = ()) -> str | None:
    """Return the existing builder's rebuild reason, or None."""
    from .cli import needs_build as implementation
    return implementation(folder, out, ignore)


def slug(text: str) -> str:
    """Use the same identifiers as the standalone builder."""
    from .build.builder import slug as implementation
    return implementation(text)


def note_paragraphs(page, clip=None) -> str:
    """Extract notes without changing the established page/clip convention."""
    from .build.notes import note_paragraphs as implementation
    return implementation(page, clip)


def __getattr__(name: str):
    if name == "Pdf":
        from .build.pdf import Pdf
        return Pdf
    if name == "NOTE_TEMPLATE":
        from .build.notes import NOTE_TEMPLATE
        return NOTE_TEMPLATE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@contextmanager
def latex_resources() -> Iterator[Path]:
    """Yield the generic style directory in a checkout or installed distribution."""
    packaged = resources.files("texstage").joinpath("latex")
    if packaged.is_dir():
        with resources.as_file(packaged) as directory:
            _check_latex(directory)
            yield directory
    else:
        directory = Path(__file__).resolve().parents[2] / "latex"
        _check_latex(directory)
        yield directory


def _check_latex(directory: Path) -> None:
    missing = [name for name in LATEX_FILES if not (directory / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Incomplete texstage LaTeX installation: {', '.join(missing)}")
