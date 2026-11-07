# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Explicit, enabled-provider preparation before any TeX compilation."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
import tempfile

from texstage.plugins import PluginError
from texstage.plugins.manifest import canonical, digest, read_json
from texstage.plugins.worker import FRAME_MAX, Workers
from .plugins import ITEM, records, source_file, validate_prepared

FRAGMENT_MAX = 128 * 1024
ITEM_MAX = 128


def tex_path(path: Path) -> str:
    text = path.resolve().as_posix()
    if any(c in text for c in "{}%#^\r\n"):
        raise PluginError("prepared TeX paths cannot contain braces, %, #, ^ or newlines")
    return r"\detokenize{" + text + "}"


def sidecar(tex: Path, activities: Path):
    root = tex.resolve().parent
    path = Path(activities).absolute()
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        raise PluginError("the activity file must be under the deck directory") from None
    raw = source_file(root, name)
    value = read_json(raw)
    if not isinstance(value, dict) or set(value) - {"format", "language", "items"} \
            or type(value.get("format")) is not int or value["format"] != 1:
        raise PluginError("activity file requires format 1, items and optional language")
    language = value.get("language", "en")
    if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
        raise PluginError("activity language must be a language tag")
    items = value.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= ITEM_MAX:
        raise PluginError(f"activity file requires 1..{ITEM_MAX} items")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "type", "source"}:
            raise PluginError("each activity requires id, type and source")
        if not isinstance(item["id"], str) or not ITEM.fullmatch(item["id"]) or item["id"].casefold() in seen:
            raise PluginError("activity IDs must be simple and unique")
        if not isinstance(item["type"], str):
            raise PluginError("activity type must be a qualified capability ID")
        seen.add(item["id"].casefold())
    return root, name, raw, language, items


@dataclass
class Preparation:
    root: Path
    directory: Path
    fingerprint: str
    items: dict
    inputs: dict                         # confined authoring-relative name -> bytes
    artifacts: dict = field(default_factory=dict)  # owned filename -> SHA-256
    provider_inputs: dict = field(default_factory=dict)  # pinned package file -> bytes
    state_digest: str = field(init=False, repr=False)

    def __post_init__(self):
        self.state_digest = digest(self.items)

    @property
    def registry(self):
        return self.directory / "registry.tex"

    @property
    def diagnostics(self):
        return [f"{item}: {d}" for item, row in self.items.items() for d in row["prepared"]["diagnostics"]]

    def validate(self, catalog):
        if digest(self.items) != self.state_digest:
            raise PluginError("prepared item data changed; prepare again")
        if catalog is None or catalog.fingerprint != self.fingerprint:
            raise PluginError("prepared provider identity changed; prepare again")
        for provider in catalog.providers.values():
            provider.verify()
        for name, raw in self.inputs.items():
            if source_file(self.root, name) != raw:
                raise PluginError(f"stale prepared source: {name}; prepare again")
        if self.directory.is_symlink() or self.directory.is_junction():
            raise PluginError("prepared directory changed; prepare again")
        for name, expected in self.artifacts.items():
            path = self.directory / name
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise PluginError("prepared artifact changed; prepare again")

    def validate_rows(self, rows):
        seen = {}
        for fields in rows:
            if len(fields) != 3:
                raise PluginError("invalid prepared activity record")
            item, cid, identity = fields
            if item not in self.items:
                raise PluginError(f"extra prepared activity record: {item}")
            expected = self.items[item]
            if (cid, identity) != (expected["type"], expected["digest"]):
                raise PluginError(f"mismatched prepared activity record: {item}")
            seen[item] = identity
        if set(seen) != set(self.items):
            raise PluginError("missing prepared activity records: " + ", ".join(sorted(set(self.items) - set(seen))))

    def validate_compile(self, record_file: Path):
        if not record_file.is_file():
            raise PluginError("missing prepared activity record file; load the current texstage.sty")
        self.validate_rows([line.strip().split("|") for line in
                            record_file.read_text(encoding="utf-8").splitlines() if line.strip()])

    def validate_tqz(self, tqz):
        self.validate_rows(tqz.records.get("prepared", []))
        definitions = records(tqz)
        placed = {i.id for p in tqz.pages.values() for i in p.items if i.kind == "plugin"}
        builtins = {i.id for p in tqz.pages.values() for i in p.items if i.kind != "plugin"}
        for item, row in self.items.items():
            if item not in placed or item not in definitions or item in builtins:
                raise PluginError(f"missing or conflicting prepared live box: {item}")
            record = definitions[item]
            if record["type"] != row["type"] or any(record[k] for k in ("public", "private", "public_json", "private_json")):
                raise PluginError(f"conflicting prepared live data: {item}")

    def preamble(self):
        # Only the host writes this path, never an exercise or a plugin.
        return r"\def\texstagepreparedfile{" + tex_path(self.registry) + "}"

    def write(self, name, raw):
        path = self.directory / name
        identity = hashlib.sha256(raw).hexdigest()
        if name in self.artifacts and self.artifacts[name] != identity:
            raise PluginError("prepared artifact name collision")
        path.write_bytes(raw)
        self.artifacts[name] = identity
        return path

    def materialize(self):
        registry = ["% Host-generated; regenerate with texstage prepare. Contains local private build references."]
        for path, raw in [(self.root / n, b) for n, b in self.inputs.items()] + list(self.provider_inputs.items()):
            md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest().upper()
            registry.append(r"\texstagepreparedcheck{" + tex_path(path) + "}{" + md5 + "}")
        for item, row in self.items.items():
            for kind, text in row["fragments"].items():
                path = self.write(f"{item}-{kind}.tex", text.encode("utf-8"))
                registry.append(r"\texstagepreparedcheck{" + tex_path(path) + "}{" +
                                hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest().upper() + "}")
            registry.append(r"\texstageprepareddeclare{" + item + "}{" + row["type"] + "}{" + row["digest"] +
                            "}{" + tex_path(self.directory / f"{item}-exercise.tex") +
                            "}{" + tex_path(self.directory / f"{item}-solutions.tex") + "}")
            for logical, asset in row["prepared"]["assets"].items():
                raw = self.inputs[asset["source"]]
                # Keep local TeX paths below common Windows limits; full hashes are
                # retained in the artifact inventory and collisions fail in write().
                name = "asset-" + hashlib.sha256(raw).hexdigest()[:20] + Path(asset["source"]).suffix.lower()
                path = self.write(name, raw)
                registry.append(r"\texstagepreparedassetdeclare{" + item + "}{" + logical +
                                "}{" + tex_path(path) + "}{" + asset["visibility"] + "}")
                registry.append(r"\texstagepreparedcheck{" + tex_path(path) + "}{" +
                                hashlib.md5(raw, usedforsecurity=False).hexdigest().upper() + "}")
        self.write("registry.tex", ("\n".join(registry) + "\n").encode("utf-8"))
        inventory = {"format": 1, "provider_fingerprint": self.fingerprint,
                     "items": {i: {"type": r["type"], "digest": r["digest"]} for i, r in self.items.items()},
                     "files": dict(self.artifacts)}
        self.write("preparation.json", canonical(inventory))

    def export(self, tex: Path, catalog):
        """Materialize mode-specific direct-pdfLaTeX entry points; no code runs in TeX."""
        from .latex import LATEX_DIR
        self.validate(catalog)
        paths = [LATEX_DIR, *catalog.latex_dirs, self.root]
        # LaTeX's input path is local to this explicitly materialized entry point.
        input_path = "".join("{" + tex_path(p) + "/}" for p in paths)
        result = {}
        for mode in ("handout", "solutions", "present"):
            text = (r"\makeatletter\def\input@path{" + input_path + r"}\makeatother" + "\n" +
                    rf"\def\texquizmode{{{mode}}}" + self.preamble() + "\n" +
                    r"\input{" + tex_path(tex) + "}\n")
            result[mode] = self.write(f"{tex.stem}-{mode}-prepared.tex", text.encode("utf-8"))
        return result


def prepare_sources(tex: Path, activities: Path, catalog, output_dir: Path) -> Preparation:
    root, name, raw, language, declarations = sidecar(tex, activities)
    inputs = {name: raw}
    def remember(name, raw):
        if name in inputs and inputs[name] != raw:
            raise PluginError("activity source changed during preparation")
        inputs[name] = raw
    items, provider_inputs = {}, {}
    # Fail metadata/path checks before importing any enabled provider.
    sources = []
    for row in declarations:
        provider, spec = catalog.capability(row["type"])
        if "authoring_hook" not in spec:
            raise PluginError(f"{row['type']} does not declare an authoring_hook")
        data = source_file(root, row["source"])
        value = read_json(data, limit=2 * 1024 * 1024)
        if not isinstance(value, dict):
            raise PluginError("activity source must be a JSON object")
        remember(row["source"], data)
        sources.append((row, provider, spec, value, data))
    workers = Workers(catalog)
    try:
        for row, provider, spec, value, raw in sources:
            source_identity = hashlib.sha256(raw).hexdigest()
            ctx = {"item_id": row["id"], "type": row["type"], "language": language,
                   "source": {"path": row["source"], "sha256": source_identity},
                   "limits": {"fragment_bytes": FRAGMENT_MAX, "response_bytes": FRAME_MAX}}
            made = workers.call(row["type"], "prepare_source", value, ctx)
            if not isinstance(made, dict) or set(made) != {"format", "prepared", "fragments"} \
                    or type(made["format"]) is not int or made["format"] != 1:
                raise PluginError("authoring hook must return PreparedAuthoring format 1")
            if len(canonical(made)) > FRAME_MAX:
                raise PluginError("authoring response exceeds JSON budget")
            fragments = made["fragments"]
            if not isinstance(fragments, dict) or set(fragments) != {"exercise", "solutions"} or any(
                    not isinstance(v, str) or "\0" in v or len(v.encode("utf-8")) > FRAGMENT_MAX
                    for v in fragments.values()):
                raise PluginError("authoring requires bounded exercise and solutions TeX fragments")
            validate_prepared(made["prepared"], spec)
            assets = {}
            for logical, asset in made["prepared"]["assets"].items():
                if not ITEM.fullmatch(logical):
                    raise PluginError("prepared asset names must be simple identifiers")
                data = source_file(root, asset["source"])
                remember(asset["source"], data)
                assets[logical] = hashlib.sha256(data).hexdigest()
            # Verify dependent engines now, before compiling the static materials.
            for binding in spec.get("evaluations", {}).values():
                catalog.capability(binding["engine"], engine=True)
            identity = digest({"format": 1, "providers": catalog.requirements(
                                   [row["type"]], [b["engine"] for b in spec.get("evaluations", {}).values()]),
                               "source": source_identity, "type": row["type"], "item": row["id"],
                               "language": language, "assets": assets, "prepared": made})
            items[row["id"]] = {"type": row["type"], "digest": identity, **made}
        # Direct-TeX exports detect edits to approved package files as well as inputs.
        for provider in catalog.providers.values():
            provider.verify()
            provider_inputs.update({provider.root / p: b for p, b in provider.resources.items()})
    finally:
        workers.close()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="prepared-", dir=output_dir))
    result = Preparation(root, directory, catalog.fingerprint, items, inputs, provider_inputs=provider_inputs)
    result.materialize()
    result.validate(catalog)
    return result
