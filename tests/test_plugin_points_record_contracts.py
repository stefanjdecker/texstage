# SPDX-License-Identifier: Apache-2.0
import pytest
from texstage.plugins import PluginError
from test_plugin_contracts import installed, TYPE, ENGINE
from test_plugin_actor_records import catalog


def test_scoring_manifest_retains_bounded_records_notifications_and_cache(tmp_path):
    def change(m):
        m['manifest_version']=4
        m['capabilities']['content_types'][TYPE].update(state_records=True,participant_updates='actor',
            scoring={'policy':'fixed-v1','points_field':'points'})
        m['capabilities']['engines'][ENGINE]['result_cache']='by-input'
    p=installed(tmp_path,mutate=change)
    assert p.manifest['capabilities']['content_types'][TYPE]['state_records'] is True


def test_record_context_contracts_cannot_be_combined(tmp_path):
    def change(m):
        m['manifest_version']=4
        m['capabilities']['content_types'][TYPE]['state_records']=True
    with pytest.raises(PluginError): catalog(tmp_path,modify=change)
