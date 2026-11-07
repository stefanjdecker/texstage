# SPDX-License-Identifier: Apache-2.0
"""Reusing a schema check must never reuse another actor's view or accept changes."""
import copy
import json
import pytest
from test_plugin_contracts import typed, installed, TYPE
from test_plugins import Hooks, start
from texstage.plugins import PluginError


class Views(Hooks):
    def __init__(self):
        super().__init__()
        self.value = {'values': [1], 'active': True, 'finished': []}
        self.actors = []

    def call(self, kind, method, *args):
        if method == 'view':
            self.actors.append(args[1]['actor'])
            return copy.deepcopy(self.value)
        return super().call(kind, method, *args)


def test_reused_check_still_runs_each_actor_hook_and_rejects_changed_data(tmp_path, typed):
    hooks = Views()
    r = start(tmp_path, typed, hooks=hooks)
    try:
        def view(actor='alice'):
            return r.view('session', TYPE, 'item', 'participant', 'participant-input', actor)['data']
        first = view()
        first['values'].append(99)
        assert view('bob')['values'] == [1]
        assert hooks.actors == ['alice', 'bob']
        for bad in ([True], ['1'], (1,)):
            hooks.value['values'] = bad
            with pytest.raises(PluginError):
                view()
        hooks.value['values'] = [1]
        hooks.value['extra'] = 'not in the closed schema'
        with pytest.raises(PluginError):
            view()
        del hooks.value['extra']
        for i in range(140):
            hooks.value['values'] = [i]
            assert view()['values'] == [i]
        assert len(r.view_checks) <= 128
    finally:
        r.close()


def test_success_for_one_surface_schema_cannot_validate_another(tmp_path):
    def different_schema(manifest):
        content = manifest['capabilities']['content_types'][TYPE]
        content['view_schemas']['participant-input'] = 'fixture_plugin/result.json'
    provider = installed(tmp_path / 'provider', mutate=different_schema)
    hooks = Views()
    r = start(tmp_path, provider, hooks=hooks)
    try:
        r.view('session', TYPE, 'item', 'presenter', 'presenter-controls', 'teacher')
        # Identical bytes pass the first schema, but not the second.
        with pytest.raises(PluginError):
            r.view('session', TYPE, 'item', 'participant', 'participant-input', 'alice')
    finally:
        r.close()


def test_prepared_spec_checks_keep_fresh_contexts_and_reject_invalid_changes(tmp_path, typed):
    r = start(tmp_path, typed)
    try:
        row = dict(r._item('session', TYPE, 'item'))
        r._spec(row)['public']['changed'] = True
        assert r._spec(row)['public'] == {}
        for raw in ('{"public":{},"public":{}}', '{"public":{"n":NaN}}'):
            with pytest.raises(PluginError):
                r._spec({**row, 'spec': raw})
        for i in range(20):
            raw = json.dumps({'public': {'points': i}})
            assert r._spec({**row, 'spec': raw})['public']['points'] == i
        assert len(r.spec_checks) <= 16
    finally:
        r.close()
