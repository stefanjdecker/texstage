# SPDX-License-Identifier: Apache-2.0
"""Grouped disk commits must not acknowledge uncommitted or cross-actor data."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from texstage.plugins import PluginError
from texstage.plugins.runtime import COMMAND_BATCH
from texstage.server.plugins import PluginHost
from test_plugins import command, provider, start
from test_plugin_actor_records import live, command as actor_command, TYPE


def entry(actor, request, **changes):
    return ('session', actor, command(request, **changes), 123.0)


def test_batch_commits_once_and_is_durable_before_return(tmp_path, provider):
    r = start(tmp_path, provider)
    observer = sqlite3.connect(tmp_path / 'state.sqlite3')
    calls, statements = [], []
    original = r.workers.call
    def hook(*args):
        calls.append(observer.execute('SELECT count(*) FROM receipts').fetchone()[0])
        return original(*args)
    r.workers.call = hook
    r.db.set_trace_callback(statements.append)
    entries = [entry('alice', 'request0001'), entry('bob', 'request0002')]
    try:
        result = r.command_batch(entries)
        assert all(reply['accepted'] for reply in result)
        assert calls == [0, 0]  # no partial commit observable during hooks
        assert statements.count('COMMIT') == 1
        assert observer.execute('SELECT count(*) FROM receipts').fetchone()[0] == 2
        assert observer.execute('SELECT count(*) FROM jobs').fetchone()[0] == 2
        assert r.db.execute('PRAGMA synchronous').fetchone()[0] == 2  # FULL
        r.close()
        r = start(tmp_path, provider)
        assert r.command_batch(entries) == result  # lost ACK/restart is idempotent
        assert r.db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 2
    finally:
        observer.close()
        r.close()


def test_each_rejected_command_rolls_back_and_neighbors_still_commit(tmp_path, provider, monkeypatch):
    r = start(tmp_path, provider)
    save = r._save_receipt
    def fail_after_write(sid, actor, *args):
        save(sid, actor, *args)
        if actor == 'bad': raise PluginError('injected after write')
    monkeypatch.setattr(r, '_save_receipt', fail_after_write)
    try:
        replies = r.command_batch([entry('alice','request0001'), entry('bad','request0002'),
            entry('bob','request0003'), entry('schema','request0004',payload={'value':True}),
            entry('role','request0005',operation='_reset',payload={}),
            entry('stale','request0006',epoch=0), entry('refused','request0007',payload={'value':-1})])
        assert replies[0]['accepted'] and replies[2]['accepted']
        assert all(isinstance(replies[i], PluginError) for i in (1,3,4))
        assert replies[5]['error'] == 'stale-epoch'
        assert replies[6]['error'] == 'negative-value'
        assert r.db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 2
        assert r.db.execute('SELECT count(*) FROM receipts').fetchone()[0] == 4
        row = r._item('session', command()['type'], 'item')
        assert json.loads(row['state'])['values'] == [3,3]
        assert row['revision'] == 3 and row['epoch'] == 1
    finally: r.close()


def test_failed_outer_commit_rolls_back_every_receipt_and_notification(tmp_path, provider):
    r = start(tmp_path, provider)
    before = dict(r.changes)
    db = r.db
    class FailingCommit:
        def __getattr__(self, key): return getattr(db, key)
        def execute(self, sql, *args):
            if sql == 'COMMIT': raise sqlite3.OperationalError('injected disk failure')
            return db.execute(sql, *args)
    r.db = FailingCommit()
    try:
        with pytest.raises(sqlite3.OperationalError):
            r.command_batch([entry('alice','request0001'), entry('bob','request0002')])
        assert not db.in_transaction
        assert r.changes == before
        assert db.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
        r.db = db
        assert r.command_batch([entry('alice','request0001')])[0]['accepted']
    finally:
        r.db = db
        r.close()


def test_actor_records_in_a_batch_remain_private_and_ordered(live):
    r,h,_ = live
    replies = r.command_batch([('session', actor, actor_command(i,value=value), 123.0)
        for i,(actor,value) in enumerate([('alice',11),('bob',22),('alice',33)])])
    assert all(x['accepted'] for x in replies)
    contexts = h.contexts[-3:]
    assert [c['records']['value'] for c in contexts] == [None,None,{'answer':11}]
    assert all('record_page' not in c for c in contexts)
    r.view('session',TYPE,'exercise','participant','participant-input','bob')
    assert h.contexts[-1]['records']['value'] == {'answer':22}


def test_batch_size_is_bounded(tmp_path, provider):
    r = start(tmp_path, provider)
    try:
        for entries in ([],[entry('a','request0001')]*(COMMAND_BATCH+1)):
            with pytest.raises(PluginError,match='batch size'): r.command_batch(entries)
    finally: r.close()


def test_queue_rechecks_auth_and_yields_between_bounded_batches():
    async def scenario():
        host = PluginHost.__new__(PluginHost)
        host.command_queue = asyncio.Queue(maxsize=64)
        host.server = SimpleNamespace(plugins_changed=lambda *a,**k:None)
        chunks = []
        def batch(calls):
            chunks.append([x[1] for x in calls])
            return [{'accepted':True} for _ in calls]
        host.runtime = SimpleNamespace(command_batch=batch,drain=lambda sid:None,take_changes=lambda sid:set())
        host.sync_points = lambda sid:None
        host.sync = lambda sid:(None,SimpleNamespace(items={'type':{'item':{}}}),[])
        def identity(conn):
            if conn.revoked: raise PluginError('participant is no longer in this session')
            return 'participant',conn.actor
        host.identity = identity
        conns = [SimpleNamespace(session='s',actor=str(i),revoked=False) for i in range(140)]
        message = {'t':'plugin.command','command':{'type':'type','item':'item'}}
        tasks = [asyncio.create_task(host.submit(conn,message,123)) for conn in conns]
        await asyncio.sleep(0)
        assert host.command_queue.qsize() == 64  # excess readers wait, not a larger queue
        conns[0].revoked = True
        worker = asyncio.create_task(host.commands())
        try:
            replies = await asyncio.gather(*tasks,return_exceptions=True)
            assert isinstance(replies[0],PluginError)
            assert all(r['receipt']['accepted'] for r in replies[1:])
            assert all(len(c)<=COMMAND_BATCH for c in chunks)
            assert [a for c in chunks for a in c] == [str(i) for i in range(1,140)]
        finally:
            worker.cancel()
            await asyncio.gather(worker,return_exceptions=True)
    asyncio.run(scenario())


def test_busy_queue_cannot_starve_broadcasts_or_retain_unbounded_sessions():
    host = PluginHost.__new__(PluginHost)
    host.command_queue = asyncio.Queue(maxsize=64)
    host.broadcast_deferred = {}
    for _ in range(COMMAND_BATCH): host.command_queue.put_nowait(None)
    assert host.defer_broadcast('s',10)
    assert host.defer_broadcast('s',10.999)
    assert not host.defer_broadcast('s',11)
    assert 's' not in host.broadcast_deferred
    for i in range(200): host.defer_broadcast(str(i),12)
    assert len(host.broadcast_deferred) == 128
    while not host.command_queue.empty(): host.command_queue.get_nowait()
    assert not host.defer_broadcast('0',12.1)


def test_continuous_submissions_cannot_starve_evaluation():
    host = PluginHost.__new__(PluginHost)
    host.command_queue = asyncio.Queue(maxsize=64)
    host.evaluation_deferred = {}
    for _ in range(COMMAND_BATCH): host.command_queue.put_nowait(None)
    assert host.defer_evaluation('s', 10)
    assert host.defer_evaluation('s', 10.999)
    assert not host.defer_evaluation('s', 11)
    # A still-busy queue cannot restart the delay on every poll.
    assert not host.defer_evaluation('s', 11.01)
    assert not host.defer_evaluation('s', 100)
    for i in range(200): host.defer_evaluation(str(i), 100)
    assert len(host.evaluation_deferred) == 128
    assert not host.defer_evaluation('overflow', 100)
    while not host.command_queue.empty(): host.command_queue.get_nowait()
    assert not host.defer_evaluation('s', 101)
    assert 's' not in host.evaluation_deferred
    for _ in range(COMMAND_BATCH): host.command_queue.put_nowait(None)
    assert host.defer_evaluation('s', 102)


def test_spec_cache_retains_only_checked_text_and_returns_independent_values(tmp_path, provider):
    r = start(tmp_path, provider)
    try:
        row = {'spec':'{"private":{"answer":[1]}}'}
        first = r._spec(row)
        first['private']['answer'].append(2)
        assert r._spec(row) == {'private':{'answer':[1]}}
        row['spec'] = '{"private":{"answer":[3]}}'
        assert r._spec(row)['private']['answer'] == [3]
        for invalid in ('{"x":1,"x":2}','{"x":NaN}'):
            with pytest.raises(PluginError): r._spec({'spec':invalid})
            assert invalid not in r.checked_specs
        for i in range(40): r._spec({'spec':json.dumps({'n':i})})
        assert len(r.checked_specs) == 32
        large = json.dumps({'note':'x'*65536})
        assert r._spec({'spec':large})['note'] == 'x'*65536
        assert large not in r.checked_specs
    finally: r.close()
