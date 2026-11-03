r"""Plain Beamer to image-based PowerPoint, including speaker notes.

Moved from lecture_tools.media.beamer_to_pptx; see NOTICE for its retained
licensing status. The public entry point is texstage.api.convert_beamer_to_pptx.
Course assembly belongs to lecture-tools; this converter accepts one .tex file.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .notes import NOTE_TEMPLATE, note_paragraphs
from .pdf import Pdf
from .powerpoint import PptxDeck


LATEX_AUX_EXTS = [
    ".aux", ".log", ".nav", ".out", ".snm", ".toc", ".vrb",
    ".bbl", ".blg", ".fls", ".fdb_latexmk", ".synctex.gz", ".dvi",
]


# ---------- LaTeX helpers ----------

def run_pdflatex(tex_file: Path, workdir: Path, jobname: str, passes: int = 2) -> Path:
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={jobname}",
        tex_file.name,
    ]
    for i in range(passes):
        print(f"  pdflatex {jobname} (pass {i + 1}/{passes})")
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
        if r.returncode != 0:
            tail = "\n".join(r.stdout.splitlines()[-60:])
            raise RuntimeError(f"pdflatex failed for {jobname}:\n{tail}")
    return workdir / f"{jobname}.pdf"


def inject_preamble(tex_source: str, injection: str) -> str:
    r"""Insert LaTeX code immediately before \begin{document}."""
    pat = re.compile(r"\\begin\s*\{document\}")
    m = pat.search(tex_source)
    if not m:
        raise ValueError("Could not find \\begin{document} in source .tex")
    # Lambda avoids re.sub's replacement-string escape processing,
    # which would otherwise choke on \s, \i, etc. in our LaTeX injection.
    return pat.sub(lambda _m: injection + "\n" + _m.group(0), tex_source, count=1)


def cleanup_artifacts(src_dir: Path, jobnames):
    """Remove generated .tex, .pdf, and aux files for our jobnames."""
    for job in jobnames:
        for ext in [".tex", ".pdf"] + LATEX_AUX_EXTS:
            f = src_dir / f"{job}{ext}"
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass


# ---------- PDF helpers (PDFium: texstage/build/pdf.py) ----------

def pdf_to_images(pdf_path: Path, out_dir: Path, target_height: int = 1080,
                  dpi_override=None):
    """Rasterise each page so its pixel height ≈ target_height,
    unless dpi_override is set (then use that fixed DPI).

    This is only used by the legacy two-PDF mode.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with Pdf(pdf_path) as doc:
        for i, page in enumerate(doc):
            if dpi_override is not None:
                dpi = int(dpi_override)
            else:
                page_height_inch = page.height / 72.0
                dpi = int(round(target_height / page_height_inch))
            im = page.render(dpi / 72)
            if i == 0:
                print(f"  DPI = {dpi} → {im.width}×{im.height} px per slide")
            p = out_dir / f"slide_{i:03d}.png"
            im.save(p)
            paths.append(p)
    return paths


def extract_notes(pdf_path: Path):
    """Extract text from every page of a notes-only PDF.

    This is only used by the legacy two-PDF mode.
    """
    with Pdf(pdf_path) as doc:
        return [note_paragraphs(page) for page in doc]


def split_second_screen_pdf(pdf_path: Path, out_dir: Path, target_height: int = 1080,
                            dpi_override=None, note_side: str = "right"):
    """Split a Beamer notes-on-second-screen PDF into slide images and notes.

    Beamer's ``show notes on second screen=right`` creates each PDF page with
    the rendered slide and its note page side-by-side. Because both live on the
    same physical PDF page, the alignment is much more robust than compiling a
    separate slides PDF and notes PDF and then matching them by index.
    """
    if note_side not in {"left", "right"}:
        raise ValueError("note_side must be 'left' or 'right'")

    out_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    notes = []

    with Pdf(pdf_path) as doc:
        for i, page in enumerate(doc):
            mid_x = page.width / 2.0
            left_rect = (0, 0, mid_x, page.height)
            right_rect = (mid_x, 0, page.width, page.height)

            if note_side == "right":
                slide_rect, note_rect = left_rect, right_rect
            else:
                note_rect, slide_rect = left_rect, right_rect

            if dpi_override is not None:
                dpi = int(dpi_override)
            else:
                page_height_inch = page.height / 72.0
                dpi = int(round(target_height / page_height_inch))

            im = page.render(dpi / 72, clip=slide_rect)
            if i == 0:
                print(f"  DPI = {dpi} → {im.width}×{im.height} px per slide")

            img_path = out_dir / f"slide_{i:03d}.png"
            im.save(img_path)
            image_paths.append(img_path)

            notes.append(note_paragraphs(page, note_rect))

    return image_paths, notes


def align_notes_by_index(image_paths, notes):
    """Legacy fallback: pad or truncate notes so they can be zipped by index."""
    notes = list(notes)
    if len(notes) < len(image_paths):
        notes.extend([""] * (len(image_paths) - len(notes)))
    elif len(notes) > len(image_paths):
        notes = notes[:len(image_paths)]
    return notes


def build_pptx(image_paths, notes, output_path: Path, widescreen=True):
    """Use the same slide writer as live decks, fitting rather than stretching images."""
    if len(image_paths) != len(notes):
        raise ValueError(
            f"Cannot build PPTX: {len(image_paths)} slide images but {len(notes)} notes."
        )
    # Preserve the legacy canvas dimensions, including 13.333 inches for 16:9.
    deck = PptxDeck((13.333 if widescreen else 10, 7.5))
    for image_path, note in zip(image_paths, notes):
        deck.add_slide(Path(image_path).read_bytes(), note, fit="contain")
    deck.save(output_path)


def convert_beamer_to_pptx(
    tex: str | Path, output: str | Path | None = None, *,
    target_height: int = 1080, dpi: int | None = None, standard: bool = False,
    note_side: str = "right", legacy_two_pass_notes: bool = False,
    allow_note_mismatch: bool = False, keep_artifacts: bool = False,
) -> Path:
    """Convert one Beamer document and return the absolute PPTX path.

    Relative includes resolve beside the source. Output defaults to <source>.pptx;
    an explicit relative output is relative to the caller's working directory.
    One PDF page produces one image slide, so overlays remain separate slides.
    The default second-screen mode keeps each slide beside its own speaker notes.
    Legacy mode instead compiles separate slide/notes PDFs and matches by index.

    Compilation uses pdflatex on PATH, twice per variant. Generated source/PDF/aux
    files live beside the source and are removed even on failure unless
    keep_artifacts is true. Existing artifacts are never overwritten or deleted.
    The requested PPTX is replaced on success, as in the legacy command.
    Raises OSError for file/tool errors, ValueError for invalid input, and
    RuntimeError for compilation or legacy note-count mismatches.
    """
    tex_path = Path(tex).resolve()
    if not tex_path.is_file():
        raise FileNotFoundError(f"File not found: {tex_path}")
    if target_height <= 0 or (dpi is not None and dpi <= 0):
        raise ValueError("target_height and dpi must be positive")
    if note_side not in {"left", "right"}:
        raise ValueError("note_side must be 'left' or 'right'")
    if shutil.which("pdflatex") is None:
        raise FileNotFoundError("pdflatex not on PATH — install MiKTeX or TeX Live.")
    out_path = Path(output).resolve() if output else tex_path.with_suffix(".pptx")

    src_dir = tex_path.parent
    src = tex_path.read_text(encoding="utf-8")

    # Keep the established debug-artifact names, but never overwrite existing files.
    stem = tex_path.stem

    if legacy_two_pass_notes:
        jobnames = [f"_b2p_{stem}_slides", f"_b2p_{stem}_notes"]
    else:
        jobnames = [f"_b2p_{stem}_combined"]

    for job in jobnames:
        for extension in [".tex", ".pdf", *LATEX_AUX_EXTS]:
            artifact = src_dir / (job + extension)
            if artifact.exists():
                raise FileExistsError(f"Conversion artifact already exists: {artifact}. "
                                      "Move or remove it before converting again.")

    try:
        if legacy_two_pass_notes:
            slides_job, notes_job = jobnames
            slides_tex_file = src_dir / f"{slides_job}.tex"
            notes_tex_file = src_dir / f"{notes_job}.tex"

            # Legacy method: write two variant .tex files right next to the original,
            # so all relative paths (../foo.sty, figs/x.pdf, \input{...}) keep working.
            slides_injection = r"\setbeameroption{hide notes}"
            notes_injection = (
                r"\setbeameroption{show only notes}" "\n"
                + NOTE_TEMPLATE
            )
            slides_tex_file.write_text(inject_preamble(src, slides_injection), encoding="utf-8")
            notes_tex_file.write_text(inject_preamble(src, notes_injection), encoding="utf-8")

            print("[1/4] Compile slides PDF")
            slides_pdf = run_pdflatex(slides_tex_file, src_dir, jobname=slides_job)

            print("[2/4] Compile notes PDF")
            notes_pdf = run_pdflatex(notes_tex_file, src_dir, jobname=notes_job)

            with tempfile.TemporaryDirectory(prefix="b2p_") as tmp:
                tmp = Path(tmp)
                # Copy the PDFs out so we can still read them after cleanup.
                slides_copy = tmp / "slides.pdf"
                notes_copy = tmp / "notes.pdf"
                shutil.copy2(slides_pdf, slides_copy)
                shutil.copy2(notes_pdf, notes_copy)

                print("[3/4] Rasterise + extract notes")
                images = pdf_to_images(
                    slides_copy,
                    tmp / "img",
                    target_height=target_height,
                    dpi_override=dpi,
                )
                notes = extract_notes(notes_copy)

                if len(notes) != len(images):
                    msg = (
                        f"slide/note page mismatch: {len(images)} slides vs "
                        f"{len(notes)} note pages"
                    )
                    if not allow_note_mismatch:
                        raise RuntimeError(
                            msg + "; use --allow-note-mismatch to pad/truncate by index"
                        )
                    print(f"  ⚠ {msg} — padding/truncating notes by index.")
                    notes = align_notes_by_index(images, notes)

                print("[4/4] Assemble PPTX")
                build_pptx(images, notes, out_path, widescreen=not standard)

        else:
            combined_job = jobnames[0]
            combined_tex_file = src_dir / f"{combined_job}.tex"

            # Default method: one combined Beamer PDF with slide and note on the
            # same physical page. This keeps notes aligned with overlays.
            combined_injection = (
                rf"\setbeameroption{{show notes on second screen={note_side}}}" "\n"
                + NOTE_TEMPLATE
            )
            combined_tex_file.write_text(inject_preamble(src, combined_injection), encoding="utf-8")

            print("[1/3] Compile combined slide+notes PDF")
            combined_pdf = run_pdflatex(combined_tex_file, src_dir, jobname=combined_job)

            with tempfile.TemporaryDirectory(prefix="b2p_") as tmp:
                tmp = Path(tmp)
                combined_copy = tmp / "combined.pdf"
                shutil.copy2(combined_pdf, combined_copy)

                print("[2/3] Split slides + extract notes")
                images, notes = split_second_screen_pdf(
                    combined_copy,
                    tmp / "img",
                    target_height=target_height,
                    dpi_override=dpi,
                    note_side=note_side,
                )

                print("[3/3] Assemble PPTX")
                build_pptx(images, notes, out_path, widescreen=not standard)

    finally:
        if not keep_artifacts:
            cleanup_artifacts(src_dir, jobnames)
        else:
            print(f"  artifacts kept with prefix _b2p_ in {src_dir}")

    print(f"\n✓ Done: {out_path}")

    return out_path
