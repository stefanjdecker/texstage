# SPDX-License-Identifier: Apache-2.0
"""Opt-in deterministic outcomes never replace authentication or job guards."""
import json
import pytest
from texstage.plugins import PluginError
from test_plugins import command,start
from test_plugin_contracts import installed,outcome,finish,ENGINE,TYPE


@pytest.fixture
def runtime(tmp_path):
    p=installed(tmp_path/'provider',mutate=lambda m:m['capabilities']['engines'][ENGINE].update(result_cache='by-input'))
    r=start(tmp_path,p)
    yield r
    r.close()


def submit(r,n,value=3):
    r.command('session',str(n),'participant',command(f'request{n:06d}',payload={'value':value}))


def prime(r,n=0,value=3):
    submit(r,n,value); job=r.lease('session','owner',now=10)[0]
    result=outcome(job); assert finish(r,job,result,owner='owner')
    return job,result


def test_only_accepted_successes_are_immutable_and_input_scoped(runtime):
    r=runtime; job,value=prime(r)
    value['data']['valid']=False
    submit(r,1)
    assert r.db.execute("SELECT status FROM jobs WHERE actor='1'").fetchone()[0]=='succeeded'
    assert r.lease('session','owner',now=12)==[]
    row=r.db.execute("SELECT * FROM jobs WHERE actor='1'").fetchone()
    assert row['status']=='succeeded' and json.loads(row['result'])['data']['valid'] is True
    r.drain('session')
    assert len(r.archive('session')['items'])==1
    submit(r,2,value=4)
    assert len(r.lease('session','owner',now=13))==1


def test_failures_wrong_owners_invalid_facts_and_stale_generations_never_prime(runtime):
    r=runtime; submit(r,0); job=r.lease('session','owner',now=10)[0]
    assert not finish(r,job,outcome(job),owner='wrong')
    assert not r.outcomes
    with pytest.raises(PluginError): finish(r,job,outcome(job,data={'secret':True}),owner='owner')
    assert not r.outcomes
    assert r.release('session','owner')==1
    assert not finish(r,job,outcome(job),owner='owner')
    job=r.lease('session','owner',now=11)[0]
    assert finish(r,job,{'status':'timeout'},owner='owner',now=12)
    assert not r.outcomes


def test_seed_and_round_are_part_of_cache_identity(runtime):
    r=runtime; prime(r)
    row=r._item('session',TYPE,'item'); spec=json.loads(row['spec'])
    spec['evaluations']['value']['seed']='different'
    r.db.execute('UPDATE items SET spec=?',(json.dumps(spec),))
    submit(r,1)
    assert len(r.lease('session','owner',now=12))==1
    r.command('session','teacher','presenter',command('reset000001',operation='_reset',payload={},expected_revision=r._item('session',TYPE,'item')['revision']))
    spec['evaluations']['value']['seed']=''
    r.db.execute('UPDATE items SET spec=?',(json.dumps(spec),))
    r.command('session','new','participant',command('newround0001',epoch=2))
    assert len(r.lease('session','owner',now=13))==1


def test_other_sessions_items_and_cancelled_jobs_do_not_reuse_or_prime(runtime):
    r=runtime; prime(r)
    spec=json.loads(r._item('session',TYPE,'item')['spec'])
    for sid,item in [('another','item'),('session','another')]:
        r.ensure(sid,TYPE,item,spec)
        r.activate(sid,{(TYPE,item)})
        r.command(sid,'bob','participant',command('separate0001',item=item))
        jobs=r.lease(sid,'owner',now=12)
        assert len(jobs)==1
        job=jobs[0]
        r.db.execute("UPDATE jobs SET status='cancelled' WHERE id=?",(job['id'],))
        assert not r.finish(sid,'owner',{k:job[k] for k in ('id','epoch','generation')} |
                            {'outcome':outcome(job)},now=13)
    assert len(r.outcomes)==1


def test_bounded_cache_and_delivery_work(runtime,monkeypatch):
    r=runtime
    monkeypatch.setattr('texstage.plugins.runtime.MAX_CACHED_RESULTS',2)
    for n in range(3): prime(r,n,value=n)
    assert len(r.outcomes)==2
    retained=r.outcomes.copy(); r.outcomes.clear()
    for n in range(3,43): submit(r,n,value=2)
    r.outcomes.update(retained)
    before=r.db.execute("SELECT count(*) FROM jobs WHERE status='succeeded'").fetchone()[0]
    assert r.lease('session','owner',now=13)==[]
    after=r.db.execute("SELECT count(*) FROM jobs WHERE status='succeeded'").fetchone()[0]
    assert after-before==32 and r.pending('session')
    assert r.lease('session','owner',now=14)==[] and not r.pending('session')


def test_existing_providers_do_not_cache_by_default(tmp_path):
    r=start(tmp_path,installed(tmp_path/'provider'))
    try:
        prime(r); submit(r,1)
        assert not r.outcomes and len(r.lease('session','owner',now=12))==1
    finally: r.close()


def test_catalog_capabilities_remain_independent_snapshots(runtime):
    r=runtime
    _,first=r.catalog.capability(TYPE)
    first['messages']['submit']['from'].append('projector')
    first['state_records']=True
    _,second=r.catalog.capability(TYPE)
    assert 'projector' not in second['messages']['submit']['from']
    assert 'state_records' not in second


def test_a_failed_work_batch_rolls_back_cached_deliveries(runtime,monkeypatch):
    r=runtime; prime(r)
    retained=r.outcomes.copy(); r.outcomes.clear()
    submit(r,1); submit(r,2)
    r.outcomes.update(retained)
    original=r._outcome_key
    calls=0
    def fail_second(*args):
        nonlocal calls
        calls+=1
        if calls==2: raise RuntimeError('interrupted work batch')
        return original(*args)
    monkeypatch.setattr(r,'_outcome_key',fail_second)
    with pytest.raises(RuntimeError,match='interrupted'):
        r.lease('session','owner',now=12)
    assert [row[0] for row in r.db.execute("SELECT status FROM jobs WHERE actor IN ('1','2')")]==['queued','queued']
    monkeypatch.setattr(r,'_outcome_key',original)
    assert r.lease('session','owner',now=13)==[] and not r.pending('session')


def test_cached_jobs_survive_restart_without_the_memory_cache(tmp_path):
    p=installed(tmp_path/'provider',mutate=lambda m:m['capabilities']['engines'][ENGINE].update(result_cache='by-input'))
    r=start(tmp_path,p)
    prime(r); submit(r,1)
    r.close()
    r=start(tmp_path,p)
    try:
        assert not r.outcomes
        r.drain('session'); r.drain('session')
        state=json.loads(r._item('session',TYPE,'item')['state'])
        assert len(state['finished'])==2
        assert all(j['delivered']==1 for j in r.archive('session')['jobs'])
        submit(r,1)  # accepted receipt replay does not append another job
        assert len(r.archive('session')['jobs'])==2
    finally:
        r.close()
