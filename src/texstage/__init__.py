# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage: Beamer decks presented live - with quizzes (texquiz), in the browser or in
PowerPoint (docs/content-types-design.md)."""
from pathlib import Path

__version__ = "0.2.1.dev2"
# The quiz server on the presenting laptop: its port and data folder (database, presenter key,
# remembered keys, tunnel). The commands, the presenter keys and the build take them from here.
DEFAULT_PORT = 8470
DATA_NAME = ".texstage"                          # the data folder, in the home folder
OLD_DATA_NAME = ".texquiz"                       # its name until 2026-10-10


def data_folder(home: Path) -> Path:
    """The laptop server's data folder: ~/.texstage - or ~/.texquiz where only that one exists
    (the name until 2026-10-10: nothing is moved, the server goes on with its data)."""
    new, old = home / DATA_NAME, home / OLD_DATA_NAME
    return old if old.is_dir() and not new.exists() else new


DEFAULT_DATA = data_folder(Path.home())
DEFAULT_SERVER = f"http://localhost:{DEFAULT_PORT}"
SERVER_NAMES = ("texstage", "texquiz")         # what /api/status says (texquiz until 2026-10-10)
