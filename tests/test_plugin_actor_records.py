# SPDX-License-Identifier: Apache-2.0
"""Partitioned storage must preserve authorization, atomicity and bounded reads."""
import copy
import json
import pytest
from texstage.plugins import PluginError
from texstage.plugins.catalog import Catalog, discover
from texstage.plugins.manifest import canonical
from texstage.plugins.runtime import Runtime
from test_plugins import distribution

TYPE = "org.example.fixture.plane"
VALUE = {"type": "object", "additionalProperties": False, "required": ["answer"],
         "properties": {"answer": {"type": "integer", "minimum": 0, "maximum": 10000}}}
SUMMARY = {"type": "object", "additionalProperties": False, "required": ["saved"],
           "properties": {"saved": {"type": "boolean"}}}
EMPTY = {"type": "object", "additionalProperties": False, "properties": {}}


def catalog(tmp_path, capacity=1000, modify=None):
    def change(m):
        m["manifest_version"] = 3
        spec = m["capabilities"]["content_types"][TYPE]
        spec["view_schemas"] = {s: "fixture_plugin/view.json" for s in spec["views"]}
        spec["actor_records"] = {"capacity": capacity, "page_size": 25, "page_field": "page",
                                "value_schema": "fixture_plugin/value.json",
                                "summary_schema": "fixture_plugin/summary.json"}
        spec["messages"]["inspect"] = {"from": ["presenter"], "revision_policy": "latest",
                                      "schema": "fixture_plugin/inspect.json", "record_actor_field": "actor"}
        if modify:
            modify(m)
    dist = distribution(tmp_path, modify=change, extra_resources={
        "fixture_plugin/value.json": canonical(VALUE), "fixture_plugin/summary.json": canonical(SUMMARY),
        "fixture_plugin/view.json": canonical(EMPTY),
        "fixture_plugin/inspect.json": canonical({"type":"object","additionalProperties":False,
            "required":["actor"],"properties":{"actor":{"type":"string","maxLength":256}}})})
    return Catalog(discover(distributions=[dist]))


class Hooks:
    def __init__(self):
        self.contexts = []
        self.effects = None
        self.before_return = None
    def close(self):
        pass
    def call(self, kind, method, *args):
        if method == "initial_state":
            self.contexts.append(copy.deepcopy(args[-1]))
            return {"page": 0}
        if method == "view":
            self.contexts.append(copy.deepcopy(args[-1]))
            return {}
        state, event, ctx = args
        self.contexts.append(copy.deepcopy(ctx))
        effects = []
        if event["kind"] == "command":
            effects = self.effects if self.effects is not None else (
                [{"kind":"save-actor","value":{"answer":event["payload"]["value"]},"summary":{"saved":True}}]
                if event["operation"] == "submit" else [])
        if self.before_return:
            callback, self.before_return = self.before_return, None
            callback()
        return {"state": copy.deepcopy(state), "effects": copy.deepcopy(effects)}


def command(i, operation="submit", value=1, epoch=1):
    return {"type":TYPE,"item":"exercise","operation":operation,"epoch":epoch,
            "expected_revision":0,"request_id":f"request{i:09d}",
            "payload":{"actor":value} if operation=="inspect" else {} if operation=="_reset" else {"value":value}}


@pytest.fixture
def live(tmp_path):
    cat = catalog(tmp_path/"installed")
    hooks = Hooks()
    runtime = Runtime(tmp_path/"db.sqlite", cat, workers=hooks)
    runtime.ensure("session",TYPE,"exercise",{"evaluations":{"value":{"engine":"org.example.fixture.engine","seed":""}}})
    runtime.activate("session",{(TYPE,"exercise")})
    yield runtime, hooks, cat
    runtime.close()


def test_600_records_are_separate_and_each_context_is_bounded(live):
    r,h,_=live
    for i in range(600):
        assert r.command("session",f"student{i}","participant",command(i,value=i))["accepted"]
        ctx=h.contexts[-1]
        assert ctx["records"]["count"]==i and ctx["records"]["value"] is None
        assert "record_page" not in ctx and len(canonical(ctx))<2048
    row=r._item("session",TYPE,"exercise")
    assert json.loads(row["state"])=={"page":0}
    assert r.records.count(row)==600
    r.view("session",TYPE,"exercise","participant","participant-input","student599")
    assert h.contexts[-1]["records"]["value"]=={"answer":599}
    assert "student598" not in canonical(h.contexts[-1]).decode()
    r.view("session",TYPE,"exercise","presenter","presenter-controls","teacher")
    page=h.contexts[-1]["record_page"]
    assert page["pages"]==24 and len(page["rows"])==25
    assert [p["number"] for p in page["rows"]]==list(range(1,26))
    assert all(set(p)=={"actor","number","summary"} for p in page["rows"])
    assert h.contexts[-1]["records"]["value"] is None
    r.command("session","teacher","presenter",command(700,"inspect","student599"))
    assert h.contexts[-1]["records"]["value"]=={"answer":599}
    r.ensure("other",TYPE,"exercise",{})
    r.view("other",TYPE,"exercise","participant","participant-input","student599")
    assert h.contexts[-1]["records"]["value"] is None


def test_initial_and_reset_contexts_are_empty_in_the_new_epoch(live):
    r,h,_=live
    assert h.contexts[0]["records"] == {"actor":None,"count":0,"number":1,"value":None}
    r.command("session","alice","participant",command(1))
    before=len(h.contexts)
    r.command("session","teacher","presenter",command(2,"_reset"))
    for ctx in h.contexts[before:]:
        assert ctx["epoch"] == 2
        assert ctx["records"] == {"actor":None,"count":0,"number":1,"value":None}
        assert ctx["record_page"] == {"page":0,"pages":1,"total":0,"rows":[]}


def test_actor_write_cannot_select_another_identity_and_presenter_cannot_write(live):
    r,h,_=live
    h.effects=[{"kind":"save-actor","actor":"bob","value":{"answer":1},"summary":{"saved":True}}]
    with pytest.raises(PluginError,match="invalid actor record"):
        r.command("session","alice","participant",command(1))
    h.effects=[{"kind":"save-actor","value":{"answer":1},"summary":{"saved":True}}]
    with pytest.raises(PluginError,match="not authorized"):
        r.command("session","teacher","presenter",command(2,"inspect","bob"))
    assert r.db.execute("SELECT count(*) FROM actor_records").fetchone()[0]==0
    with pytest.raises(PluginError,match="role"):
        r.command("session","alice","participant",command(3,"inspect","bob"))


@pytest.mark.parametrize("effects", [
    [{"kind":"save-actor","value":{"answer":"secret"},"summary":{"saved":True}}],
    [{"kind":"save-actor","value":{"answer":1},"summary":{"saved":True,"private":7}}],
    [{"kind":"save-actor","value":{"answer":1,"large":"x"*5000},"summary":{"saved":True}}],
    [{"kind":"save-actor","value":{"answer":1},"summary":{"saved":True}}]*2,
])
def test_bad_records_leave_no_partial_state_receipt_or_job(live,effects):
    r,h,_=live
    before=dict(r._item("session",TYPE,"exercise"))
    h.effects=effects
    with pytest.raises(PluginError):
        r.command("session","alice","participant",command(1))
    assert dict(r._item("session",TYPE,"exercise"))==before
    assert r.db.execute("SELECT count(*) FROM actor_records").fetchone()[0]==0
    assert r.db.execute("SELECT count(*) FROM receipts").fetchone()[0]==0


def test_queue_failure_and_storage_failure_roll_back_everything(live,monkeypatch):
    r,h,_=live
    save={"kind":"save-actor","value":{"answer":1},"summary":{"saved":True}}
    h.effects=[save,{"kind":"evaluate","binding":"value","correlation_id":"evaluation0001","text":"x"}]
    monkeypatch.setattr("texstage.plugins.runtime.MAX_PENDING",0)
    with pytest.raises(PluginError,match="queue"):
        r.command("session","alice","participant",command(1))
    assert r.db.execute("SELECT count(*) FROM actor_records").fetchone()[0]==0
    monkeypatch.setattr("texstage.plugins.runtime.MAX_PENDING",1000)
    apply=r.records.apply
    def fail_after_insert(*args,**kwargs):
        apply(*args,**kwargs)
        raise RuntimeError("simulated write failure")
    monkeypatch.setattr(r.records,"apply",fail_after_insert)
    with pytest.raises(RuntimeError):
        r.command("session","alice","participant",command(1))
    assert r.db.execute("SELECT count(*) FROM actor_records").fetchone()[0]==0
    assert r.db.execute("SELECT count(*) FROM jobs").fetchone()[0]==0
    monkeypatch.setattr(r.records,"apply",apply)
    accepted=r.command("session","alice","participant",command(1))
    assert r.command("session","alice","participant",command(1))==accepted
    assert r.records.count(r._item("session",TYPE,"exercise"))==1


def test_capacity_replacement_reset_and_restart(tmp_path):
    cat=catalog(tmp_path/"installed",capacity=2)
    path=tmp_path/"db.sqlite"; h=Hooks();r=Runtime(path,cat,workers=h)
    try:
        r.ensure("s",TYPE,"exercise",{});r.activate("s",{(TYPE,"exercise")})
        for i,name in enumerate(("alice","bob")):r.command("s",name,"participant",command(i))
        with pytest.raises(PluginError,match="capacity"):
            r.command("s","carol","participant",command(3))
        r.command("s","alice","participant",command(4,value=9))
        r.close();r=Runtime(path,cat,workers=h)
        r.view("s",TYPE,"exercise","participant","participant-input","alice")
        assert h.contexts[-1]["records"]["value"]=={"answer":9} and h.contexts[-1]["records"]["number"]==1
        assert len(r.archive("s")["actor_records"])==2
        reset=r.command("s","teacher","presenter",command(5,"_reset"))
        assert reset["epoch"]==2 and not r.archive("s")["actor_records"]
        assert r.command("s","teacher","presenter",command(5,"_reset"))==reset
        assert r.command("s","alice","participant",command(6))["error"]=="stale-epoch"
    finally:r.close()


def test_concurrent_revision_change_prevents_stale_record_commit(live,tmp_path):
    r,h,cat=live
    other=Runtime(r.db.execute("PRAGMA database_list").fetchone()[2],cat,workers=Hooks())
    try:
        h.before_return=lambda:other.command("session","alice","participant",command(2,value=2))
        with pytest.raises(PluginError,match="concurrently"):
            r.command("session","alice","participant",command(1,value=1))
        r.view("session",TYPE,"exercise","participant","participant-input","alice")
        assert h.contexts[-1]["records"]["value"]=={"answer":2}
        assert r.db.execute("SELECT count(*) FROM receipts").fetchone()[0]==1
    finally:other.close()


def test_old_manifests_cannot_enable_records_and_participants_cannot_request_reads(tmp_path):
    for i,modify in enumerate((
        lambda m:m.update(manifest_version=2),
        lambda m:m["capabilities"]["content_types"][TYPE]["messages"]["inspect"].update(**{"from":["participant"]}),
    )):
        with pytest.raises(PluginError):
            catalog(tmp_path/str(i),modify=modify)


@pytest.mark.parametrize('revision', [3, 4])
@pytest.mark.parametrize('policy', ['actor', 'all', True, None])
def test_actor_update_policy_remains_available_with_records_and_points(tmp_path, revision, policy):
    def modify(manifest):
        manifest['manifest_version'] = revision
        manifest['capabilities']['content_types'][TYPE]['participant_updates'] = policy
    if policy == 'actor':
        result = catalog(tmp_path, modify=modify)
        assert result.capability(TYPE)[1]['participant_updates'] == 'actor'
    else:
        with pytest.raises(PluginError):
            catalog(tmp_path, modify=modify)
