# SPDX-License-Identifier: Apache-2.0
"""Public exports are projector projections, not filtered private archives."""
import io
import json
import zipfile
import pytest
from texstage.plugins import PluginError
from test_plugin_actor_records import live, TYPE
from test_server import world, KEY, hello


def test_public_export_uses_projector_and_omits_private_state(live):
    runtime, hooks, _ = live
    result = runtime.public_archive('session')
    row = result['items'][0]
    assert set(result) == {'format', 'surface', 'items'}
    assert set(row) == {'type', 'item', 'provider', 'snapshot'}
    assert row['snapshot']['data'] == {}
    assert hooks.contexts[-1]['role'] == 'projector'
    assert hooks.contexts[-1].get('actor') is None
    assert runtime.public_archive('other')['items'] == []
    raw = json.dumps(result)
    for key in ('records', 'jobs', 'receipts', 'spec', 'state', 'sid'):
        assert '"' + key + '"' not in raw


def test_public_export_fails_closed(live, monkeypatch):
    runtime, _, _ = live
    def failure(*args, **kwargs):
        raise PluginError('private-path-and-submission')
    monkeypatch.setattr(runtime, 'view', failure)
    result = runtime.public_archive('session')
    assert result['items'][0]['unavailable'] == 'projector-view-unavailable'
    assert 'private-path-and-submission' not in json.dumps(result)
    provider, spec = runtime.catalog.capability(TYPE)
    spec.pop('view_schemas')
    monkeypatch.setattr(type(runtime.catalog), 'capability', lambda self, kind: (provider, spec))
    assert runtime.public_archive('session')['items'][0]['unavailable'] == 'projector-schema-required'


def test_archive_routes_require_presenter_and_no_plugin_fallback(world):
    client, fb = world
    with client.websocket_connect('/ws') as ws:
        sid = hello(ws, fb)['session']
    for filename in ('plugins.json', 'plugins-public.json'):
        url = f'/api/archive/{sid}/{filename}'
        assert client.get(url).status_code == 403
        assert client.get(url, headers={'X-Texquiz-Key': 'wrong'}).status_code == 403
        reply = client.get(url, headers={'X-Texquiz-Key': KEY})
        assert reply.status_code == 200 and reply.headers['cache-control'] == 'no-store'
        assert reply.json()['items'] == []
        assert client.get('/api/archive/unknown/'+filename, headers={'X-Texquiz-Key': KEY}).status_code == 404


def test_private_json_allowed_in_zip_and_recording_group_unchanged(tmp_path):
    from texstage.server.archive import files
    for name in ('plugins.json','plugins-public.json','recording-123456abcdef.webm','secrets.json'):
        (tmp_path/name).write_text('{}')
    entries = files(tmp_path)
    assert [x['name'] for x in entries] == ['plugins.json','recording-123456abcdef.webm']
    assert entries[1]['take'] == '123456abcdef'


def test_lecturer_zip_includes_the_private_plugin_snapshot(world, monkeypatch):
    from types import SimpleNamespace
    client, fb = world
    with client.websocket_connect('/ws') as ws:
        sid = hello(ws, fb)['session']
    server = client.app.state.server
    private = {'format': 1, 'items': [], 'actor_records': [{'actor': 'private-student'}]}
    # Isolate ZIP assembly from runtime setup; runtime privacy is tested above.
    with monkeypatch.context() as patch:
        patch.setattr(server.plugins, 'sync', lambda sid: None)
        patch.setattr(server.plugins, 'runtime', SimpleNamespace(archive=lambda session: private))
        reply = client.get(f'/api/archive/{sid}.zip', headers={'X-Texquiz-Key': KEY})
        assert reply.status_code == 200
        with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
            assert json.loads(archive.read('plugins.json')) == private
            assert 'plugins-public.json' not in archive.namelist()
