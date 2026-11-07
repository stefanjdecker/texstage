# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Bounded, non-executable result/view contracts shared with the browser.

New result/view schemas use an explicit portable subset of JSON Schema 2020-12.
Unknown keywords fail discovery instead of being silently ignored in JavaScript.
Command schemas retain their existing server-only JSON Schema support.
"""
from functools import lru_cache
from pathlib import Path
import math
import re

from . import PluginError
from .manifest import canonical, digest, read_json, validate_json, validate_schema

OUTCOME_MAX = 12 * 1024
DATA_MAX = 8 * 1024
SCHEMA_MAX = 32 * 1024
CONTRACT_VERSION = 2
ANNOTATIONS = {"$schema", "title", "description", "$comment", "examples", "default"}
KEYWORDS = ANNOTATIONS | {
    "$defs", "$ref", "type", "enum", "const", "properties", "required",
    "additionalProperties", "minProperties", "maxProperties", "items", "prefixItems",
    "minItems", "maxItems", "uniqueItems", "minLength", "maxLength", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "allOf", "anyOf", "oneOf", "not",
}


def json_data(value, depth=0):
    """Reject values that cannot round-trip through JSON and browser numbers."""
    if depth > 64:
        raise PluginError("JSON nesting exceeds contract budget")
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        if abs(value) > 9007199254740991 or not math.isfinite(value):
            raise PluginError("JSON number exceeds the portable finite-number range")
        return
    if type(value) is list:
        for item in value: json_data(item, depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values(): json_data(item, depth + 1)
        return
    raise PluginError("expected plain JSON data")


def validate_portable_schema(schema):
    if len(canonical(schema)) > SCHEMA_MAX:
        raise PluginError("portable schema exceeds 32 KiB")
    json_data(schema)
    validate_schema(schema)
    visits = 0

    def walk(node, stack=(), depth=0):
        nonlocal visits
        visits += 1
        if visits > 2048 or depth > 32:
            raise PluginError("portable schema exceeds complexity budget")
        if isinstance(node, bool): return
        if not isinstance(node, dict) or set(node) - KEYWORDS:
            raise PluginError("unsupported portable schema keyword")
        if "$schema" in node and node["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            raise PluginError("portable schemas require JSON Schema 2020-12")
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/") or ref in stack or "%" in ref or re.search(r"~(?![01])", ref):
                raise PluginError("portable schema references must be acyclic local JSON pointers")
            target = schema
            try:
                for part in ref[2:].split("/"):
                    key = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(target, list):
                        if not re.fullmatch(r"0|[1-9][0-9]*", key): raise KeyError(key)
                        target = target[int(key)]
                    else:
                        target = target[key]
            except (KeyError, TypeError, IndexError) as exc:
                raise PluginError("unresolved portable schema reference") from exc
            walk(target, (*stack, ref), depth + 1)
        for keyword in ("$defs", "properties"):
            for child in node.get(keyword, {}).values(): walk(child, stack, depth + 1)
        for keyword in ("additionalProperties", "items", "not"):
            if keyword in node: walk(node[keyword], stack, depth + 1)
        for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
            for child in node.get(keyword, []): walk(child, stack, depth + 1)
    walk(schema)


@lru_cache(maxsize=256)
def _portable(raw):
    schema = read_json(raw, limit=SCHEMA_MAX)
    validate_portable_schema(schema)
    return schema


def resource_schema(provider, path):
    return _portable(provider.resources[path])


def result_contract(provider, engine):
    path = engine.get("result_data_schema")
    schema = resource_schema(provider, path) if path else None
    return {"version": CONTRACT_VERSION, "summary_schema": summary_schema(),
            "data_schema": schema, "data_schema_digest": digest(schema) if path else None,
            "data_max": DATA_MAX, "outcome_max": OUTCOME_MAX}


@lru_cache(maxsize=1)
def summary_schema():
    return read_json((Path(__file__).parent / "schemas" / "engine-summary-v1.json").read_bytes())


def namespace(provider, engine_id, engine, binding):
    schema = result_contract(provider, engine)["data_schema_digest"]
    return digest({"provider": provider.requirement(), "engine": engine_id,
                   "format": engine["canonical_format"], "binding": binding,
                   "result_contract": CONTRACT_VERSION, "result_data_schema": schema})


def validate_outcome(outcome, provider, engine, expected_namespace, *, references=False):
    json_data(outcome)
    if not isinstance(outcome, dict) or len(canonical(outcome)) > OUTCOME_MAX:
        raise PluginError("invalid evaluation outcome or output budget exceeded")
    status = outcome.get("status")
    if status not in ("ok", "syntax", "error", "refused", "timeout"):
        raise PluginError("invalid evaluation outcome status")
    if status != "ok":
        if set(outcome) != {"status"}:
            raise PluginError("failed evaluations carry only a bounded status")
        return
    required = {"status", "key", "namespace", "summary"}
    if (not required <= set(outcome) or set(outcome) - required - {"matches", "data"} or
            outcome["namespace"] != expected_namespace or
            not isinstance(outcome["key"], str) or not re.fullmatch(r"[a-f0-9]{16}", outcome["key"]) or
            ("matches" in outcome) != bool(references) or
            ("matches" in outcome and type(outcome["matches"]) is not bool)):
        raise PluginError("evaluation result does not match its engine contract")
    summary = outcome["summary"]
    validate_json(summary_schema(), summary, label="engine summary")
    if summary["kind"] not in engine["summary_kinds"]:
        raise PluginError("undeclared engine summary kind")
    if "rows" in summary:
        width = 3 if summary["kind"] == "graph" else len(summary["columns"])
        if len(summary["rows"]) > summary["count"] or any(len(row) != width for row in summary["rows"]):
            raise PluginError("engine summary rows disagree with columns or count")
    if "data" in outcome:
        path = engine.get("result_data_schema")
        if not path: raise PluginError("engine data requires a declared result_data_schema")
        if len(canonical(outcome["data"])) > DATA_MAX:
            raise PluginError("engine data exceeds 8 KiB")
        validate_json(resource_schema(provider, path), outcome["data"], label="engine data")
