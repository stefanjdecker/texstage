# SPDX-License-Identifier: Apache-2.0
"""Later manifests retain bounded storage/cache options without mixing APIs."""
import pytest
from texstage.plugins import PluginError
from test_plugin_contracts import installed, TYPE, ENGINE


def configured(manifest, version):
    manifest["manifest_version"]=version
    kind=manifest["capabilities"]["content_types"][TYPE]
    kind.update(state_records=True,participant_updates="actor")
    manifest["capabilities"]["engines"][ENGINE]["result_cache"]="by-input"
    if version>=4:kind["scoring"]={"policy":"fixed-v1","points_field":"points"}


@pytest.mark.parametrize("version",[2,3,4,5])
def test_bounded_item_options_survive_manifest_revision(tmp_path,version):
    p=installed(tmp_path/f"v{version}",mutate=lambda m:configured(m,version))
    c=p.manifest["capabilities"]["content_types"][TYPE]
    assert c["state_records"] is True and c["participant_updates"]=="actor"
    assert p.manifest["capabilities"]["engines"][ENGINE]["result_cache"]=="by-input"


@pytest.mark.parametrize("version",[3,4,5])
def test_record_context_contracts_cannot_be_combined(tmp_path,version):
    def modify(m):
        configured(m,version)
        c=m["capabilities"]["content_types"][TYPE]
        schema=next(iter(c["view_schemas"].values()))
        c["actor_records"]={"capacity":1000,"page_size":16,"page_field":"page",
                           "value_schema":schema,"summary_schema":schema}
    with pytest.raises(PluginError,match="schema"):installed(tmp_path/"dual",mutate=modify)


@pytest.mark.parametrize("field,value",[
    ("state_records","true"),("participant_updates","everyone"),
    ("result_cache","cross-session"),("scoring",{"policy":"unlimited","points_field":"points"}),
    ("allow_network",True),
])
def test_new_manifest_options_keep_strict_values(tmp_path,field,value):
    def modify(m):
        configured(m,4)
        section="engines" if field=="result_cache" else "content_types"
        key=ENGINE if section=="engines" else TYPE
        m["capabilities"][section][key][field]=value
    with pytest.raises(PluginError):installed(tmp_path/"invalid",mutate=modify)
