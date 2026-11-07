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
    s.plugins = SimpleNamespace(safe_views=lambda conns: {c: {"private_actor": c.player} for c in conns})
    return s


def peer(s, role, actor):
    class Connection:
        pass
    c = Connection()
    c.role, c.player, c.qa, c.session = role, actor, False, "lesson"
    c.push = Mock()
    s.conns["lesson"].add(c)
    return c


def flush_once(s, monkeypatch):
    calls = 0
    async def sleep(delay):
        nonlocal calls
        if delay == 0: return
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
    bridge.sync_points = lambda sid: None
    bridge.sync = lambda sid: (None, SimpleNamespace(items={"kind": {"one": {}}}), [])
    bridge.runtime = SimpleNamespace(command=Mock(return_value={"accepted": True}),
        finish=Mock(return_value=True), drain=Mock(), take_changes=Mock(return_value=None))
    result = bridge.handle(SimpleNamespace(session="lesson", role="stage", key="owner"),
        {"t": operation, "command": {"type": "kind", "item": "one"}, "result": {}})
    assert result == ({"receipt": {"accepted": True}} if operation == "plugin.command" else {"accepted": True})
    assert s.plugin_dirty == {"lesson"}
    assert (bridge.runtime.command if operation == "plugin.command" else bridge.runtime.finish).call_count == 1
    s.push.assert_not_called()


def test_yielded_batches_refresh_membership_and_preserve_new_dirty_generation(monkeypatch):
    s = server()
    peers = [peer(s, "player", str(i)) for i in range(65)]
    s.plugins_changed("lesson")
    yielded = 0
    removed = moved = None
    async def yield_to_commands(delay):
        nonlocal yielded, removed, moved
        assert delay == 0
        yielded += 1
        if yielded == 1:
            unsent = [c for c in peers if not c.push.called]
            removed, moved = unsent[:2]
            s.conns["lesson"].remove(removed)
            moved.session = "other-session"
            s.plugins_changed("lesson")
    monkeypatch.setattr("texstage.server.app.asyncio.sleep", yield_to_commands)
    asyncio.run(s.flush_plugins())
    assert yielded == 5 and s.plugin_dirty == {"lesson"}
    removed.push.assert_not_called()
    moved.push.assert_not_called()
    for c in peers:
        if c not in (removed, moved):
            c.push.assert_called_once()
            assert c.push.call_args.args[0]["private_actor"] == c.player


def test_actor_updates_reach_both_devices_and_hosts_but_not_other_students(monkeypatch):
    s = server()
    a, a2, b = peer(s,"player","alice"), peer(s,"player","alice"), peer(s,"player","bob")
    teacher, projector = peer(s,"stage",None), peer(s,"display",None)
    s.plugins_changed("lesson",only={"alice"})
    flush_once(s,monkeypatch)
    for c in (a,a2,teacher,projector):c.push.assert_called_once()
    b.push.assert_not_called()
    assert not s.plugin_dirty and not s.plugin_recipients
    s.plugins_changed("lesson",only={"alice"})
    s.plugins_changed("lesson")  # shared-state change dominates targeted markers
    s.plugins_changed("lesson",only={"bob"})
    assert s.plugin_recipients["lesson"] is None
    s.plugin_push_after.clear()
    flush_once(s,monkeypatch)
    b.push.assert_called_once()
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


def test_presenter_receipt_projects_lecturers_then_flushes_the_class(monkeypatch):
    s=server();students=[peer(s,'player',str(i)) for i in range(600)]
    teacher=peer(s,'stage',None);projector=peer(s,'display',None)
    bridge=object.__new__(PluginHost);bridge.server=s
    bridge.identity=lambda conn: ('presenter','authenticated')
    bridge.sync_points=lambda sid: None
    bridge.sync=lambda sid: (None,SimpleNamespace(items={'kind':{'one':{}}}),[])
    bridge.runtime=SimpleNamespace(command=Mock(return_value={'accepted':True}),drain=Mock(),take_changes=Mock(return_value=None))
    result=bridge.handle(SimpleNamespace(session='lesson',role='stage',key='owner'),{'t':'plugin.command','command':{'type':'kind','item':'one'}})
    assert result=={'receipt':{'accepted':True}}
    teacher.push.assert_called_once();projector.push.assert_called_once()
    assert all(not p.push.called for p in students)
    assert s.plugin_dirty=={'lesson'}
    flush_once(s,monkeypatch)
    for p in students:
        p.push.assert_called_once()
        assert p.push.call_args.args[0]['private_actor']==p.player
