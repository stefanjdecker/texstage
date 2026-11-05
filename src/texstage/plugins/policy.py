# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Explicit operator enablement. Profiles contain pins, never executable paths."""
from pathlib import Path

from . import PluginError
from .catalog import Catalog, discover
from .manifest import canonical, read_json


def read_profile(data: Path):
    path = Path(data) / "plugins.json"
    if not path.exists():
        return {"format": 1, "enabled": []}
    profile = read_json(path.read_bytes())
    if not isinstance(profile, dict) or set(profile) != {"format", "enabled"} or type(profile["format"]) is not int or profile["format"] != 1 \
            or not isinstance(profile["enabled"], list):
        raise PluginError("invalid plugin profile")
    return profile


def catalog_for(data: Path | None) -> Catalog:
    profile = read_profile(data) if data is not None else {"enabled": []}
    if not profile["enabled"]:
        return Catalog()
    installed = {p.id: p for p in discover()}
    selected = []
    for pin in profile["enabled"]:
        if not isinstance(pin, dict) or set(pin) != {"id", "version", "payload"}:
            raise PluginError("invalid enablement pin")
        p = installed.get(pin["id"])
        if p is None or pin != p.requirement():
            raise PluginError(f"enabled plugin changed or missing: {pin['id']}; explicitly review and enable its new pin")
        selected.append(p)
    return Catalog(selected)


def enable(data: Path, pid: str, version: str, payload: str):
    installed = {p.id: p for p in discover()}
    p = installed.get(pid)
    if p is None or p.requirement() != {"id": pid, "version": version, "payload": payload}:
        raise PluginError("enable requires the exact installed ID, version and payload digest from inspect")
    profile = read_profile(data)
    profile["enabled"] = sorted([pin for pin in profile["enabled"] if pin["id"] != pid] + [p.requirement()],
                                key=lambda pin: pin["id"])
    for pin in profile["enabled"]:
        if installed.get(pin["id"]) is None or installed[pin["id"]].requirement() != pin:
            raise PluginError(f"another enabled provider changed: {pin['id']}; review its pin first")
    Catalog([installed[pin["id"]] for pin in profile["enabled"]])
    write_json(Path(data) / "plugins.json", profile)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(canonical(value) + b"\n")
    temp.replace(path)
