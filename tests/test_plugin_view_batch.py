# SPDX-License-Identifier: Apache-2.0
"""Batched IPC preserves per-view privacy, validation and kill deadlines."""
import copy
import io
import json
import queue
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

import pytest

from texstage.plugin_api.v1 import PluginV1
from texstage.plugins import PluginError, worker
from texstage.plugins.manifest import canonical, validate_json_many
from texstage.server.plugins import PluginHost
from test_plugins import Hooks, start
from test_plugin_contracts import TYPE, typed
from test_plugins import command


def audiences(count=65):
    return [{"role": "participant", "surface": "participant-input", "actor": str(i)} for i in range(count)]


class BatchedHooks(Hooks):
    def __init__(self):
        super().__init__()
        self.batches = []
        self.bad = None

    def views(self, kind, state, audience, ctx):
        self.batches.append(copy.deepcopy(audience))
        result = [copy.deepcopy(state) for a in audience]
        if self.bad == "schema": result[-1]["private"] = "must not leave the host"
        if self.bad == "size": result[-1]["finished"] = ["x" * (128 * 1024)]
        return result


def test_batch_one_committed_revision_and_role_checks_before_hooks(tmp_path, typed):
    hooks = BatchedHooks()
    runtime = start(tmp_path, typed, hooks=hooks)
    try:
        result = runtime.views("session", TYPE, "item", audiences())
        assert len(result) == 65 and len({r["revision"] for r in result}) == 1
        assert [len(b) for b in hooks.batches] == [32, 32, 1]
        hooks.batches.clear()
        bad = audiences(2); bad[1]["surface"] = "presenter-controls"
        with pytest.raises(PluginError, match="surface not allowed"):
            runtime.views("session", TYPE, "item", bad)
        assert not hooks.batches
    finally:
        runtime.close()


@pytest.mark.parametrize("fault,match", [("schema", "surface view"), ("size", "output budget")])
def test_every_batched_view_is_validated(tmp_path, typed, fault, match):
    hooks = BatchedHooks(); hooks.bad = fault
    runtime = start(tmp_path, typed, hooks=hooks)
    try:
        with pytest.raises(PluginError, match=match):
            runtime.views("session", TYPE, "item", audiences(2))
    finally:
        runtime.close()


@pytest.mark.parametrize("fault", ["broken", "large"])
def test_worker_batch_isolates_state_audience_context_and_keeps_stream_aligned(monkeypatch, fault):
    class MutatingView:
        def view(self, state, audience, ctx):
            if audience["actor"] == "broken": raise ValueError("private answer")
            if audience["actor"] == "large": return {"large": "x" * (128 * 1024)}
            result = {"before": copy.deepcopy(state), "actor": ctx["actor"], "role": ctx["role"],
                      "private": ctx["item"]["private"]["number"],
                      "record": copy.deepcopy(ctx["records"])}
            assert "_audience_contexts" not in ctx
            ctx["records"]["secret"].append("must not reach another call")
            state["answers"].append("contamination")
            audience["actor"] = "someone else"
            ctx["item"]["private"]["number"] = "changed"
            return result
    module = ModuleType("batch_fixture")
    module.factory = lambda: PluginV1(state_hooks={"tree": MutatingView()})
    monkeypatch.setitem(sys.modules, "batch_fixture", module)
    provider = SimpleNamespace(id="fixture", version="1", payload="hash", entry_point="batch_fixture:factory",
        manifest={"capabilities": {"content_types": {"kind": {"state_hook": "tree"}}}})
    monkeypatch.setattr(worker, "discover", lambda: [provider])
    monkeypatch.setattr(sys, "argv", ["worker", "fixture", "1", "hash"])
    state, ctx = {"answers": []}, {"item": {"private": {"number": 7}}, "actor": None, "role": "system"}
    def batch(people):
        own = ctx | {"_audience_contexts": [{"records": {"secret": [p["actor"]]}} for p in people]}
        return {"capability": "kind", "method": "view_batch", "args": [state, people, own]}
    bad = audiences(2); bad[1]["actor"] = fault
    requests = [batch(audiences(2)), batch(bad), batch(audiences(1))]
    source, target = io.BytesIO(b"".join(canonical(r) + b"\n" for r in requests)), io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=source))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=target))
    worker.main()
    messages = [json.loads(line) for line in target.getvalue().splitlines()]
    assert messages[0] == {"ready": "hash"}
    assert messages[1]["result"]["actor"] == "0" and messages[2]["result"]["actor"] == "1"
    assert "error" in messages[4] and "private answer" not in str(messages[4])
    assert messages[5]["view"] == 0  # A failed batch leaves no unread trailing frames.
    for message in messages[1:]:
        if "result" in message:
            assert message["result"]["before"] == {"answers": []}
            assert message["result"]["private"] == 7
            assert message["result"]["record"] == {"secret": [message["result"]["actor"]]}


def test_each_streamed_view_has_ordinary_timeout_and_failure_kills_worker():
    instance = worker.Worker(SimpleNamespace(id="fixture"))
    instance.process = SimpleNamespace(stdin=io.BytesIO())
    responses = Mock()
    responses.get.side_effect = [{"view": 0, "result": {}}, queue.Empty()]
    instance.responses = responses
    instance.close = Mock()
    with pytest.raises(PluginError, match="timed out"):
        instance.views("kind", {}, audiences(2), {})
    assert responses.get.call_args_list == [call(timeout=.25), call(timeout=.25)]
    instance.close.assert_called_once()


def test_authenticated_batch_cannot_reuse_another_actor_or_session():
    class Connection:
        def __init__(self, role, actor, session="s"):
            self.role, self.player, self.session = role, actor, session
    a, b, teacher = Connection("player", "alice"), Connection("player", "bob"), Connection("stage", None)
    host = object.__new__(PluginHost)
    spec = {"views": {s: "view.mjs" for s in ("participant-input", "presenter-controls", "presenter-overlay")}}
    host.catalog = SimpleNamespace(fingerprint="cat", capability=lambda kind: (SimpleNamespace(payload="p", resources={}), spec))
    host.identity = lambda c: ("participant", c.player) if c.role == "player" else ("presenter", "owner")
    host.sync = Mock(return_value=(None, SimpleNamespace(deck_json={"language": "de"}, items={"kind": {"i": {}}}), [("kind", "i")]))
    host.runtime = SimpleNamespace(views=lambda sid, kind, item, aa: [{"data": dict(a)} for a in aa])
    views = host.safe_views([a, b, teacher])
    host.sync.assert_called_once_with("s")
    for c in (a, b):
        descriptor = views[c]["plugins"]["items"][0]
        assert list(descriptor["views"]) == ["participant-input"]
        assert descriptor["views"]["participant-input"]["data"]["actor"] == c.player
        assert views[c]["language"] == "de"
    assert set(views[teacher]["plugins"]["items"][0]["views"]) == {"presenter-controls", "presenter-overlay"}
    b.session = "another"
    views = host.safe_views([a, b])
    assert all(v["plugins"]["items"] == [] for v in views.values())


def test_noop_completion_is_durable_without_changing_revision_and_retains_cas(tmp_path, typed):
    class NoopHooks(BatchedHooks):
        def call(self, kind, method, *args):
            if method == "transition" and args[1]["kind"] == "evaluation.finished":
                return {"state": args[0], "effects": []}
            return super().call(kind, method, *args)
    runtime = start(tmp_path, typed, hooks=NoopHooks())
    try:
        runtime.command("session", "alice", "participant", command())
        job = runtime.lease("session", "owner", now=10)[0]
        result = {k: job[k] for k in ("id", "epoch", "generation")} | {"outcome": {"status": "error"}}
        assert runtime.finish("session", "owner", result, now=11)
        before = runtime._item("session", TYPE, "item")
        runtime.drain("session")
        assert dict(runtime._item("session", TYPE, "item")) == dict(before)
        assert runtime.db.execute("SELECT delivered FROM jobs WHERE id=?", (job["id"],)).fetchone()[0] == 1
        runtime.drain("session")  # Durable delivery is not replayed.
        runtime.db.execute("UPDATE items SET revision=revision+1")
        with pytest.raises(PluginError, match="changed concurrently"):
            runtime._commit(before, {"state": json.loads(before["state"]), "effects": []}, delivery=job["id"])
    finally:
        runtime.close()


def test_batch_schema_errors_cannot_poison_another_batch_or_hide_invalid_values():
    schema = {"type": "object", "properties": {"value": {"enum": [1]}}, "additionalProperties": False}
    original = copy.deepcopy(schema)
    with pytest.raises(PluginError) as caught:
        validate_json_many(schema, [{"value": 1}, {"value": 2}])
    caught.value.__cause__.schema["enum"].append(2)
    assert schema == original
    with pytest.raises(PluginError):
        validate_json_many(schema, [{"value": 1}, {"value": 2}])
    schema["properties"]["value"]["enum"] = [2]
    validate_json_many(schema, [{"value": 2}] * 32)
    with pytest.raises(PluginError):
        validate_json_many(schema, [{"value": 2}] * 31 + [{"value": 1}])
    schema["$ref"] = "https://invalid.example/schema"
    with pytest.raises(PluginError, match="local fragment"):
        validate_json_many(schema, [])


@pytest.mark.parametrize("count,expected", [(3, 2), (31, 2), (32, 4), (127, 4), (128, 8), (1000, 8)])
def test_classroom_leases_adapt_with_an_eight_job_ceiling(tmp_path, typed, count, expected):
    runtime = start(tmp_path, typed, hooks=BatchedHooks())
    try:
        for n in range(count):
            runtime.command("session", str(n), "participant", command(f"request-{n:05}"))
        jobs = runtime.lease("session", "presenter", now=10, adaptive=True)
        assert len(jobs) == expected
        assert len({j["id"] for j in jobs}) == expected
        assert all(j["generation"] == 1 for j in jobs)
        assert runtime.release("session", "presenter") == expected
        # The explicit ordinary lease API and retry generations remain intact.
        retry = runtime.lease("session", "another", now=11)
        assert len(retry) == 2 and all(j["generation"] == 2 for j in retry)
    finally:
        runtime.close()


def test_lease_batch_failure_rolls_back_before_any_job_is_exposed(tmp_path, typed, monkeypatch):
    runtime = start(tmp_path, typed, hooks=BatchedHooks())
    try:
        for n in range(4):
            runtime.command("session", str(n), "participant", command(f"request-{n:05}"))
        original = runtime._item
        calls = 0
        def fail_after_first_lease(*args):
            nonlocal calls
            calls += 1
            if calls == 2: raise PluginError("simulated lease failure")
            return original(*args)
        monkeypatch.setattr(runtime, "_item", fail_after_first_lease)
        with pytest.raises(PluginError, match="simulated"):
            runtime.lease("session", "presenter", now=10)
        assert not runtime.db.in_transaction
        assert all(tuple(r) == ("queued", 0) for r in runtime.db.execute("SELECT status,generation FROM jobs"))
        monkeypatch.setattr(runtime, "_item", original)
        assert len(runtime.lease("session", "presenter", now=11)) == 2
    finally:
        runtime.close()
