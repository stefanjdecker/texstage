# SPDX-License-Identifier: Apache-2.0
"""Classroom bursts defer projections, never durable mutations or receipts."""
import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from texstage.server.app import Server
from texstage.server.plugins import PluginHost


def server():
    s = object.__new__(Server)
    s.plugin_dirty, s.dirty, s.qa_dirty = set(), set(), set()
    s.plugin_push_after = {}
    s.plugin_recipients = {}
    s.qa_pushed = 0
    s.engine = SimpleNamespace(sessions={"lesson": object()}, due={},
        host_view=lambda sid, now: {"session": {"pin": "1234"}},
        player_view=lambda actor, now, questions: {"actor": actor})
    s.config = SimpleNamespace(public_url="https://example.test")
    s.conns = defaultdict(set)
    s.plugins = SimpleNamespace(safe_view=lambda conn: {"private_actor": conn.player})
    return s


def peer(s, role, actor):
    class Connection:
        pass
    c = Connection()
    c.role, c.player, c.qa = role, actor, False
    c.session = "lesson"
    c.session = "lesson"
    c.push = Mock()
    s.conns["lesson"].add(c)
    return c


def flush_once(s, monkeypatch):
    calls = 0
    async def sleep(_):
        nonlocal calls
        if _ == 0:
            return
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError()
    monkeypatch.setattr("texstage.server.app.asyncio.sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(s.flusher())


def test_burst_uses_latest_state_and_separate_actor_projections(monkeypatch):
    s = server()
    peers = [peer(s, "player", str(i)) for i in range(64)]
    host = peer(s, "stage", None)
    for _ in range(128):
        s.plugins_changed("lesson")
    assert all(not c.push.called for c in peers)
    # Membership/roles are read when sending, not captured by the dirty marker.
    removed = peers.pop()
    s.conns["lesson"].remove(removed)
    s.dirty.add("lesson")
    flush_once(s, monkeypatch)
    for c in peers:
        c.push.assert_called_once()
        assert c.push.call_args.args[0]["private_actor"] == c.player
    host.push.assert_called_once()
    removed.push.assert_not_called()
    assert not s.plugin_dirty and not s.dirty


def test_partial_push_retains_pending_broadcast_full_push_clears_it(monkeypatch):
    s = server()
    player, host = peer(s, "player", "one"), peer(s, "stage", None)
    s.plugins_changed("lesson")
    s.push("lesson", players=False)
    assert s.plugin_dirty == {"lesson"}
    s.push("lesson", hosts=False, only="one")
    assert s.plugin_dirty == {"lesson"}
    s.push("lesson")
    assert not s.plugin_dirty
    player.push.reset_mock(); host.push.reset_mock()
    flush_once(s, monkeypatch)
    player.push.assert_not_called(); host.push.assert_not_called()


def test_ended_session_is_swept_without_stale_projection(monkeypatch):
    s = server()
    s.plugins_changed("lesson")
    s.engine.sessions.clear()
    s._sweep = Mock()
    flush_once(s, monkeypatch)
    s._sweep.assert_called_once()
    assert not s.plugin_dirty


def test_batches_yield_and_keep_new_mutations_and_membership_checks(monkeypatch):
    s = server()
    peers = [peer(s, "player", str(i)) for i in range(600)]
    s.plugins_changed("lesson")
    calls = 0
    removed = None
    async def yield_once(_):
        nonlocal calls, removed
        calls += 1
        if calls == 1:
            assert sum(c.push.called for c in peers) == 16
            removed = next(c for c in peers if not c.push.called)
            s.conns["lesson"].remove(removed)
            s.plugins_changed("lesson")
    monkeypatch.setattr("texstage.server.app.asyncio.sleep", yield_once)
    asyncio.run(s.flush_plugins())
    assert calls == 38
    assert sum(c.push.called for c in peers) == 599
    removed.push.assert_not_called()
    assert s.plugin_dirty == {"lesson"}


@pytest.mark.parametrize("operation", ["plugin.command", "plugin.result"])
def test_receipt_follows_durable_operation_without_eager_broadcast(operation):
    s = server()
    s.push = Mock(side_effect=AssertionError("eager broadcast"))
    bridge = object.__new__(PluginHost)
    bridge.sync_points = lambda sid: None  # this fixture isolates broadcast scheduling
    bridge.server = s
    bridge.identity = lambda conn: ("participant" if operation == "plugin.command" else "presenter", "authenticated")
    bridge.sync = lambda sid: (None, SimpleNamespace(items={"kind": {"one": {}}}), [])
    bridge.runtime = SimpleNamespace(command=Mock(return_value={"accepted": True}),
        finish=Mock(return_value=True), drain=Mock(), take_changes=Mock(return_value=None))
    result = bridge.handle(SimpleNamespace(session="lesson", role="stage", key="owner"),
        {"t": operation, "command": {"type": "kind", "item": "one"}, "result": {}})
    assert result == ({"receipt": {"accepted": True}} if operation == "plugin.command" else {"accepted": True})
    assert s.plugin_dirty == {"lesson"}
    assert (bridge.runtime.command if operation == "plugin.command" else bridge.runtime.finish).call_count == 1
    s.push.assert_not_called()


def test_targeted_updates_union_actors_and_keep_presenters_current(monkeypatch):
    s=server(); alice=peer(s,'player','alice'); bob=peer(s,'player','bob'); other=peer(s,'player','other')
    host=peer(s,'stage',None)
    s.plugins_changed('lesson',only={'alice'}); s.plugins_changed('lesson',only={'bob'})
    flush_once(s,monkeypatch)
    alice.push.assert_called_once(); bob.push.assert_called_once(); host.push.assert_called_once()
    other.push.assert_not_called(); assert not s.plugin_dirty and not s.plugin_recipients


def test_global_update_dominates_targeted_notifications(monkeypatch):
    s=server(); alice=peer(s,'player','alice'); other=peer(s,'player','other')
    s.plugins_changed('lesson',only={'alice'}); s.plugins_changed('lesson'); s.plugins_changed('lesson',only={'alice'})
    flush_once(s,monkeypatch)
    alice.push.assert_called_once(); other.push.assert_called_once()
