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
    c.push = Mock()
    s.conns["lesson"].add(c)
    return c


def flush_once(s, monkeypatch):
    calls = 0
    async def sleep(_):
        nonlocal calls
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


@pytest.mark.parametrize("operation", ["plugin.command", "plugin.result"])
def test_receipt_follows_durable_operation_without_eager_broadcast(operation):
    s = server()
    s.push = Mock(side_effect=AssertionError("eager broadcast"))
    bridge = object.__new__(PluginHost)
    bridge.server = s
    bridge.identity = lambda conn: ("participant" if operation == "plugin.command" else "presenter", "authenticated")
    bridge.sync = lambda sid: (None, SimpleNamespace(items={"kind": {"one": {}}}), [])
    bridge.runtime = SimpleNamespace(command=Mock(return_value={"accepted": True}),
        finish=Mock(return_value=True), drain=Mock())
    result = bridge.handle(SimpleNamespace(session="lesson", role="stage", key="owner"),
        {"t": operation, "command": {"type": "kind", "item": "one"}, "result": {}})
    assert result == ({"receipt": {"accepted": True}} if operation == "plugin.command" else {"accepted": True})
    assert s.plugin_dirty == {"lesson"}
    assert (bridge.runtime.command if operation == "plugin.command" else bridge.runtime.finish).call_count == 1
    s.push.assert_not_called()
