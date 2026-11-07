# SPDX-License-Identifier: Apache-2.0
"""Load-discovered host invariants: cached schemas and evaluator disconnects."""
import copy
from types import SimpleNamespace

import pytest

from texstage.plugins import PluginError
from texstage.plugins import manifest
from texstage.server.plugins import PluginHost
from test_plugins import command, provider, start


def test_schema_cache_checks_every_instance_and_schema_mutation(monkeypatch):
    manifest._schema_validator.cache_clear()
    calls = []
    original = manifest.Draft202012Validator.check_schema
    monkeypatch.setattr(manifest.Draft202012Validator, 'check_schema',
                        lambda schema: (calls.append(copy.deepcopy(schema)), original(schema))[1])
    schema = {'type': 'integer', 'minimum': 0}
    manifest.validate_json(schema, 1)
    manifest.validate_json(copy.deepcopy(schema), 2)
    assert len(calls) == 1
    with pytest.raises(PluginError):
        manifest.validate_json(schema, -1)
    assert len(calls) == 1
    schema['minimum'] = 3
    with pytest.raises(PluginError):
        manifest.validate_json(schema, 2)
    assert len(calls) == 2
    assert manifest._schema_validator.cache_info().maxsize == 128


@pytest.mark.parametrize('extra', [
    {'$ref': 'https://invalid.example/schema'},
    {'$id': 'https://invalid.example/scope'}, {'$dynamicRef': '#local'},
    {'type': 'not-a-type'},
])
def test_cached_validation_still_rejects_forbidden_or_invalid_schemas(extra):
    manifest.validate_schema({'type': 'integer'})
    with pytest.raises(PluginError):
        manifest.validate_json({'type': 'integer'} | extra, 1)


def test_large_schemas_are_validated_without_retaining_them():
    manifest._schema_validator.cache_clear()
    schema = {'type': 'integer', 'description': 'x' * (64 * 1024)}
    manifest.validate_json(schema, 1)
    assert manifest._schema_validator.cache_info().currsize == 0
    with pytest.raises(PluginError):
        manifest.validate_json(schema, 'bad')


def test_disconnect_releases_only_owned_leases_and_rejects_old_results(tmp_path, provider):
    runtime = start(tmp_path, provider)
    try:
        for i in range(3):
            runtime.command('session', str(i), 'participant', command(f'request{i:04d}'))
        old = runtime.lease('session', 'old', now=10, limit=1)[0]
        other = runtime.lease('session', 'other', now=10, limit=1)[0]
        result = {k: old[k] for k in ('id', 'epoch', 'generation')} | {'outcome': {'status': 'error'}}
        assert runtime.release('another-session', 'old') == 0
        assert runtime.release('session', 'missing') == 0
        assert runtime.release('session', 'old') == 1
        assert runtime.release('session', 'old') == 0
        assert not runtime.finish('session', 'old', result, now=11)
        new = runtime.lease('session', 'new', now=11, limit=1)[0]
        assert new['id'] == old['id'] and new['generation'] == old['generation'] + 1
        assert not runtime.finish('session', 'old', result, now=12)
        assert runtime.db.execute('SELECT owner FROM jobs WHERE id=?', (other['id'],)).fetchone()[0] == 'other'
        new_result = {k: new[k] for k in ('id', 'epoch', 'generation')} | {'outcome': {'status': 'error'}}
        assert runtime.finish('session', 'new', new_result, now=12)
        assert runtime.release('session', 'new') == 0  # never resurrect terminal jobs
    finally:
        runtime.close()


def test_repeated_disconnects_do_not_reset_retry_budget(tmp_path, provider):
    runtime = start(tmp_path, provider)
    try:
        runtime.command('session', 'alice', 'participant', command())
        for generation in range(1, 4):
            job = runtime.lease('session', 'owner', now=generation)[0]
            assert job['generation'] == generation
            runtime.release('session', 'owner')
        assert runtime.lease('session', 'owner', now=4) == []
        runtime.drain('session')
        row = runtime.db.execute('SELECT status,result,delivered FROM jobs').fetchone()
        assert tuple(row) == ('failed', '{"status":"timeout"}', 1)
    finally:
        runtime.close()


def test_bridge_disconnect_never_releases_other_roles():
    calls = []
    host = object.__new__(PluginHost)
    host.runtime = SimpleNamespace(release=lambda *args: calls.append(args))
    for role in ('player', 'host', 'display', None):
        host.disconnect(SimpleNamespace(role=role, session='session', key='owner'))
    assert calls == []
    host.disconnect(SimpleNamespace(role='stage', session='session', key='owner'))
    assert calls == [('session', 'owner')]


def test_presenter_controls_push_immediately_but_student_bursts_coalesce():
    # A presenter can select then share. Returning its receipt while keeping
    # the old guarded view queued made that sequence fail with stale-control.
    calls = []
    host = object.__new__(PluginHost)
    receipt = {'accepted': True, 'epoch': 1, 'revision': 2}
    host.runtime = SimpleNamespace(command=lambda *args: receipt)
    host.server = SimpleNamespace(push=lambda sid: calls.append(('push', sid)),
                                  plugins_changed=lambda sid: calls.append(('coalesce', sid)))
    host.sync = lambda sid: (None, SimpleNamespace(items={'org.example.plane': {'one': {}}}), [])
    host.identity = lambda conn: (conn.role, 'actor')
    message = {'t': 'plugin.command', 'command': {'type': 'org.example.plane', 'item': 'one'}}
    for role in ('participant', 'presenter'):
        assert host.handle(SimpleNamespace(role=role, session='s'), message) == {'receipt': receipt}
    assert calls == [('coalesce', 's'), ('push', 's')]
