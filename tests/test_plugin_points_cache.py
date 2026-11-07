# SPDX-License-Identifier: Apache-2.0
"""Prepared point limits may be reused, but changed content must be validated."""
import json
import pytest
from test_plugin_points import live, TYPE
from texstage.plugins import PluginError


def test_limit_cache_revalidates_changed_specs_and_never_caches_actor_credit(live):
    w, runtime, _, _, actor, _ = live
    row = dict(runtime._item(w.session.id, TYPE, 'activity'))
    assert runtime.points.settings(row)[0] == 1000
    for maximum in range(20):
        other = {**row, 'spec': json.dumps({'public': {'points': maximum}})}
        assert runtime.points.settings(other)[0] == maximum
    assert runtime.points.settings(row)[0] == 1000
    with pytest.raises(PluginError):
        runtime.points.settings({**row, 'spec': '{"public":{"points":true}}'})
    with pytest.raises(PluginError):
        runtime.points.settings({**row, 'spec': '{"public":{"points":1000,"points":1}}'})
    # Only the immutable maximum is cached; publication and credits remain live.
    from test_plugin_points import send
    send(w, runtime, actor.id, 'submit', 500)
    assert runtime.points.context(row, actor.id)['scoring']['awarded'] is None
    send(w, runtime, 'teacher', 'publish')
    assert runtime.points.context(row, actor.id)['scoring']['awarded'] == 500
    send(w, runtime, actor.id, 'submit', 1000, request='changedcredit')
    assert runtime.points.context(row, actor.id)['scoring']['awarded'] == 1000


def test_private_new_round_does_not_reproject_the_whole_class(live):
    from unittest.mock import patch
    from test_plugin_points import send
    w, runtime, _, bridge, actor, _ = live
    send(w, runtime, actor.id, 'submit')
    send(w, runtime, 'teacher', 'publish')
    bridge.sync_points(w.session.id)
    send(w, runtime, 'teacher', '_reset', request='resetnewround')
    bridge.sync_points(w.session.id)
    assert actor.score == 0
    bridge.server.plugins_changed.reset_mock()
    with patch.object(w.engine, '_rank', wraps=w.engine._rank) as rank:
        for i in range(10):
            send(w, runtime, actor.id, 'submit', request=f'newanswer{i:08}', epoch=2)
            bridge.sync_points(w.session.id)
        assert actor.score == 0 and rank.call_count == 0
        bridge.server.plugins_changed.assert_not_called()
        assert w.session.activity_points[TYPE, 'activity'].revision == runtime.points.heads(w.session.id)[0]['revision']
        send(w, runtime, 'teacher', 'publish', request='newpublication', epoch=2)
        bridge.sync_points(w.session.id)
        assert actor.score == 1000 and rank.call_count == 1
        bridge.server.plugins_changed.assert_called_once_with(w.session.id)


def test_batched_scores_use_one_snapshot_and_remain_actor_private(live):
    import copy
    from texstage.plugins.runtime import Runtime
    from test_plugin_points import send, Hooks
    w, runtime, hooks, _, alice, bob = live
    send(w, runtime, alice.id, "submit", 1000)
    send(w, runtime, bob.id, "submit", 900)
    send(w, runtime, "teacher", "publish")
    other = Runtime(runtime.db.execute("PRAGMA database_list").fetchone()[2], runtime.catalog, workers=Hooks())
    seen = []
    def views(kind, state, audience, ctx):
        if not seen:
            send(w, other, bob.id, "submit", 100, request="concurrentgrade")
        seen.extend(copy.deepcopy(ctx["_audience_contexts"]))
        return [{} for _ in audience]
    hooks.views = views
    audience = [{"role": "participant", "surface": "participant-input", "actor": bob.id} for _ in range(33)]
    audience += [{"role": "participant", "surface": "participant-input", "actor": alice.id},
                 {"role": "presenter", "surface": "presenter-controls", "actor": "teacher"},
                 {"role": "projector", "surface": "projector-overlay", "actor": "display"}]
    try:
        runtime.views(w.session.id, TYPE, "activity", audience)
        assert [ctx["scoring"]["awarded"] for ctx in seen] == [900] * 33 + [1000, None, None]
        assert not runtime.db.in_transaction
        row = runtime._item(w.session.id, TYPE, "activity")
        assert runtime.points.context(row, bob.id)["scoring"]["awarded"] == 100
    finally:
        other.close()


def test_full_credit_ledger_allows_replacement_and_reset_but_not_new_actor(live, monkeypatch):
    from test_plugin_points import send
    monkeypatch.setattr("texstage.plugins.points.MAX_ACTORS", 2)
    w, runtime, hooks, _, alice, bob = live
    send(w, runtime, alice.id, "submit", 1000)
    send(w, runtime, bob.id, "submit", 500)
    # The existing slot counts even when its grade is pending/null.
    hooks.effects = [{"kind": "set-credit", "credit": None}]
    send(w, runtime, alice.id, "submit", 0, request="pendingagain1")
    hooks.effects = None
    send(w, runtime, alice.id, "submit", 900, request="gradedagain1")
    before = dict(runtime._item(w.session.id, TYPE, "activity"))
    with pytest.raises(PluginError, match="credit capacity"):
        send(w, runtime, "third-student", "submit")
    assert dict(runtime._item(w.session.id, TYPE, "activity")) == before
    assert runtime.db.execute("SELECT count(*) FROM point_credits").fetchone()[0] == 2
    send(w, runtime, "teacher", "publish")
    row = runtime._item(w.session.id, TYPE, "activity")
    assert runtime.points.context(row, alice.id)["scoring"]["awarded"] == 900
    send(w, runtime, "teacher", "_reset", request="resetcapacity")
    send(w, runtime, "third-student", "submit", epoch=2)
    assert runtime.db.execute("SELECT count(*) FROM point_credits").fetchone()[0] == 1
