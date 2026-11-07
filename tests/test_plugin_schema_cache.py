# SPDX-License-Identifier: Apache-2.0
"""Exact-content schema caching must preserve validation and schema confinement."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from texstage.plugins import PluginError
from texstage.plugins.manifest import _schema_validator, validate_json

@pytest.fixture(autouse=True)
def clear_cache():
    _schema_validator.cache_clear()
    yield
    _schema_validator.cache_clear()

def test_reuses_checked_content_but_validates_every_value():
    schema={"type":"object","properties":{"n":{"type":"integer","minimum":0}},
            "required":["n"],"additionalProperties":False}
    validate_json(schema,{"n":1})
    validate_json(copy.deepcopy(schema),{"n":2})
    assert _schema_validator.cache_info().hits==1
    for value in ({"n":True},{"n":-1},{"n":"2"},{"n":2,"extra":0},{}):
        with pytest.raises(PluginError): validate_json(schema,value)
    assert _schema_validator.cache_info().misses==1

def test_mutating_a_schema_cannot_change_an_existing_validator_or_bypass_checks():
    original={"type":"integer","minimum":0}
    changed=copy.deepcopy(original)
    validate_json(changed,2)
    changed["minimum"]=5
    with pytest.raises(PluginError):validate_json(changed,2)
    validate_json(original,2)
    changed["$ref"]="https://invalid.example/schema"
    with pytest.raises(PluginError,match="local fragment"):validate_json(changed,10)
    with pytest.raises(PluginError):validate_json(original,"secret")
    assert "secret" not in str(pytest.raises(PluginError,validate_json,original,"secret").value)

@pytest.mark.parametrize("change",[
    {"$ref":"file:///private/schema.json"},{"$id":"https://invalid.example/"},
    {"$dynamicRef":"#anything"},{"properties":{"x":{"$ref":"https://invalid.example/schema"}}},
    {"type":"not-a-type"},
])
def test_forbidden_and_invalid_schemas_never_enter_the_cache(change):
    with pytest.raises(PluginError):validate_json(change,{})
    assert _schema_validator.cache_info().currsize==0

def test_large_schema_is_not_retained_and_is_still_enforced():
    large={"type":"integer","description":"x"*70000}
    validate_json(large,1)
    with pytest.raises(PluginError):validate_json(large,"1")
    assert _schema_validator.cache_info().currsize==0

def test_cache_count_is_bounded_and_eviction_does_not_skip_validation():
    for n in range(129):validate_json({"const":n},n)
    assert _schema_validator.cache_info().currsize==128
    with pytest.raises(PluginError):validate_json({"const":0},1)
    assert _schema_validator.cache_info().currsize==128

def test_local_references_and_concurrent_validation():
    schema={"$defs":{"n":{"type":"integer","minimum":0}},"$ref":"#/$defs/n"}
    def check(n):
        try:validate_json(schema,n);return True
        except PluginError:return False
    values=list(range(-30,30))
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(check,values))==[n>=0 for n in values]
