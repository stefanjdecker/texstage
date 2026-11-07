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
