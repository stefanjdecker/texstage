# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Generic LaTeX records to code-free bundle items, through enabled build hooks."""
import hashlib
import re
from pathlib import Path

from texstage.plugins import PluginError
from texstage.plugins.manifest import canonical, read_json, resource_path, validate_bindings
from texstage.plugins.worker import Workers
from .bundle import public_rects

ITEM = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,79}\Z")
DATA_MIME = {".json", ".txt", ".csv", ".sql", ".ttl", ".png", ".jpg"}


def records(tqz):
    result = {}
    for fields in tqz.records.get("plugin", []):
        if len(fields) != 6: raise PluginError("invalid plugin LaTeX record")
        item, cid, public, private, public_json, private_json = fields
        if not ITEM.fullmatch(item): raise PluginError("plugin item IDs must be simple unique identifiers")
        row = dict(zip(("type", "public", "private", "public_json", "private_json"),
                       [bytes.fromhex(v).decode("utf-8") for v in (cid, public, private, public_json, private_json)]))
        if item in result and result[item] != row: raise PluginError(f"conflicting definitions of plugin item {item}")
        result[item] = row
    return result


def box(tqz, item, definitions):
    record = definitions.get(item.id)
    if record is None: raise PluginError(f"missing plugin definition: {item.id}")
    return {"type": record["type"], "item": item.id,
            "rects": public_rects(item.rects, {}, tqz.paper)}


def source_file(root, name):
    resource_path(name)
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise PluginError("plugin data file escapes the deck directory")
    if path.stat().st_size > 2 * 1024 * 1024: raise PluginError("plugin data exceeds 2 MiB")
    return path.read_bytes()


def prepare(tqz, root, catalog):
    definitions = records(tqz)
    built_in_ids = {i.id for page in tqz.pages.values() for i in page.items if i.kind != "plugin"}
    if set(definitions) & built_in_ids:
        raise PluginError("plugin item IDs must not collide with built-in items")
    public, private, files, used_engines = {}, {}, {}, set()
    workers = Workers(catalog)
    try:
        for item, record in definitions.items():
            cid = record["type"]
            _, spec = catalog.capability(cid)
            value = {}
            for key in ("public", "private"):
                path, inline = record[key], record[key + "_json"]
                if path and inline: raise PluginError(f"{item}: use a file or inline JSON for {key}")
                value[key] = read_json(source_file(root, path) if path else inline or "{}", limit=2 * 1024 * 1024)
            prepared = workers.call(cid, "prepare", value, {"item_id": item, "type": cid})
            expected = {"public", "private", "assets", "evaluations", "diagnostics"}
            if not isinstance(prepared, dict) or set(prepared) != expected:
                raise PluginError("build hook must return PreparedItem")
            if not isinstance(prepared["public"], dict) or not isinstance(prepared["private"], dict):
                raise PluginError("prepared public/private item data must be objects")
            assets_public, assets_private = {}, {}
            for logical, asset in prepared["assets"].items():
                if not isinstance(asset, dict) or set(asset) != {"source", "visibility"} \
                        or asset["visibility"] not in ("public", "private"):
                    raise PluginError("asset requires source and public/private visibility")
                suffix = Path(asset["source"]).suffix.lower()
                if suffix not in DATA_MIME: raise PluginError("only core-approved data/image assets can enter a bundle")
                data = source_file(root, asset["source"])
                name = f"plugin-data/{hashlib.sha256(data).hexdigest()}{suffix}"
                files[name] = data
                (assets_public if asset["visibility"] == "public" else assets_private)[logical] = name
            evaluations = prepared["evaluations"]
            validate_bindings(evaluations, spec.get("evaluations", {}))
            for binding, options in evaluations.items():
                engine = spec["evaluations"][binding]["engine"]
                catalog.capability(engine, engine=True)
                used_engines.add(engine)
                options["engine"] = engine
            public.setdefault(cid, {})[item] = prepared["public"] | {"plugin_assets": assets_public}
            private.setdefault(cid, {})[item] = {"private": prepared["private"], "assets": assets_private,
                                                 "evaluations": evaluations}
        requirements = catalog.requirements(public, used_engines) if public else []
        return public, private, files, requirements
    finally:
        workers.close()


def verify_styles(catalog, recorder: Path, source_dir: Path):
    for line in recorder.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("INPUT "): continue
        path = Path(line[6:])
        path = path if path.is_absolute() else source_dir / path
        declared = catalog.styles.get(path.name.casefold())
        if declared:
            pid, name = declared
            provider = catalog.providers[pid]
            expected = provider.root / name
            if path.resolve() != expected.resolve() or path.read_bytes() != provider.resources[name]:
                raise PluginError(f"TeX loaded an unapproved plugin style: {path}; expected {expected}")
