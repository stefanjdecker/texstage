# SPDX-License-Identifier: Apache-2.0
"""Quiz speed/streak parity with durable clocks and mixed activity timelines."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_game import World, T0
from test_plugin_actor_records import catalog, TYPE
from texstage.plugins import PluginError
from texstage.plugins.runtime import Runtime
from texstage.plugins.points import point_settings
from texstage.plugins.manifest import canonical, load_manifest
from texstage.server.activity_points import scoring_context
from texstage.server.game import Engine
from texstage.server.store import Store
from texstage.server.plugins import PluginHost


class Hooks:
    def close(self):pass
    def call(self,kind,method,*args):
        if method=='initial_state':return {'page':0}
        if method=='view':return {}
        state,event,ctx=args;effects=[]
        if event['kind']=='command':
            op=event['operation']
            if op in ('open','close'):effects=[{'kind':'points-open','open':op=='open'}]
            elif op=='publish':effects=[{'kind':'publish-points'}]
            else:effects=[{'kind':'set-credit','credit':None if event['payload']['value']==9999 else event['payload']['value']}]
        return {'state':copy.deepcopy(state),'effects':effects}


@pytest.fixture
def live(tmp_path):
    w=World(tmp_path,store_path=tmp_path/'game.sqlite3');a,b=w.join('Alice','Bob')
    def modify(m):
        m['manifest_version']=5
        spec=m['capabilities']['content_types'][TYPE]
        spec['scoring']={'policy':'quiz-v1','points_field':'points','time_field':'time'}
        for op in ('open','close','publish'):
            spec['messages'][op]={'from':['presenter'],'revision_policy':'latest','schema':'fixture_plugin/view.json'}
    cat=catalog(tmp_path/'distribution',modify=modify)
    r=Runtime(tmp_path/'plugins.sqlite3',cat,workers=Hooks())
    r.ensure(w.session.id,TYPE,'activity',{'public':{'points':1000,'time':120}})
    r.activate(w.session.id,{(TYPE,'activity')})
    bridge=object.__new__(PluginHost);bridge.runtime=r;bridge.point_versions={}
    bridge.server=SimpleNamespace(engine=w.engine,plugins_changed=Mock())
    yield w,r,bridge,a[0],b[0]
    r.close();w.engine.store.close()


def send(live,op,seconds,*,value=1000,actor=None,request=None,item='activity',epoch=1):
    w,r,_,a,_=live;role='participant' if op=='submit' else 'presenter'
    return r.command(w.session.id,actor or (a.id if role=='participant' else 'teacher'),role,
        {'type':TYPE,'item':item,'operation':op,'epoch':epoch,'expected_revision':0,
         'request_id':request or f'{op}request{seconds:09d}','payload':{'value':value} if op=='submit' else {}},
        now=T0/1000+seconds)


def complete(live,credit=1000):
    w,r,_,a,_=live
    row=r._item(w.session.id,TYPE,'activity')
    r._commit(row,{'state':{'page':0},'effects':[{'kind':'set-credit','credit':credit}]},
              record_actor=a.id,scoring_now=T0+900000)


def reveal(live,seconds=60):
    send(live,'close',seconds-1);send(live,'publish',seconds)
    live[2].sync_points(live[0].session.id)


def own(live):
    w,_,_,a,_=live
    return scoring_context(w.session,TYPE,'activity',a.id)


def test_host_submission_time_and_latest_answer_ignore_evaluator_delay(live):
    w,r,bridge,a,b=live
    send(live,'open',0);receipt=send(live,'submit',30,value=9999,request='firstrequest1')
    assert send(live,'submit',100,value=9999,request='firstrequest1')==receipt
    reveal(live,150);assert a.score==0 and own(live)['awarded'] is None
    complete(live);bridge.sync_points(w.session.id)
    assert own(live)=={'maximum':1000,'released':True,'awarded':875,'base_points':875,'bonus':0,'answer_ms':30000,'streak':1}
    assert (a.score,a.streak,a.total_ms)==(875,1,30000)
    bridge.point_versions.clear();bridge.sync_points(w.session.id)
    assert a.score==875
    assert w.engine.results_table(w.session.id)[1][-5:]==[1.0,875,875,0,30000]
    assert w.engine.player_view(a.id,w.now)['me']['score']==875


def test_replacement_uses_new_time_and_pause_resume_excludes_closed_time(live):
    send(live,'open',0);send(live,'submit',5,value=9999)
    send(live,'close',10);send(live,'open',100)
    send(live,'submit',110,value=9999);complete(live);reveal(live,120)
    assert own(live)['answer_ms']==20000 and own(live)['awarded']==917


def test_speed_floor_and_no_automatic_closure(live):
    send(live,'open',0);assert send(live,'submit',180)['accepted'];reveal(live,200)
    assert own(live)['answer_ms']==120000 and own(live)['awarded']==500


def quizzes_around_pending_activity(live):
    w,r,bridge,a,b=live
    q=w.show('question','pick');w.engine.tick(w.at(3000))
    w.engine.answer(a.id,q.id,{'choice':'B'},w.at(5000));w.show('reveal','pick')
    assert a.score==950
    send(live,'open',10);send(live,'submit',40,value=9999);reveal(live,60)
    w.at(70000);q=w.show('question','many');w.engine.tick(w.at(73000))
    w.engine.answer(a.id,q.id,{'choices':['A','C']},w.at(74000));w.at(75000);w.show('reveal','many')
    assert a.score==2025 and a.streak==2
    return q


@pytest.mark.parametrize('credit,total,streak,bonus',[(1000,3100,3,200),(0,1925,1,0),(None,2025,2,100)])
def test_late_feedback_recomputes_downstream_quiz_bonus_and_reset(live,credit,total,streak,bonus):
    w,r,bridge,a,b=live;q=quizzes_around_pending_activity(live)
    complete(live,credit);bridge.sync_points(w.session.id)
    assert a.score==total and a.streak==streak and q.answers[a.id].bonus==bonus
    send(live,'_reset',600);bridge.sync_points(w.session.id)
    assert a.score==2025 and a.streak==2 and q.answers[a.id].bonus==100


def test_restart_and_replayed_projection_preserve_timing_and_bonuses(live):
    w,r,bridge,a,b=live;quizzes_around_pending_activity(live);complete(live);bridge.sync_points(w.session.id)
    aid=a.id;w.engine.store.close();w.engine=Engine(w.bundles,Store(w.store_path));w.session=w.engine.session(w.session.id)
    bridge.server.engine=w.engine;bridge.point_versions.clear();bridge.sync_points(w.session.id)
    a=w.session.players[aid]
    assert (a.score,a.streak,a.total_ms)==(3100,3,33000)
    assert scoring_context(w.session,TYPE,'activity',aid)['bonus']==100
    send(live,'_reset',600);bridge.sync_points(w.session.id)
    assert a.score==2025 and a.streak==2 and a.total_ms==3000


def test_failed_game_commit_restores_scores_bonuses_and_computed_results(live,monkeypatch):
    w,r,bridge,a,b=live;q=quizzes_around_pending_activity(live)
    before=(a.score,a.streak,a.total_ms,a.rank,a.prev_rank,q.answers[a.id].bonus)
    complete(live);commit=w.engine.store.commit
    monkeypatch.setattr(w.engine.store,'commit',lambda:(_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):bridge.sync_points(w.session.id)
    assert (a.score,a.streak,a.total_ms,a.rank,a.prev_rank,q.answers[a.id].bonus)==before
    assert own(live)['awarded'] is None
    monkeypatch.setattr(w.engine.store,'commit',commit);bridge.sync_points(w.session.id)
    assert a.score==3100 and q.answers[a.id].bonus==200


def test_private_second_attempt_does_not_replay_or_broadcast_scores(live,monkeypatch):
    w,r,bridge,a,b=live;quizzes_around_pending_activity(live)
    complete(live);bridge.sync_points(w.session.id)
    send(live,'_reset',600);bridge.sync_points(w.session.id)
    before=(a.score,a.streak,a.total_ms,a.rank,a.prev_rank)
    bridge.server.plugins_changed.reset_mock()
    with monkeypatch.context() as patch:
        patch.setattr('texstage.server.activity_points.rescore',lambda *args:pytest.fail('private attempt replayed scores'))
        for op,seconds in [('open',610),('submit',620),('close',625)]:
            send(live,op,seconds,epoch=2);bridge.sync_points(w.session.id)
        complete(live);bridge.sync_points(w.session.id)
        assert (a.score,a.streak,a.total_ms,a.rank,a.prev_rank)==before
        bridge.server.plugins_changed.assert_not_called()
        assert w.session.activity_points[TYPE,'activity'].revision==r.points.heads(w.session.id)[0]['revision']
    send(live,'publish',630,epoch=2);bridge.sync_points(w.session.id)
    assert a.score==3183 and a.streak==3 and own(live)['awarded']==1158
    bridge.server.plugins_changed.assert_called_once_with(w.session.id)


@pytest.mark.parametrize('enabled,expected',[(True,10500),(False,8000)])
def test_quiz_streak_bonus_cap_and_host_setting(live,enabled,expected):
    w,r,bridge,a,b=live;w.engine.settings.streak_bonus=enabled
    for i in range(8):
        item=f'item{i}';r.ensure(w.session.id,TYPE,item,{'public':{'points':1000,'time':120}})
        r.activate(w.session.id,{(TYPE,item)})
        send(live,'open',10*i,item=item);send(live,'submit',10*i,item=item)
        send(live,'close',10*i+1,item=item);send(live,'publish',10*i+2,item=item);bridge.sync_points(w.session.id)
    assert a.score==expected and a.streak==8


def test_missing_answer_breaks_streak_but_unavailable_is_neutral(live):
    w,r,bridge,a,b=live
    send(live,'open',0);send(live,'submit',0);reveal(live,1)
    for i,value in enumerate((9999,None,1000),2):
        item=f'item{i}';r.ensure(w.session.id,TYPE,item,{'public':{'points':1000,'time':120}});r.activate(w.session.id,{(TYPE,item)})
        send(live,'open',i*10,item=item)
        if value is not None:send(live,'submit',i*10,item=item,value=value)
        send(live,'close',i*10+1,item=item);send(live,'publish',i*10+2,item=item);bridge.sync_points(w.session.id)
        assert a.streak=={2:1,3:0,4:1}[i]
    assert a.score==2000


def test_timing_authority_and_revision_gate(live):
    w,r,bridge,a,b=live
    manifest=copy.deepcopy(next(iter(r.catalog.providers.values())).manifest)
    manifest['manifest_version']=4
    with pytest.raises(PluginError):load_manifest(canonical(manifest))
    row=r._item(w.session.id,TYPE,'activity')
    with pytest.raises(PluginError):r._commit(row,{'state':{},'effects':[{'kind':'points-open','open':True}]},record_actor=a.id,scoring_role='participant')
    with pytest.raises(PluginError):complete(live)
    assert not r.points.heads(w.session.id)


@pytest.mark.parametrize('seconds',[0,3601,True,1.5,None,'120'])
def test_invalid_scoring_windows_are_rejected(seconds):
    with pytest.raises(PluginError):point_settings({'points':1000,'time':seconds},{'scoring':{'policy':'quiz-v1','points_field':'points','time_field':'time'}})
