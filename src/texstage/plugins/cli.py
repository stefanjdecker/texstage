# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Operator commands. Merely inspecting an installation never runs its factory."""
import json
from pathlib import Path
import sys

from texstage import DEFAULT_DATA
from . import PluginError
from .catalog import discover
from .lock import write_lock
from .policy import catalog_for, enable, read_profile, write_json


def add_parser(sub):
    p = sub.add_parser("plugins", help="experimental plugins: inspect, enable and pin trusted installed packages")
    p.add_argument("--data", default=str(DEFAULT_DATA), help="operator profile (use a disposable directory for experiments)")
    commands = p.add_subparsers(dest="plugin_action", required=True)
    commands.add_parser("list")
    inspect = commands.add_parser("inspect"); inspect.add_argument("id")
    e = commands.add_parser("enable"); e.add_argument("id"); e.add_argument("--version", required=True); e.add_argument("--payload", required=True)
    d = commands.add_parser("disable"); d.add_argument("id")
    lock = commands.add_parser("lock"); lock.add_argument("--output", required=True)
    check = commands.add_parser("check"); check.add_argument("bundle")
    c = commands.add_parser("catalog"); c.add_argument("action", choices=["update"])
    src = c.add_mutually_exclusive_group(required=True); src.add_argument("--url"); src.add_argument("--file")
    search = commands.add_parser("search"); search.add_argument("query", nargs="?", default="")
    info = commands.add_parser("info"); info.add_argument("id")
    install = commands.add_parser("install"); install.add_argument("pin")
    install.add_argument("--write-requirements", required=True); install.add_argument("--offline", action="store_true")
    p.set_defaults(func=run)


def run(args):
    data, action = Path(args.data), args.plugin_action
    try:
        if action in ("list", "inspect"):
            enabled = {pin["id"] for pin in read_profile(data)["enabled"]}
            found = [p for p in discover() if action == "list" or p.id == args.id]
            if action == "inspect" and not found: raise PluginError("plugin is not installed")
            result = [p.requirement() | {"enabled": p.id in enabled, "distribution": p.distribution,
                       **({"manifest": p.manifest} if action == "inspect" else {})} for p in found]
        elif action == "enable":
            enable(data, args.id, args.version, args.payload)
            result = {"enabled": args.id, "note": "restart the server to use the changed profile"}
        elif action == "disable":
            profile = read_profile(data)
            profile["enabled"] = [p for p in profile["enabled"] if p["id"] != args.id]
            write_json(data / "plugins.json", profile); result = {"disabled": args.id}
        elif action == "lock":
            write_lock(Path(args.output), catalog_for(data)); result = {"lock": args.output}
        elif action == "check":
            from texstage.server.bundles import load_bundle
            b = load_bundle(Path(args.bundle), catalog=catalog_for(data)); result = {"bundle": b.id, "valid": True}
        else:
            from . import collection
            if action == "catalog": result = collection.update(data, url=args.url, file=args.file)
            elif action == "install": result = collection.install(data, args.pin, requirements=Path(args.write_requirements), offline=args.offline)
            else:
                result = [r for r in collection.cached(data)["releases"] if
                          (r["id"] == args.id if action == "info" else args.query.lower() in r["id"].lower())]
        print(json.dumps(result, indent=2))
        return 0
    except (PluginError, OSError, ValueError) as exc:
        print(f"texstage plugins: {exc}", file=sys.stderr)
        return 2
