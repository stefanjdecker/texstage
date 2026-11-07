# SPDX-License-Identifier: Apache-2.0
"""Game points must be private, durable, idempotent and retractable."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_plugin_actor_records import catalog, TYPE
from test_game import World
from texstage.plugins import PluginError
from texstage.plugins.runtime import Runtime
from texstage.plugins.points import fixed_points
from texstage.server.game import Engine
from texstage.server.store import Store
from texstage.server.plugins import PluginHost


class Hooks:
    effects = None
    def close(self):pass
    def call(self,kind,method,*args):
        if method=='initial_state':return {'page':0}
        if method=='view':return {}
        state,event,ctx=args
        effects=[]
        if event['kind']=='command':
            effects=([{'kind':'publish-points'}] if event['operation']=='publish' else
                     [{'kind':'set-credit','credit':event['payload']['value']}])
            if self.effects is not None:effects=self.effects
        return {'state':copy.deepcopy(state),'effects':copy.deepcopy(effects)}


@pytest.fixture
def live(tmp_path):
    w=World(tmp_path,store_path=tmp_path/'game.sqlite3')
    a,b=w.join('Alice','Bob')
    def modify(m):
        m['manifest_version']=4
        spec=m['capabilities']['content_types'][TYPE]
        spec['scoring']={'policy':'fixed-v1','points_field':'points'}
        spec['messages']['publish']={'from':['presenter'],'revision_policy':'latest','schema':'fixture_plugin/view.json'}
    cat=catalog(tmp_path/'distribution',modify=modify)
    hooks=Hooks();r=Runtime(tmp_path/'plugins.sqlite3',cat,workers=hooks)
    r.ensure(w.session.id,TYPE,'activity',{'public':{'points':1000}})
    r.activate(w.session.id,{(TYPE,'activity')})
    bridge=object.__new__(PluginHost);bridge.runtime=r;bridge.point_versions={}
    bridge.server=SimpleNamespace(engine=w.engine,plugins_changed=Mock())
    yield w,r,hooks,bridge,a[0],b[0]
    r.close();w.engine.store.close()


def send(w,r,actor,operation,value=1000,request='request00001',epoch=1):
    return r.command(w.session.id,actor,'presenter' if operation in ('publish','_reset') else 'participant',
        {'type':TYPE,'item':'activity','operation':operation,'epoch':epoch,'expected_revision':0,
         'request_id':request,'payload':{} if operation in ('publish','_reset') else {'value':value}})


def test_reveal_points_total_leaderboard_export_and_exact_replay(live):
    w,r,_,bridge,a,b=live
    send(w,r,a.id,'submit');send(w,r,b.id,'submit',0)
    bridge.sync_points(w.session.id)
    assert a.score==b.score==a.rank==b.rank==0
    assert not w.session.activity_points
    assert r._ctx(r._item(w.session.id,TYPE,'activity'),role='participant',actor=a.id)['scoring']['awarded'] is None
    receipt=send(w,r,'teacher','publish')
    bridge.sync_points(w.session.id)
    assert (a.score,b.score,a.rank,b.rank)==(1000,0,1,2)
    bridge.server.plugins_changed.assert_called_once_with(w.session.id)
    assert w.engine.player_view(a.id,w.now)['me']['score']==1000
    assert w.engine.host_view(w.session.id,w.now)['players'][0]['score']==1000
    rows=w.engine.results_table(w.session.id)
    assert rows[0][-2:]==['activity activity credit','activity activity points']
    assert rows[1][-2:]==[1.0,1000] and rows[2][-2:]==[0.0,0]
    assert rows[1][2:5]==[1000,1,1]
    assert send(w,r,'teacher','publish')==receipt
    bridge.sync_points(w.session.id);assert a.score==1000
    # The exact absolute ledger may be redelivered after process restart.
    bridge.point_versions.clear();bridge.sync_points(w.session.id);assert a.score==1000
    assert len(w.session.activity_points)==1


def test_replacement_late_result_reset_and_mixed_quiz_rescore(live):
    w,r,_,bridge,a,b=live
    round_=w.show('question','pick');w.engine.tick(w.at(3000))
    w.engine.answer(a.id,round_.id,{'choice':'B'},w.at(4000));w.show('reveal','pick')
    quiz_points=a.score;streak=a.streak
    send(w,r,a.id,'submit',1000);send(w,r,a.id,'submit',0,request='replacement1')
    send(w,r,b.id,'submit',500)
    send(w,r,'teacher','publish');bridge.sync_points(w.session.id)
    assert a.score==quiz_points and b.score==500 and a.streak==streak
    # Real runtime delivery uses this same authenticated job actor path.
    row=r._item(w.session.id,TYPE,'activity')
    r._commit(row,{'state':{'page':0},'effects':[{'kind':'set-credit','credit':1000}]},record_actor=a.id)
    bridge.sync_points(w.session.id);assert a.score==quiz_points+1000
    w.engine._rescore(w.session);w.engine._commit()
    assert a.score==quiz_points+1000 and b.score==500 and a.streak==streak
    send(w,r,'teacher','_reset',request='reset0000001');bridge.sync_points(w.session.id)
    assert a.score==quiz_points and b.score==0
    assert not any(x.published for x in w.session.activity_points.values())
    assert r.archive(w.session.id)['point_credits']==[]
    assert send(w,r,a.id,'submit',request='stale0000001')['error']=='stale-epoch'
    send(w,r,a.id,'submit',epoch=2,request='new000000001')
    send(w,r,'teacher','publish',epoch=2,request='newpublish01');bridge.sync_points(w.session.id)
    assert a.score==quiz_points+1000  # one current-epoch award, never cumulative farming


def test_recovery_after_runtime_commit_before_game_commit_and_restart(live,monkeypatch):
    w,r,_,bridge,a,b=live
    send(w,r,a.id,'submit');send(w,r,'teacher','publish')
    original=w.engine.replace_activity_points
    def fail(_):raise OSError('simulated game-store interruption')
    monkeypatch.setattr(w.engine,'replace_activity_points',fail)
    with pytest.raises(OSError):bridge.sync_points(w.session.id)
    assert a.score==0 and bridge.point_versions=={}
    monkeypatch.setattr(w.engine,'replace_activity_points',original)
    bridge.sync_points(w.session.id);assert a.score==1000
    w.engine.store.close()
    w.engine=Engine(w.bundles,Store(w.store_path));w.session=w.engine.session(w.session.id)
    bridge.server.engine=w.engine;bridge.point_versions.clear()
    bridge.sync_points(w.session.id)
    assert w.session.players[a.id].score==1000
    send(w,r,'teacher','_reset',request='reset0000001');bridge.sync_points(w.session.id)
    assert w.session.players[a.id].score==0


def test_game_transaction_failure_rolls_back_points_and_projection(live,monkeypatch):
    w,r,_,bridge,a,_=live
    send(w,r,a.id,'submit');send(w,r,'teacher','publish')
    commit=w.engine.store.commit
    monkeypatch.setattr(w.engine.store,'commit',lambda:(_ for _ in ()).throw(OSError('write failed')))
    with pytest.raises(OSError):bridge.sync_points(w.session.id)
    assert a.score==0 and not w.session.activity_points
    assert w.engine.store.db.execute('select count(*) from activity_points').fetchone()[0]==0
    monkeypatch.setattr(w.engine.store,'commit',commit)
    bridge.sync_points(w.session.id);assert a.score==1000


@pytest.mark.parametrize('effects',[
    [{'kind':'publish-points'}],
    [{'kind':'set-credit','credit':1001}],
    [{'kind':'set-credit','credit':True}],
    [{'kind':'set-credit','credit':0.5}],
    [{'kind':'set-credit','credit':1000,'actor':'someone-else'}],
    [{'kind':'set-credit','credit':1000}]*2,
])
def test_scoring_effect_authority_and_bounds_are_atomic(live,effects):
    w,r,h,_,a,_=live;h.effects=effects
    before=dict(r._item(w.session.id,TYPE,'activity'))
    with pytest.raises(PluginError):send(w,r,a.id,'submit')
    assert dict(r._item(w.session.id,TYPE,'activity'))==before
    assert not r.archive(w.session.id)['point_rounds']
    assert not r.archive(w.session.id)['point_credits']


def test_practice_mode_and_invalid_public_point_settings(live):
    w,r,_,bridge,a,_=live
    for bad in (True,1.5,-1,10001,None,'1000'):
        with pytest.raises(PluginError):fixed_points({'points':bad},{'scoring':{'points_field':'points'}})
    r.ensure(w.session.id,TYPE,'practice',{'public':{'points':0}})
    row=r._item(w.session.id,TYPE,'practice')
    r._commit(row,{'state':{},'effects':[{'kind':'set-credit','credit':1000}]},record_actor=a.id)
    row=r._item(w.session.id,TYPE,'practice')
    r._commit(row,{'state':{},'effects':[{'kind':'publish-points'}]},scoring_role='presenter')
    bridge.sync_points(w.session.id)
    assert a.score==0 and not r.points.heads(w.session.id)


def test_storage_failure_rolls_back_credit_with_item_and_receipt(live,monkeypatch):
    w,r,_,_,a,_=live
    apply=r.points.apply
    def fail(*args,**kwargs):apply(*args,**kwargs);raise OSError('credit insert failed')
    monkeypatch.setattr(r.points,'apply',fail)
    with pytest.raises(OSError):send(w,r,a.id,'submit')
    assert r.db.execute('select count(*) from receipts').fetchone()[0]==0
    assert not r.points.heads(w.session.id)
    monkeypatch.setattr(r.points,'apply',apply)
    assert send(w,r,a.id,'submit')['accepted']
