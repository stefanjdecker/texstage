# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Portable provider pins, deliberately separate from Python dependency locks."""
from pathlib import Path

from . import PluginError
from .manifest import read_json
from .policy import write_json


def write_lock(path: Path, catalog):
    write_json(path, {"format": 1, "plugin_api": 1,
                      "providers": [p.requirement() for p in catalog.providers.values()]})


def check_lock(path: Path, catalog):
    lock = read_json(path.read_bytes())
    expected = {"format": 1, "plugin_api": 1,
                "providers": [p.requirement() for p in catalog.providers.values()]}
    if lock != expected:
        raise PluginError("plugin lock does not match the explicitly enabled profile")
    return lock
