# SPDX-License-Identifier: Apache-2.0
"""Bounded item records share the state/receipt/job transaction and epoch."""
import copy
import pytest
from texstage.plugins import PluginError
from texstage.plugins.runtime import Runtime
from texstage.plugins.catalog import Catalog
from texstage.plugin_api.v1 import evaluation_correlation
from test_plugins import Hooks, command, start
from test_plugin_contracts import installed, TYPE


class Records(Hooks):
    def __init__(self):
        super().__init__(); self.contexts=[]; self.keys=None; self.extra=None

    def call(self, kind, method, *args):
        if method == 'record_keys':
            return self.keys if self.keys is not None else ([args[-1]['actor']] if args[-1].get('actor') else [])
        if method in ('transition','view'):
            self.contexts.append(copy.deepcopy(args[-1].get('records',{})))
        value=super().call(kind,method,*args)
        if method=='transition' and args[1]['kind']=='command' and 'refusal' not in value:
            value['effects'][0]['correlation_id']=evaluation_correlation(args[-1]['actor'],args[1]['request_id'],'value')
            value['effects'].append(self.extra or {'kind':'put-record','key':args[-1]['actor'],
                'value':{'private':args[1]['payload']['value']}})
        return value


@pytest.fixture
def setup(tmp_path):
    p=installed(tmp_path/'provider',mutate=lambda m:m['capabilities']['content_types'][TYPE].update(state_records=True))
    hooks=Records(); r=start(tmp_path,p,hooks=hooks)
    yield r,hooks,p
    r.close()


def test_atomic_records_receipts_jobs_reset_and_restart(setup,tmp_path,monkeypatch):
    r,h,p=setup
    receipt=r.command('session','alice','participant',command())
    assert r.command('session','alice','participant',command())==receipt
    assert len(r.archive('session')['records'])==1
    original=r._save_receipt
    monkeypatch.setattr(r,'_save_receipt',lambda *args:(_ for _ in ()).throw(RuntimeError('crash')))
    with pytest.raises(RuntimeError): r.command('session','bob','participant',command())
    assert len(r.archive('session')['records'])==1
    monkeypatch.setattr(r,'_save_receipt',original)
    r2=Runtime(tmp_path/'state.sqlite3',Catalog([p]),workers=Records(),fingerprint='test-runtime')
    try:
        r2.view('session',TYPE,'item','participant','participant-input','alice')
        assert r2.workers.contexts[-1]=={'alice':{'private':3}}
        r2.view('session',TYPE,'item','participant','participant-input','bob')
        assert r2.workers.contexts[-1]=={}
        row=r2._item('session',TYPE,'item')
        r2.command('session','teacher','presenter',command('reset000001',operation='_reset',payload={},expected_revision=row['revision']))
        assert r2.archive('session')['records']==[]
        r2.view('session',TYPE,'item','participant','participant-input','alice')
        assert r2.workers.contexts[-1]=={}
    finally: r2.close()


@pytest.mark.parametrize('effect',[
    {'kind':'put-record','key':'x','value':'a'*4097},
    {'kind':'put-record','key':'','value':1},
    {'kind':'put-record','key':'x'*257,'value':1},
    {'kind':'put-record','key':'x','value':1,'extra':True},
])
def test_invalid_record_writes_are_atomic(setup,effect):
    r,h,p=setup; h.extra=effect
    with pytest.raises(PluginError): r.command('session','alice','participant',command())
    assert not r.archive('session')['records'] and not r.archive('session')['jobs']
    assert r.db.execute('SELECT count(*) FROM receipts').fetchone()[0]==0


def test_capacity_allows_replacement_not_new_record(setup,monkeypatch):
    r,h,p=setup; monkeypatch.setattr('texstage.plugins.runtime.MAX_RECORDS',1)
    r.command('session','alice','participant',command())
    r.command('session','alice','participant',command('replace00001',payload={'value':4}))
    with pytest.raises(PluginError,match='record capacity'):
        r.command('session','bob','participant',command())
    assert len(r.archive('session')['records'])==1
    r.view('session',TYPE,'item','participant','participant-input','alice')
    assert h.contexts[-1]['alice']['private']==4


@pytest.mark.parametrize('keys',[['x']*33,['x','x'],[True],['x'*257],'x'])
def test_read_sets_are_bounded(setup,keys):
    r,h,p=setup; h.keys=keys
    with pytest.raises(PluginError): r.view('session',TYPE,'item','participant','participant-input','alice')


def test_other_items_sessions_and_undeclared_providers_cannot_read_records(setup,tmp_path):
    r,h,p=setup; r.command('session','alice','participant',command())
    spec=r._ctx(r._item('session',TYPE,'item'))['item']
    for sid,item in [('other','item'),('session','other')]:
        r.ensure(sid,TYPE,item,spec)
        r.view(sid,TYPE,item,'participant','participant-input','alice')
        assert h.contexts[-1]=={}
    r.catalog=Catalog([installed(tmp_path/'undeclared')])
    with pytest.raises(PluginError,match='invalid record write'):
        r.command('session','alice','participant',command('disabled0001'))


def test_actor_scoped_changes_are_opt_in_and_global_controls_dominate(setup,tmp_path):
    r,h,p=setup
    p=installed(tmp_path/'targeted',mutate=lambda m:m['capabilities']['content_types'][TYPE].update(state_records=True,participant_updates='actor'))
    r.catalog=Catalog([p])
    assert r.take_changes('session') is None  # initial activation
    r.command('session','alice','participant',command())
    r.command('session','bob','participant',command())
    assert r.take_changes('session')=={'alice','bob'}
    r.command('session','alice','participant',command())  # receipt replay
    assert r.take_changes('session')==set()
    row=r._item('session',TYPE,'item')
    r.command('session','teacher','presenter',command('reset000001',operation='_reset',payload={},expected_revision=row['revision']))
    assert r.take_changes('session') is None


def test_record_pages_are_ordered_scoped_and_bounded(setup):
    r,h,p=setup
    for actor in ('zebra','bob','alice'):
        r.command('session',actor,'participant',command())
    h.keys={'keys':['zebra'],'page':{'offset':0,'limit':2}}
    r.view('session',TYPE,'item','presenter','presenter-controls','teacher')
    assert set(h.contexts[-1])=={'alice','bob','zebra'}
    row=r._item('session',TYPE,'item')
    ctx=r._record_context(row,{}, {},{})
    assert ctx['record_page']==['alice','bob']
    h.keys={'keys':[],'page':{'offset':2,'limit':2}}
    ctx=r._record_context(row,{}, {},{})
    assert ctx['record_page']==['zebra'] and set(ctx['records'])=={'zebra'}


@pytest.mark.parametrize('page',[{'offset':-1,'limit':1},{'offset':True,'limit':1},
    {'offset':0,'limit':33},{'offset':0,'limit':False},{'offset':0,'limit':1,'extra':1}])
def test_invalid_pages_are_rejected(setup,page):
    r,h,p=setup; h.keys={'keys':[],'page':page}
    with pytest.raises(PluginError): r.view('session',TYPE,'item','presenter','presenter-controls','teacher')
