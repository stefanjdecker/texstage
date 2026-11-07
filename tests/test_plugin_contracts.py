# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Revision-2 boundaries and domain concurrency on the durable host."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from texstage.plugins import PluginError
from texstage.plugins.catalog import discover
from texstage.plugins.contracts import (
    DATA_MAX, namespace, result_contract, summary_schema, validate_outcome, validate_portable_schema,
)
from texstage.plugins.manifest import canonical, digest, load_manifest, read_json, validate_json
from texstage.plugin_api.v1 import evaluation_correlation
from test_plugins import Hooks, command, distribution, provider, start

PID = "org.example.fixture"
ENGINE = PID + ".engine"
TYPE = PID + ".plane"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["valid", "order"],
          "properties": {"valid": {"type": "boolean"},
                         "order": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True}}}
VIEW = {"type": "object", "additionalProperties": False, "required": ["values", "active", "finished"],
        "properties": {"values": {"type": "array", "items": {"type": "integer"}},
                       "active": {"type": "boolean"}, "finished": {"type": "array", "items": {"type": "string"}}}}


def installed(tmp_path, schema=SCHEMA, mutate=None):
    def revise(m):
        m["manifest_version"] = 2
        m["capabilities"]["engines"][ENGINE]["result_data_schema"] = "fixture_plugin/result.json"
        content = m["capabilities"]["content_types"][TYPE]
        content["view_schemas"] = {s: "fixture_plugin/view.json" for s in content["views"]}
        if mutate: mutate(m)
    return discover(distributions=[distribution(tmp_path, modify=revise, extra_resources={
        "fixture_plugin/result.json": canonical(schema), "fixture_plugin/view.json": canonical(VIEW)})])[0]


@pytest.fixture
def typed(tmp_path):
    return installed(tmp_path / "typed")


def outcome(job, **changes):
    return {"status": "ok", "key": "a" * 16, "namespace": job["namespace"],
            "summary": {"kind": "text", "text": "Analyzed"},
            "data": {"valid": True, "order": ["a", "b"]}} | changes


def finish(r, job, value, owner="evaluator", now=11):
    return r.finish("session", owner, {k: job[k] for k in ("id", "epoch", "generation")} |
                    {"outcome": value}, now=now)


class CapturingHooks(Hooks):
    def __init__(self):
        super().__init__()
        self.results = []

    def call(self, kind, method, *args):
        if method == "transition" and args[1]["kind"] == "evaluation.finished":
            self.results.append(copy.deepcopy(args[1]))
        return super().call(kind, method, *args)


def test_typed_facts_survive_restart_and_deliver_once(tmp_path, typed):
    r = start(tmp_path, typed)
    r.command("session", "alice", "participant", command())
    job = r.lease("session", "evaluator", now=10)[0]
    value = outcome(job)
    assert finish(r, job, value)
    r.close()
    hooks = CapturingHooks()
    r = start(tmp_path, typed, hooks=hooks)
    try:
        r.drain("session"); r.drain("session")
        assert len(hooks.results) == 1
        assert hooks.results[0]["outcome"] == value
        assert hooks.results[0]["actor"] == "alice"
        assert not finish(r, job, value)
    finally: r.close()


@pytest.mark.parametrize("change", [
    {"data": {"valid": "yes", "order": ["a"]}},
    {"data": {"valid": True, "order": ["a"], "private": "unintended field"}},
    {"data": {"valid": True, "order": ["a", "a"]}},
    {"data": {"valid": True, "order": ["ü" * 1400]}},
    {"data": {"valid": True, "order": [float("nan")]}},
    {"summary": {"kind": "text"}},
    {"summary": {"kind": "text", "text": "x", "html": "<script/>"}},
    {"namespace": "f" * 64}, {"key": "not-a-key"}, {"matches": True},
])
def test_invalid_outcomes_do_not_consume_lease(tmp_path, typed, change):
    r = start(tmp_path, typed)
    try:
        r.command("session", "alice", "participant", command())
        job = r.lease("session", "evaluator", now=10)[0]
        with pytest.raises(PluginError): finish(r, job, outcome(job, **change))
        assert r.db.execute("SELECT status FROM jobs").fetchone()[0] == "leased"
        assert finish(r, job, outcome(job))
    finally: r.close()


def test_revision_one_still_works_and_rejects_undeclared_data(tmp_path, provider):
    r = start(tmp_path, provider)
    try:
        r.command("session", "alice", "participant", command())
        job = r.lease("session", "evaluator", now=10)[0]
        with pytest.raises(PluginError, match="declared"): finish(r, job, outcome(job))
        old = outcome(job); del old["data"]
        assert finish(r, job, old)
    finally: r.close()


def test_namespace_includes_schema_and_contract_identity(typed):
    engine = typed.manifest["capabilities"]["engines"][ENGINE]
    binding = {"seed": "{}", "references": []}
    first = namespace(typed, ENGINE, engine, binding)
    summary_only = dict(engine); del summary_only["result_data_schema"]
    assert first != namespace(typed, ENGINE, summary_only, binding)
    assert result_contract(typed, engine)["data_schema_digest"] == digest(SCHEMA)


def test_manifest_versions_missing_resources_and_view_coverage(typed):
    m = typed.manifest
    assert load_manifest(canonical(m)) == m
    v3 = copy.deepcopy(m); v3["manifest_version"] = 3
    assert load_manifest(canonical(v3)) == v3
    v4 = copy.deepcopy(m); v4["manifest_version"] = 4
    load_manifest(canonical(v4))
    for revision in (1, 5, True):
        bad = copy.deepcopy(m); bad["manifest_version"] = revision
        with pytest.raises(PluginError): load_manifest(canonical(bad))
    bad = copy.deepcopy(m); del bad["resources"]["fixture_plugin/result.json"]
    with pytest.raises(PluginError, match="resource"): load_manifest(canonical(bad))
    bad = copy.deepcopy(m)
    del bad["capabilities"]["content_types"][TYPE]["view_schemas"]["participant-input"]
    with pytest.raises(PluginError, match="exactly"): load_manifest(canonical(bad))
    bad = copy.deepcopy(m)
    bad["capabilities"]["content_types"][TYPE]["authoring_hook"] = "future"
    with pytest.raises(PluginError): load_manifest(canonical(bad))


@pytest.mark.parametrize("schema", [
    {"$ref": "https://example.invalid/schema"}, {"$ref": "#/$defs/missing"},
    {"$defs": {"x": {"$ref": "#/$defs/x"}}, "$ref": "#/$defs/x"},
    {"$defs": {"x%25": {"type": "string"}}, "$ref": "#/$defs/x%25"},
    {"$defs": {"x~2": {"type": "string"}}, "$ref": "#/$defs/x~2"},
    {"type": "string", "pattern": ".*"}, {"type": "number", "multipleOf": .1},
    {"type": "object", "unevaluatedProperties": False}, {"format": "email"},
])
def test_discovery_rejects_unsupported_schemas_before_factory_import(tmp_path, schema):
    with pytest.raises(PluginError): installed(tmp_path / "invalid", schema=schema)


def test_view_schema_rejects_private_field_on_exact_surface(tmp_path, typed):
    class LeakingHooks(Hooks):
        def call(self, kind, method, *args):
            result = super().call(kind, method, *args)
            if method == "view": result["answer"] = "private"
            return result
    r = start(tmp_path, typed, hooks=LeakingHooks())
    try:
        with pytest.raises(PluginError, match="surface view"):
            r.view("session", TYPE, "item", "participant", "participant-input", "alice")
    finally: r.close()


def test_reset_uses_epoch_despite_unrelated_submissions(tmp_path, provider):
    r = start(tmp_path, provider)
    try:
        reset = command("reset-request", operation="_reset", expected_revision=1, payload={})
        for n in range(100):
            r.command("session", f"actor{n}", "participant", command(f"submission{n:04}"))
        old_job = r.lease("session", "evaluator", now=10)[0]
        accepted = r.command("session", "teacher", "presenter", reset)
        assert accepted["accepted"] and accepted["epoch"] == 2
        assert r.command("session", "teacher", "presenter", reset) == accepted
        assert r.command("session", "other-teacher", "presenter",
                         reset | {"request_id": "other-reset"})["error"] == "stale-epoch"
        assert not finish(r, old_job, {"status": "error"})
        assert not r.lease("session", "evaluator", now=20)
        assert r._item("session", TYPE, "item")["revision"] == 0
    finally: r.close()


def test_valid_repairs_are_not_canonical_reference_matches(tmp_path, typed):
    hooks = CapturingHooks()
    r = start(tmp_path, typed, hooks=hooks)
    try:
        for n, actor in enumerate(("alice", "bob")):
            r.command("session", actor, "participant", command(f"repair{n:04}"))
        jobs = r.lease("session", "evaluator", now=10)
        for job, order, key in zip(jobs, (["a", "b"], ["b", "a"]), ("a", "b")):
            assert finish(r, job, outcome(job, key=key * 16, data={"valid": True, "order": order}))
        r.drain("session")
        assert all(e["outcome"]["data"]["valid"] for e in hooks.results)
        assert all("matches" not in e["outcome"] for e in hooks.results)
        assert hooks.results[0]["outcome"]["key"] != hooks.results[1]["outcome"]["key"]
    finally: r.close()


def test_summary_shapes_dimensions_and_total_budget(typed):
    engine = typed.manifest["capabilities"]["engines"][ENGINE] | {"summary_kinds": ["select", "ask", "graph", "text"]}
    job = {"namespace": "x"}
    for summary in ({"kind": "ask", "boolean": True},
                    {"kind": "graph", "count": 1, "rows": [["s", "p", "o"]]},
                    {"kind": "select", "columns": ["x"], "count": 1, "rows": [["1"]]}):
        validate_outcome(outcome(job, summary=summary), typed, engine, "x")
    for summary in ({"kind": "ask", "boolean": "true"},
                    {"kind": "graph", "count": 1, "rows": [["s", "p"]]},
                    {"kind": "select", "columns": ["x"], "count": 0, "rows": [["1"]]}):
        with pytest.raises(PluginError): validate_outcome(outcome(job, summary=summary), typed, engine, "x")
    value = outcome(job, summary={"kind": "text", "text": "x" * 8000},
                    data={"valid": True, "order": ["x" * 5000]})
    assert len(canonical(value["data"])) < DATA_MAX
    with pytest.raises(PluginError, match="budget"): validate_outcome(value, typed, engine, "x")


def test_latest_reducers_keep_actor_and_control_guards_separate(tmp_path):
    payload_schema = {"type": "object", "additionalProperties": False,
                      "properties": {k: {"type": "integer"} for k in ("phase", "answer", "control")}}
    def latest(m):
        m["capabilities"]["content_types"][TYPE]["messages"]["reveal"]["revision_policy"] = "latest"
    p = discover(distributions=[distribution(tmp_path / "scoped", modify=latest,
        extra_resources={"fixture_plugin/message.json": canonical(payload_schema)})])[0]

    class Scoped(Hooks):
        def call(self, kind, method, *args):
            if method == "initial_state": return {"phase": 1, "control": 0, "open": True, "answers": {}}
            if method == "view": return copy.deepcopy(args[0])
            state, event, ctx = copy.deepcopy(args)
            effects = []
            if event["kind"] == "command":
                body = event["payload"]
                if event["operation"] == "reveal":
                    if body["control"] != state["control"]: return {"refusal": "stale-control"}
                    state["control"] += 1; state["open"] = False; state["phase"] += 1
                else:
                    if not state["open"] or body["phase"] != state["phase"]: return {"refusal": "stale-phase"}
                    actor = event["actor"]
                    old = state["answers"].get(actor, {})
                    if body["answer"] != old.get("version", 0): return {"refusal": "stale-answer"}
                    correlation = evaluation_correlation(actor, event["request_id"], "answer")
                    state["answers"][actor] = {"version": old.get("version", 0) + 1, "correlation": correlation, "status": "queued"}
                    effects = [{"kind": "evaluate", "binding": "value", "correlation_id": correlation, "text": "answer"}]
            elif event["kind"] == "evaluation.finished":
                slot = state["answers"].get(event["actor"])
                if slot and slot["correlation"] == event["correlation_id"]:
                    slot["status"] = event["outcome"]["status"]
            return {"state": state, "effects": effects}

    r = start(tmp_path, p, hooks=Scoped())
    try:
        answer = command("same-request", payload={"phase": 1, "answer": 0})
        # The same client request string from two actors creates separate jobs.
        a = r.command("session", "alice", "participant", answer)
        b = r.command("session", "bob", "participant", answer)
        assert a["accepted"] and b["accepted"] and set(a["jobs"]).isdisjoint(b["jobs"])
        jobs = r.lease("session", "evaluator", now=10)
        assert len(jobs) == 2
        assert r.command("session", "alice", "participant", answer | {"request_id": "conflicting-edit"})["error"] == "stale-answer"
        assert r.command("session", "alice", "participant", answer | {
            "request_id": "replacement", "payload": {"phase": 1, "answer": 1}})["accepted"]
        # Closing uses the control version, unaffected by participant item revisions.
        close = command("close-request", operation="reveal", payload={"control": 0})
        assert r.command("session", "teacher", "presenter", close)["accepted"]
        assert r.command("session", "teacher2", "presenter", close | {"request_id": "conflicting-close"})["error"] == "stale-control"
        assert r.command("session", "charlie", "participant", answer)["error"] == "stale-phase"
        for job in jobs: assert finish(r, job, {"status": "error"})
        r.drain("session")
        state = read_json(r._item("session", TYPE, "item")["state"])
        assert state["answers"]["alice"]["status"] == "queued"  # old answer's completion ignored
        assert state["answers"]["bob"]["status"] == "error"  # accepted closed-phase answer delivered
        replacement = r.lease("session", "evaluator", now=12)[0]
        assert finish(r, replacement, {"status": "refused"}, now=13)
        r.drain("session")
        assert read_json(r._item("session", TYPE, "item")["state"])["answers"]["alice"]["status"] == "refused"
        assert r.command("session", "teacher", "presenter", close)["accepted"]  # durable lost-ACK replay
    finally: r.close()


@pytest.mark.skipif(shutil.which("node") is None, reason="requires Node")
def test_browser_contracts_and_python_schema_agree(tmp_path):
    fixtures = json.loads(Path(__file__).with_name("plugin-schema-cases.json").read_text(encoding="utf-8"))
    for case in fixtures:
        validate_portable_schema(case["schema"])
        try:
            validate_json(case["schema"], case["value"])
            valid = True
        except PluginError:
            valid = False
        assert valid == case["valid"], case["name"]
    report = tmp_path / "contracts.json"
    report.write_bytes(canonical({"schema": SCHEMA, "summary": summary_schema(), "cases": fixtures}))
    result = subprocess.run([shutil.which("node"), "--test", str(Path(__file__).with_name("web-plugin-contracts.test.mjs"))],
                            env=__import__("os").environ | {"TEXSTAGE_CONTRACT_FIXTURE": str(report)},
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
