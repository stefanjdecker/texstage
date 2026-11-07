# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Metadata-only installed-package discovery and immutable enabled catalogs."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from . import PluginError
from .assets import MAX_PACKAGE, verified_file
from .contracts import CONTRACT_VERSION, validate_portable_schema
from .manifest import canonical, digest, load_manifest, read_json, validate_json, validate_schema

GROUP = "texstage.plugins.v1"


@dataclass(frozen=True)
class Provider:
    id: str
    version: str
    distribution: str
    root: Path
    entry_point: str
    payload: str
    metadata_bytes: bytes
    resources: object

    @property
    def manifest(self) -> dict:
        return read_json(self.metadata_bytes)

    def requirement(self) -> dict:
        return {"id": self.id, "version": self.version, "payload": self.payload}

    def verify(self):
        for name, spec in self.manifest["resources"].items():
            verified_file(self.root, name, spec["sha256"], spec["size"])


def discover(*, distributions=None) -> tuple[Provider, ...]:
    result, ids = [], set()
    for dist in metadata.distributions() if distributions is None else distributions:
        entries = [e for e in dist.entry_points if e.group == GROUP]
        raw = dist.read_text("texstage-plugin.json")
        if raw is None and not entries:
            continue
        if raw is None or len(entries) != 1:
            raise PluginError(f"{dist.metadata['Name']}: expected one {GROUP} entry and manifest")
        manifest = load_manifest(raw)
        pid = manifest["id"]
        if pid in ids:
            raise PluginError(f"duplicate installed plugin ID: {pid}")
        ids.add(pid)
        entry = entries[0]
        if entry.name != pid or dist.version != manifest["version"]:
            raise PluginError(f"{pid}: entry point or distribution version disagrees with manifest")
        wheel = dist.read_text("WHEEL") or ""
        tags = [line[5:] for line in wheel.splitlines() if line.startswith("Tag: ")]
        if tags != ["py3-none-any"] or "Root-Is-Purelib: true" not in wheel:
            raise PluginError(f"{pid}: API 1 requires an installed portable py3-none-any wheel")
        inventory = manifest["resources"]
        owned = {str(p).replace("\\", "/") for p in dist.files or []}
        unlisted = {p for p in owned if ".dist-info/" not in p and not p.endswith(".pyc")}
        if unlisted != set(inventory):
            raise PluginError(f"{pid}: resource inventory and installed RECORD disagree")
        try:
            module, factory = entry.value.split(":")
        except ValueError as exc:
            raise PluginError(f"{pid}: invalid factory entry point") from exc
        if not all(s.isidentifier() for s in module.split(".")) or not factory.isidentifier():
            raise PluginError(f"{pid}: invalid factory entry point")
        package = module.split(".")[0]
        if package == "texstage" or any(not name.startswith(package + "/") for name in inventory):
            raise PluginError(f"{pid}: resources must be owned by one independent Python package")
        if module.replace(".", "/") + ".py" not in inventory and \
                module.replace(".", "/") + "/__init__.py" not in inventory:
            raise PluginError(f"{pid}: factory must be owned by the distribution")
        root = Path(dist.locate_file("")).resolve()
        resources = {}
        if sum(s["size"] for s in inventory.values()) > MAX_PACKAGE:
            raise PluginError(f"{pid}: package exceeds size budget")
        for name, spec in inventory.items():
            resources[name] = verified_file(root, name, spec["sha256"], spec["size"])
        for spec in manifest["capabilities"].get("content_types", {}).values():
            for msg in spec.get("messages", {}).values():
                schema = read_json(resources[msg["schema"]])
                # Validate the schema without executing or resolving external references.
                validate_schema(schema)
                for example in schema.get("examples", []):
                    validate_json(schema, example, label="message schema example")
        schema_paths = {
            path for spec in manifest["capabilities"].get("content_types", {}).values()
            for path in spec.get("view_schemas", {}).values()
        }
        schema_paths.update(spec["result_data_schema"]
                            for spec in manifest["capabilities"].get("engines", {}).values()
                            if "result_data_schema" in spec)
        for path in schema_paths:
            schema = read_json(resources[path])
            validate_portable_schema(schema)
            for example in schema.get("examples", []) if isinstance(schema, dict) else []:
                validate_json(schema, example, label="portable schema example")
        for spec in manifest["capabilities"].get("content_types", {}).values():
            for key in ("value_schema", "summary_schema"):
                if "actor_records" in spec:
                    validate_portable_schema(read_json(resources[spec["actor_records"][key]]))
        result.append(Provider(pid, manifest["version"], dist.metadata["Name"], root, entry.value,
                               digest(manifest), canonical(manifest), MappingProxyType(resources)))
    return tuple(sorted(result, key=lambda p: p.id))


class Catalog:
    def __setattr__(self, key, value):
        if getattr(self, "_frozen", False): raise AttributeError("runtime catalogs are immutable")
        object.__setattr__(self, key, value)

    def __init__(self, providers=()):
        providers = tuple(sorted(providers, key=lambda p: p.id))
        self.providers = MappingProxyType({p.id: p for p in providers})
        if len(self.providers) != len(providers):
            raise PluginError("duplicate enabled provider")
        engines, types, styles, exports, namespaces = {}, {}, {}, {}, set()
        for p in providers:
            m = p.manifest
            ns = m.get("latex_namespace")
            if ns and ns in namespaces:
                raise PluginError(f"duplicate enabled LaTeX namespace: {ns}")
            if ns: namespaces.add(ns)
            for family, target in (("engines", engines), ("content_types", types)):
                for cid, spec in m["capabilities"].get(family, {}).items():
                    if cid in engines or cid in types:
                        raise PluginError(f"duplicate capability: {cid}")
                    target[cid] = (p, canonical(spec))
                    for path in spec.get("latex_packages", []):
                        name = Path(path).name.casefold()
                        if name in styles and styles[name] != (p.id, path):
                            raise PluginError(f"duplicate style filename: {name}")
                        styles[name] = (p.id, path)
            for group in ("commands", "environments"):
                for export in m.get("latex_exports", {}).get(group, []):
                    if export in exports:
                        raise PluginError(f"duplicate LaTeX export: {export}")
                    exports[export] = p.id
        self.engines = MappingProxyType(engines)
        self.types = MappingProxyType(types)
        self.styles = MappingProxyType(styles)
        self.fingerprint = digest([p.requirement() for p in self.providers.values()])
        self._frozen = True

    def capability(self, cid, *, engine=False):
        entry = (self.engines if engine else self.types).get(cid)
        if entry is None:
            raise PluginError(f"capability is not enabled: {cid}")
        provider, raw = entry
        # Catalog construction retained canonical, validated immutable bytes.
        # Decode a fresh snapshot; do not repeat untrusted-input checks or share
        # a mutable capability object with a caller.
        return provider, json.loads(raw)

    @property
    def latex_dirs(self):
        return tuple(sorted({self.providers[pid].root / Path(path).parent
                             for pid, path in self.styles.values()}))

    def requirements(self, types=(), engines=()):
        selected = {}
        for cid, is_engine in [(c, False) for c in types] + [(c, True) for c in engines]:
            p, _ = self.capability(cid, engine=is_engine)
            req = selected.setdefault(p.id, p.requirement() | {"capabilities": []})
            if cid not in req["capabilities"]: req["capabilities"].append(cid)
        for r in selected.values(): r["capabilities"].sort()
        return sorted(selected.values(), key=lambda r: r["id"])

    def check(self, requirements):
        if not isinstance(requirements, list) or not requirements:
            raise PluginError("external bundles require an explicit plugin lock")
        seen = set()
        for req in requirements:
            if not isinstance(req, dict) or set(req) != {"id", "version", "payload", "capabilities"}:
                raise PluginError("invalid bundle plugin requirement")
            p = self.providers.get(req["id"])
            if req["id"] in seen or p is None or any(req[k] != p.requirement()[k] for k in ("id", "version", "payload")):
                raise PluginError(f"missing or mismatched enabled plugin: {req['id']}")
            seen.add(p.id)
            if not isinstance(req["capabilities"], list) or not req["capabilities"]:
                raise PluginError("empty plugin capability requirement")
            for cid in req["capabilities"]:
                entry = self.engines.get(cid) or self.types.get(cid)
                if entry is None or entry[0].id != p.id:
                    raise PluginError(f"unknown required capability: {cid}")


def environment_fingerprint(catalog: Catalog):
    """Runtime resumption is stricter than portable deck/provider identity."""
    distributions = []
    for d in metadata.distributions():
        record = d.read_text("RECORD") or ""
        distributions.append((d.metadata["Name"], d.version, hashlib.sha256(record.encode()).hexdigest()))
    return digest({"catalog": catalog.fingerprint, "plugin_runtime_contract": CONTRACT_VERSION,
                   "python": platform.python_version(),
                   "platform": platform.platform(), "distributions": sorted(distributions)})
