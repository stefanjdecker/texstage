# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Strict metadata validation. Reading a manifest never imports plugin code."""
from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator
from packaging.version import InvalidVersion, Version

from . import PluginError

ID = r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+"
QUALIFIED = re.compile(ID + r"\Z")
RESERVED = {"sql", "sparql", "turtle", "quiz", "video", "activity"}
CORE_STYLES = {"texstage.sty", "texquiz.sty", "texvideo.sty", "texactivity.sty"}
MAX_JSON = 1024 * 1024


def canonical(value) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("ascii")
    except (ValueError, TypeError, RecursionError) as exc:
        raise PluginError("expected a finite JSON value") from exc


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(raw: bytes | str, *, limit: int = MAX_JSON):
    if len(raw) > limit:
        raise PluginError(f"JSON exceeds {limit} bytes")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PluginError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(PluginError("non-finite JSON")))
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PluginError(f"invalid JSON: {exc}") from exc


def resource_path(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 240 or
            any(c in value for c in "\\:\x00%?#") or
            any(ord(c) < 32 for c in value) or
            value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/"))):
        raise PluginError(f"invalid package resource path: {value!r}")
    if any(p.endswith((" ", ".")) for p in value.split("/")):
        raise PluginError(f"non-portable package path: {value}")
    return PurePosixPath(value).as_posix()


@lru_cache(maxsize=128)
def _schema_validator(raw: bytes):
    # Cache successful safety checks only. A validator's ValidationError can
    # expose its schema, so retaining a validator would permit cache poisoning.
    schema = json.loads(raw)
    def refs(node):
        if isinstance(node, dict):
            if "$ref" in node and not str(node["$ref"]).startswith("#"):
                raise PluginError("JSON schemas may only use local fragment references")
            if "$dynamicRef" in node or "$id" in node:
                raise PluginError("external schema scopes and dynamic references are not supported")
            for v in node.values(): refs(v)
        elif isinstance(node, list):
            for v in node: refs(v)
    refs(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise PluginError(f"invalid JSON schema: {str(exc)[:500]}") from exc
    return None


def _validator(schema):
    raw = canonical(schema)
    # Bound retained schema bytes as well as entry count. Large valid schemas
    # still work, but do not occupy the cache.
    if len(raw) > 64 * 1024:
        _schema_validator.__wrapped__(raw)
    else:
        _schema_validator(raw)
    # Each instance validation owns a fresh snapshot, including errors exposed
    # through PluginError.__cause__. Never retain caller- or error-owned objects.
    return Draft202012Validator(json.loads(raw))


def validate_schema(schema: dict):
    _validator(schema)


def validate_json(schema: dict, value, *, label="value"):
    validator = _validator(schema)
    try:
        validator.validate(value)
    except Exception as exc:
        path = ".".join(str(p) for p in getattr(exc, "absolute_path", ())) or "root"
        rule = getattr(exc, "validator", "validation")
        raise PluginError(f"{label} does not satisfy its schema at {path} ({rule})") from exc


def validate_bindings(bindings, declared, *, prepared=False):
    """Apply the same limits to build-hook output and uploaded bundle data."""
    if not isinstance(bindings, dict) or set(bindings) != set(declared):
        raise PluginError("evaluation bindings disagree with manifest")
    for name, options in bindings.items():
        allowed = {"seed", "options", "references"} | ({"engine"} if prepared else set())
        if not isinstance(options, dict) or set(options) - allowed:
            raise PluginError("invalid evaluation binding fields")
        if prepared and options.get("engine") != declared[name]["engine"]:
            raise PluginError("evaluation engine disagrees with manifest")
        seed = options.get("seed", "")
        if not isinstance(seed, str) or len(seed.encode("utf-8")) > 2 * 1024 * 1024:
            raise PluginError("invalid evaluation seed")
        refs = options.get("references", [])
        if not isinstance(refs, list) or len(refs) > 32 or any(not isinstance(r, str) or len(r) > 2000 for r in refs):
            raise PluginError("invalid evaluation references")
        settings = options.get("options", {})
        if not isinstance(settings, dict) or len(canonical(settings)) > 64 * 1024:
            raise PluginError("invalid evaluation options")


def load_manifest(raw: bytes | str) -> dict:
    value = read_json(raw)
    version = value.get("manifest_version") if isinstance(value, dict) else None
    if type(version) is not int or version not in (1, 2, 3, 4, 5):
        raise PluginError("unsupported plugin manifest version; this host supports revisions 1, 2 and 3")
    schema = read_json((Path(__file__).parent / "schemas" / f"manifest-v{version}.json").read_bytes())
    validate_json(schema, value, label="plugin manifest")
    pid = value["id"]
    if pid.startswith(("texstage.", "org.texstage.")):
        raise PluginError(f"reserved plugin ID: {pid}")
    try:
        if str(Version(value["version"])) != value["version"]:
            raise PluginError("version must be normalized PEP 440")
    except InvalidVersion as exc:
        raise PluginError("invalid plugin version") from exc
    resources = value["resources"]
    folded = set()
    for name in resources:
        resource_path(name)
        if name.casefold() in folded:
            raise PluginError(f"case-insensitive resource collision: {name}")
        folded.add(name.casefold())
        if Path(name).suffix.lower() in {".dll", ".pyd", ".so", ".dylib", ".exe"}:
            raise PluginError("API 1 requires portable py3-none-any plugin wheels")
    def resource(name, suffix=None):
        resource_path(name)
        if name not in resources or (suffix and not name.endswith(suffix)):
            raise PluginError(f"missing or invalid declared resource: {name}")
    styles = set()
    namespace = value.get("latex_namespace")
    capabilities = value["capabilities"]
    seen = set()
    for family in ("engines", "content_types"):
        for cid, spec in capabilities.get(family, {}).items():
            if not cid.startswith(pid + ".") or cid in seen:
                raise PluginError(f"capability must belong to {pid} and be unique: {cid}")
            seen.add(cid)
            if family == "engines":
                resource(spec["module"], ".mjs")
                for asset in spec.get("assets", []): resource(asset)
                if "result_data_schema" in spec: resource(spec["result_data_schema"], ".json")
            else:
                for path in spec.get("latex_packages", []):
                    resource(path, ".sty")
                    name = Path(path).name
                    if not namespace or not re.fullmatch(rf"texstage-{namespace}-[a-z][a-z0-9-]*\.sty", name):
                        raise PluginError(f"style filename must use the declared namespace: {name}")
                    styles.add(name)
                for path in spec["views"].values(): resource(path, ".mjs")
                if version >= 2:
                    if set(spec["view_schemas"]) != set(spec["views"]):
                        raise PluginError("view_schemas must cover exactly the declared surfaces")
                    for path in spec["view_schemas"].values(): resource(path, ".json")
                if "actor_records" in spec:
                    for key in ("value_schema", "summary_schema"):
                        resource(spec["actor_records"][key], ".json")
                for msg in spec.get("messages", {}).values():
                    resource(msg["schema"], ".json")
                    if "record_actor_field" in msg and (
                            "actor_records" not in spec or msg["from"] != ["presenter"]):
                        raise PluginError("actor record reads require a presenter-only message and actor_records")
                if any("participant" in m["from"] for m in spec.get("messages", {}).values()) \
                        and "participant-input" not in spec["views"]:
                    raise PluginError(f"{cid}: participant messages require a participant-input view")
    if not seen:
        raise PluginError("a plugin must declare at least one capability")
    for group in ("commands", "environments"):
        for name in value.get("latex_exports", {}).get(group, []):
            if not namespace or not name.startswith(namespace):
                raise PluginError(f"LaTeX export must start with its namespace: {name}")
    # Every style, including supporting styles, has explicit ownership.
    if {Path(p).name for p in resources if p.endswith(".sty")} != styles:
        raise PluginError("every packaged style must be declared in latex_packages")
    return value
