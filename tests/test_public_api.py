# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Contracts consumed by independently installed course tools."""
import subprocess
import sys

import pytest

from texstage import api


def test_import_does_not_load_renderer_or_server():
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys, texstage.api; "
         "assert not any(m.startswith(('pypdfium2', 'texstage.server', 'pptx', 'PIL')) for m in sys.modules)"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_cli_preserves_arguments_and_return_code(monkeypatch):
    from texstage import cli
    seen = []
    monkeypatch.setattr(cli, "main", lambda args: seen.append(args) or 17)
    args = ["build", "a deck.tex", "--no-stage"]
    assert api.run_cli(args) == 17
    assert seen == [args]


def test_rebuild_reason_and_ignore_are_preserved(tmp_path, monkeypatch):
    from texstage import cli
    seen = []
    monkeypatch.setattr(cli, "needs_build", lambda *args: seen.append(args) or "source changed")
    assert api.needs_build(tmp_path, tmp_path / "out", ("slides.tex",)) == "source changed"
    assert seen == [(tmp_path, tmp_path / "out", ("slides.tex",))]


def test_identifiers_use_existing_builder():
    from texstage.build.builder import slug
    assert api.slug("DBIS 01-Test") == slug("DBIS 01-Test")


def test_pdf_and_note_contracts_are_original_objects():
    from texstage.build.pdf import Pdf
    from texstage.build.notes import NOTE_TEMPLATE
    assert api.Pdf is Pdf
    assert api.NOTE_TEMPLATE == NOTE_TEMPLATE
    class Page:
        def words(self, clip):
            assert clip == (1, 2, 3, 4)
            return [(0, 0, 10, 10, "First"), (12, 0, 20, 10, "line")]
    assert api.note_paragraphs(Page(), (1, 2, 3, 4)) == "First line"
    with pytest.raises(AttributeError):
        api.not_an_api


def test_generic_latex_resources_are_complete():
    with api.latex_resources() as directory:
        assert all((directory / name).is_file() for name in api.LATEX_FILES)
        assert not (directory / "dbis-slides.sty").exists()
        assert not (directory / "texquiz-theme-dbis.sty").exists()
