# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Host contracts and failure recovery, using synthetic distributions and hooks."""
import copy
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

import pytest

from texstage.plugins import PluginError
from texstage.plugins.assets import verified_file
from texstage.plugins.catalog import Catalog, discover
from texstage.plugins.manifest import canonical, load_manifest, read_json, validate_schema
from texstage.plugins.policy import catalog_for, enable
from texstage.plugins.runtime import Runtime


def distribution(root, *, pid="org.example.fixture", namespace="fixture", modify=None, extra_resources=None):
    """Installed distribution shape, with a factory that fails if accidentally imported."""
    root.mkdir(parents=True, exist_ok=True)
    resources = {
        "fixture_plugin/__init__.py": b"raise RuntimeError('factory must not be imported during discovery')\n",
        "fixture_plugin/web.mjs": b"export function mount() {}\n",
        f"fixture_plugin/texstage-{namespace}-plane.sty": b"% synthetic style\n",
        "fixture_plugin/message.json": canonical({"type": "object", "additionalProperties": False,
            "properties": {"value": {"type": "integer"}}, "required": ["value"]}),
    }
    resources.update(extra_resources or {})
    manifest = {"manifest_version": 1, "plugin_api": 1, "id": pid, "version": "0.1.0",
                "description": "Fixture", "license": "Apache-2.0", "latex_namespace": namespace,
                "latex_exports": {"commands": [], "environments": [namespace + "plane"]},
                "capabilities": {"content_types": {pid + ".plane": {
                    "content_api": 1, "build_hook": "plane", "state_hook": "plane", "state_schema": 1,
                    "latex_packages": [f"fixture_plugin/texstage-{namespace}-plane.sty"],
                    "views": {s: "fixture_plugin/web.mjs" for s in ("presenter-overlay", "presenter-controls", "projector-overlay", "participant-input")},
                    "messages": {"submit": {"from": ["participant"], "revision_policy": "latest", "schema": "fixture_plugin/message.json"},
                                 "reveal": {"from": ["presenter"], "revision_policy": "exact", "schema": "fixture_plugin/message.json"}},
                    "evaluations": {"value": {"engine": pid + ".engine"}}, "fallback": "static-slide"}},
                    "engines": {pid + ".engine": {"engine_api": 1, "module": "fixture_plugin/web.mjs",
                        "seed_types": {".txt": "text/plain"}, "input": {"mode": "code", "label": "value", "tokens": []},
                        "canonical_format": "fixture-v1", "summary_kinds": ["text"], "state_policy": "fresh-per-submission"}}},
                "resources": {n: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for n, b in resources.items()}}
    if modify: modify(manifest)
    for name, raw in resources.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    info = root / "fixture_plugin-0.1.0.dist-info"; info.mkdir()
    (info / "texstage-plugin.json").write_bytes(canonical(manifest))
    (info / "METADATA").write_text("Metadata-Version: 2.4\nName: fixture-plugin\nVersion: 0.1.0\n", encoding="utf-8")
    (info / "WHEEL").write_text("Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n", encoding="utf-8")
    (info / "entry_points.txt").write_text(f"[texstage.plugins.v1]\n{pid} = fixture_plugin:create_plugin\n", encoding="utf-8")
    (info / "RECORD").write_text("\n".join(n + ",," for n in [*resources, *[p.relative_to(root).as_posix() for p in info.iterdir()]]), encoding="utf-8")
    return metadata.Distribution.at(info)


@pytest.fixture
def provider(tmp_path):
    return discover(distributions=[distribution(tmp_path / "installed")])[0]


def test_metadata_discovery_never_imports_or_executes(provider):
    assert provider.id == "org.example.fixture"
    assert "fixture_plugin" not in sys.modules
    assert set(provider.manifest["capabilities"]) == {"engines", "content_types"}


def test_profile_requires_exact_pin_and_is_not_ambient(tmp_path, monkeypatch, provider):
    monkeypatch.setattr("texstage.plugins.policy.discover", lambda: (provider,))
    assert not catalog_for(tmp_path).providers
    with pytest.raises(PluginError, match="exact installed"):
        enable(tmp_path, provider.id, provider.version, "0" * 64)
    enable(tmp_path, provider.id, provider.version, provider.payload)
    assert catalog_for(tmp_path).providers[provider.id] == provider
    assert not catalog_for(None).providers
    assert "fixture_plugin" not in sys.modules
    (tmp_path / "plugins.json").write_text('{"format":1,"enabled":[{"id":"org.example.fixture","version":"0.2.0","payload":"bad"}]}')
    with pytest.raises(PluginError, match="changed or missing"): catalog_for(tmp_path)


def test_portable_identity_independent_of_install_path(tmp_path):
    a, b = [discover(distributions=[distribution(tmp_path / n)])[0] for n in ("windows", "linux")]
    assert a.payload == b.payload and a.root != b.root
    data = a.manifest; data["description"] = "edited"
    assert a.manifest["description"] == "Fixture"
    cat = Catalog([a])
    with pytest.raises(AttributeError): cat.fingerprint = "changed"
    with pytest.raises(TypeError): cat.providers[a.id] = b


def test_duplicate_ids_styles_namespaces_and_reserved_names(tmp_path, provider):
    dist = distribution(tmp_path / "duplicate")
    with pytest.raises(PluginError, match="duplicate installed"):
        discover(distributions=[dist, dist])
    second = discover(distributions=[distribution(tmp_path / "second", pid="org.example.second")])[0]
    with pytest.raises(PluginError, match="namespace"): Catalog([provider, second])
    with pytest.raises(PluginError, match="reserved"):
        discover(distributions=[distribution(tmp_path / "reserved", pid="org.texstage.test")])


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "a\\b", "a//b", "a/../b", "a%2fb"])
def test_resource_paths_rejected(provider, name):
    data = provider.manifest; data["resources"][name] = {"size": 0, "sha256": "0" * 64}
    with pytest.raises(PluginError): load_manifest(canonical(data))


def test_inventory_tampering_and_native_wheels(tmp_path):
    dist = distribution(tmp_path / "one")
    (tmp_path / "one/fixture_plugin/web.mjs").write_bytes(b"changed")
    with pytest.raises(PluginError, match="changed"): discover(distributions=[dist])
    dist = distribution(tmp_path / "two")
    (tmp_path / "two/fixture_plugin-0.1.0.dist-info/WHEEL").write_text("Root-Is-Purelib: false\nTag: cp314-cp314-win_amd64\n")
    with pytest.raises(PluginError, match="portable"): discover(distributions=[dist])


def test_schema_never_fetches_refs_and_rejects_duplicate_keys():
    with pytest.raises(PluginError, match="local fragment"): validate_schema({"$ref": "https://example.invalid/schema"})
    with pytest.raises(PluginError, match="duplicate JSON key"): read_json('{"x":1,"x":2}')
    with pytest.raises(PluginError): read_json('{"x":NaN}')


class Hooks:
    """Deterministic reducer with observable calls for fault injection."""
    def __init__(self): self.transitions = 0
    def close(self): pass
    def call(self, kind, method, *args):
        if method == "initial_state": return {"values": [], "active": False, "finished": []}
        if method == "view": return copy.deepcopy(args[0])
        state, event, ctx = copy.deepcopy(args)
        self.transitions += 1
        if event["kind"] in ("activate", "deactivate"):
            state["active"] = event["kind"] == "activate"
        elif event["kind"] == "evaluation.finished":
            state["finished"].append(event["job_id"])
        elif event["kind"] == "command":
            if event["payload"]["value"] < 0: return {"refusal": "negative-value"}
            state["values"].append(event["payload"]["value"])
            return {"state": state, "effects": [{"kind": "evaluate", "binding": "value",
                     "text": str(event["payload"]["value"]), "correlation_id": event["request_id"]}]}
        return {"state": state, "effects": []}


def start(tmp_path, provider, *, fingerprint="test-runtime", hooks=None):
    runtime = Runtime(tmp_path / "state.sqlite3", Catalog([provider]), workers=hooks or Hooks(), fingerprint=fingerprint)
    runtime.ensure("session", provider.id + ".plane", "item", {"public": {}, "private": {}, "evaluations": {
        "value": {"engine": provider.id + ".engine", "seed": "", "references": []}}})
    runtime.activate("session", {(provider.id + ".plane", "item")})
    return runtime


def command(request="request0001", **changes):
    return {"type": "org.example.fixture.plane", "item": "item", "operation": "submit", "epoch": 1,
            "expected_revision": 1, "request_id": request, "payload": {"value": 3}} | changes


def test_lost_ack_restart_job_delivery_and_reset(tmp_path, provider):
    r = start(tmp_path, provider)
    envelope = command()
    receipt = r.command("session", "alice", "participant", envelope)
    assert receipt["accepted"] and len(receipt["jobs"]) == 1
    r.close()
    r = start(tmp_path, provider)
    try:
        assert r.command("session", "alice", "participant", envelope) == receipt
        assert r.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        job = r.lease("session", "presenter", now=100)[0]
        result = {"id": job["id"], "epoch": job["epoch"], "generation": job["generation"], "outcome": {"status": "error"}}
        assert r.finish("session", "presenter", result, now=101)
        r.close()
        r = start(tmp_path, provider)
        r.drain("session"); r.drain("session")
        row = r._item("session", provider.id + ".plane", "item")
        assert read_json(row["state"])["finished"] == [job["id"]]
        reset = command("reset000001", operation="_reset", expected_revision=row["revision"], payload={})
        first = r.command("session", "teacher", "presenter", reset)
        assert first["epoch"] == 2
        assert r.command("session", "teacher", "presenter", reset) == first
        assert not r.finish("session", "presenter", result, now=102)
        assert read_json(r._item("session", provider.id + ".plane", "item")["state"])["active"]
    finally: r.close()


def test_auth_schema_epoch_and_request_identity(tmp_path, provider):
    r = start(tmp_path, provider)
    try:
        for role in ("projector", "system"):
            with pytest.raises(PluginError): r.command("session", "alice", role, command())
        with pytest.raises(PluginError): r.command("session", "alice", "participant", command(operation="reveal"))
        with pytest.raises(PluginError): r.command("session", "alice", "participant", command(payload={"value": "bad"}))
        receipt = r.command("session", "alice", "participant", command())
        with pytest.raises(PluginError, match="changed envelope"):
            r.command("session", "alice", "participant", command(payload={"value": 4}))
        assert r.command("session", "alice", "participant", command("stale00001", epoch=0))["error"] == "stale-epoch"
        # A new participant submission accepts the latest state even with an older revision.
        assert r.command("session", "alice", "participant", command("latest0001"))["accepted"]
        assert not r.command("session", "teacher", "presenter", command("exact00001", operation="reveal"))["accepted"]
        refused = command("refused001", payload={"value": -1})
        before = r.workers.transitions
        assert r.command("session", "alice", "participant", refused)["error"] == "negative-value"
        assert r.command("session", "alice", "participant", refused)["error"] == "negative-value"
        assert r.workers.transitions == before + 1
    finally: r.close()


def test_lease_replacement_and_rollback(tmp_path, provider):
    r = start(tmp_path, provider)
    r.command("session", "alice", "participant", command())
    first = r.lease("session", "old", now=10)[0]
    assert not r.lease("session", "new", now=11)
    second = r.lease("session", "new", now=131)[0]
    assert second["generation"] > first["generation"]
    outcome = {"status": "error"}
    assert not r.finish("session", "old", {k: first[k] for k in ("id", "epoch", "generation")} | {"outcome": outcome}, now=132)
    assert r.finish("session", "new", {k: second[k] for k in ("id", "epoch", "generation")} | {"outcome": outcome}, now=132)
    r.close()
    with pytest.raises(PluginError, match="runtime changed"):
        start(tmp_path, provider, fingerprint="upgraded-runtime")
    r = start(tmp_path, provider); r.drain("session"); r.close()


def test_crash_before_commit_rolls_back_state_receipt_and_jobs(tmp_path, provider, monkeypatch):
    r = start(tmp_path, provider)
    original = r._save_receipt
    monkeypatch.setattr(r, "_save_receipt", lambda *a: (_ for _ in ()).throw(RuntimeError("injected crash before commit")))
    with pytest.raises(RuntimeError): r.command("session", "alice", "participant", command())
    assert r.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    assert r.db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 0
    monkeypatch.setattr(r, "_save_receipt", original)
    assert r.command("session", "alice", "participant", command())["accepted"]
    r.close()


@pytest.mark.parametrize("value", [
    {"seed": 1}, {"references": ["x"] * 33}, {"options": []},
    {"engine": "org.example.other"}, {"options": {"x": float("nan")}},
])
def test_uploaded_evaluation_bindings_are_bounded(value):
    from texstage.plugins.manifest import validate_bindings
    declared = {"value": {"engine": "org.example.fixture.engine"}}
    with pytest.raises(PluginError):
        validate_bindings({"value": {"engine": declared["value"]["engine"]} | value},
                          declared, prepared=True)


def test_collection_is_offline_append_only_and_withdrawals_are_final(tmp_path, monkeypatch):
    from texstage.plugins import collection
    release = {"id": "org.example.fixture", "version": "0.1.0", "distribution": "fixture-plugin",
               "plugin_api": 1, "payload": "a" * 64, "sha256": "b" * 64, "license": "Apache-2.0",
               "url": "https://example.org/fixture_plugin-0.1.0-py3-none-any.whl", "withdrawn": False}
    index = {"format": 1, "releases": [release]}
    source = tmp_path / "index.json"
    profile = tmp_path / "profile"
    monkeypatch.setattr(collection, "download", lambda *a, **kw: pytest.fail("unexpected network access"))
    def update(value):
        source.write_bytes(canonical(value))
        return collection.update(profile, file=source)
    assert update(index) == index
    assert collection.cached(profile) == index
    with pytest.raises(PluginError, match="preserve"):
        update({"format": 1, "releases": []})
    with pytest.raises(PluginError, match="preserve"):
        update({"format": 1, "releases": [release | {"payload": "c" * 64}]})
    update({"format": 1, "releases": [release | {"withdrawn": True}]})
    with pytest.raises(PluginError, match="withdrawals"):
        update(index)
    with pytest.raises(PluginError, match="withdrawn"):
        collection.install(profile, "org.example.fixture==0.1.0",
                           requirements=tmp_path / "requirements.txt", offline=True)
    assert not (tmp_path / "requirements.txt").exists()


def test_collection_refuses_corrupted_cached_wheel_without_running_pip(tmp_path, monkeypatch):
    from texstage.plugins import collection
    release = {"id": "org.example.fixture", "version": "0.1.0", "distribution": "fixture-plugin",
               "plugin_api": 1, "payload": "a" * 64, "sha256": "b" * 64, "license": "Apache-2.0",
               "url": "https://example.org/fixture_plugin-0.1.0-py3-none-any.whl", "withdrawn": False}
    source = tmp_path / "index.json"
    source.write_bytes(canonical({"format": 1, "releases": [release]}))
    collection.update(tmp_path, file=source)
    def missing(name):
        raise metadata.PackageNotFoundError(name)
    monkeypatch.setattr(collection.metadata, "version", missing)
    monkeypatch.setattr(collection.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected pip invocation"))
    requirements = tmp_path / "requirements.txt"
    with pytest.raises(PluginError, match="not cached"):
        collection.install(tmp_path, "org.example.fixture==0.1.0", requirements=requirements, offline=True)
    cache = tmp_path / "plugin-wheels" / release["sha256"] / "fixture_plugin-0.1.0-py3-none-any.whl"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"not the reviewed wheel")
    with pytest.raises(PluginError, match="hash mismatch"):
        collection.install(tmp_path, "org.example.fixture==0.1.0", requirements=requirements, offline=True)
    assert not requirements.exists()


def test_bundle_cannot_expose_private_or_executable_files_as_plugin_assets(tmp_path, provider):
    from texstage.build.bundle import bundle_id
    from texstage.server.bundles import Bundle, BundleError, load_bundle
    catalog = Catalog([provider])
    kind, engine = provider.id + ".plane", provider.id + ".engine"
    for asset in ("keys.json", "../keys.json", "stage/" + "a" * 16 + ".pdf",
                  "plugin-data/" + "a" * 64 + ".js"):
        public = {kind: {"point": {"plugin_assets": {"data": asset}}}}
        deck = {"format": 3, "deck": "synthetic", "slides": [], "items": public,
                "plugins": catalog.requirements([kind], [engine])}
        keys = {"format": 3, "items": {kind: {"point": {"private": {}, "assets": {},
                "evaluations": {"value": {"engine": engine}}}}}}
        bid = bundle_id(deck, keys)
        (tmp_path / "deck.json").write_bytes(canonical(deck | {"bundle": bid}))
        (tmp_path / "keys.json").write_bytes(canonical(keys | {"bundle": bid}))
        with pytest.raises(BundleError, match="approved content-addressed"):
            load_bundle(tmp_path, catalog=catalog)
        unchecked = Bundle(bid, "synthetic", "Synthetic", tmp_path, {}, {}, deck, keys, items=public)
        assert unchecked.file(asset) is None
