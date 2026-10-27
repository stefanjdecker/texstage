# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""This machine's live decks (docs/design.md, section 4): every deck reaches its quiz server
through its build. texstage build records the folder of every deck it builds in builds.json in
the data folder, and a quiz server with that data folder serves those decks too - for
PowerPoint and texstage, without an upload; a server elsewhere gets the deck uploaded by the
build (cli.deliver). The PowerPoint file carries none: PowerPoint keeps at most 2 MB for an
add-in, too little for a lecture's chapter. Folders that are gone drop out."""
from __future__ import annotations

import json
from pathlib import Path

BUILDS = "builds.json"
KEEP = 500                   # the folders of the newest builds
CARRY_MAX = 1_900_000        # base64 characters a PPTX built before 2026-10-09 can bring on its join
                             # slide: PowerPoint keeps at most 2 MB for an add-in (a lecture chapter's
                             # 5.3 MB did not arrive) - texstage check flags larger ones


def _read(data_dir: Path) -> list[str]:
    try:
        folders = json.loads((data_dir / BUILDS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [f for f in folders if isinstance(f, str)] if isinstance(folders, list) else []


def build_folders(data_dir: Path) -> list[Path]:
    """The build folders recorded in this data folder that still exist."""
    return [Path(f) for f in _read(data_dir) if Path(f).is_dir()]


def remember_build(folder: Path, data_dir: Path):
    """Records a build folder (the newest last)."""
    folder = str(Path(folder).resolve())
    folders = [f for f in _read(data_dir) if f != folder and Path(f).is_dir()] + [folder]
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / BUILDS).write_text(json.dumps(folders[-KEEP:], indent=1) + "\n", encoding="utf-8")
