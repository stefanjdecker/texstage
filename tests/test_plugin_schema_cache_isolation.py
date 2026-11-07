# SPDX-License-Identifier: Apache-2.0
"""Caching schema checks must not cache permission to accept an instance."""
import copy

import pytest

from texstage.plugins import PluginError
from texstage.plugins import manifest


@pytest.fixture(autouse=True)
def clean_cache():
    manifest._schema_validator.cache_clear()
    yield
    manifest._schema_validator.cache_clear()


def test_equivalent_schemas_reuse_check_but_every_value_is_validated():
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}},
              "required": ["answer"], "additionalProperties": False}
    manifest.validate_json(schema, {"answer": 2})
    reordered = dict(reversed(list(schema.items())))
    manifest.validate_json(reordered, {"answer": 3})
    assert manifest._schema_validator.cache_info().misses == 1
    assert manifest._schema_validator.cache_info().hits == 1
    with pytest.raises(PluginError, match=r"reply.*answer \(type\)"):
        manifest.validate_json(schema, {"answer": "private"}, label="reply")
    with pytest.raises(PluginError, match="additionalProperties"):
        manifest.validate_json(schema, {"answer": 2, "solution": 42})


def test_nested_mutation_requires_a_new_check():
    schema = {"type": "object", "properties": {"answer": {"enum": [1]}}}
    manifest.validate_json(schema, {"answer": 1})
    schema["properties"]["answer"]["enum"][:] = [2]
    with pytest.raises(PluginError, match="enum"):
        manifest.validate_json(schema, {"answer": 1})
    manifest.validate_json(schema, {"answer": 2})
    assert manifest._schema_validator.cache_info().misses == 2


@pytest.mark.parametrize("unsafe", [
    {"$ref": "https://example.invalid/schema"},
    {"$ref": "file:///secret"},
    {"$id": "https://example.invalid/scope"},
    {"$dynamicRef": "#x"},
    {"type": "not-a-json-type"},
])
def test_unsafe_mutation_is_rejected_and_failures_are_not_cached(unsafe):
    schema = {"properties": {"answer": {"type": "integer"}}}
    manifest.validate_json(schema, {"answer": 1})
    schema["properties"]["answer"] = unsafe
    for _ in range(2):
        with pytest.raises(PluginError):
            manifest.validate_json(schema, {"answer": 1})
    assert manifest._schema_validator.cache_info().currsize == 1
    assert manifest._schema_validator.cache_info().misses == 3


def test_error_schema_cannot_poison_future_validation():
    schema = {"properties": {"answer": {"enum": [1]}}}
    original = copy.deepcopy(schema)
    with pytest.raises(PluginError) as caught:
        manifest.validate_json(schema, {"answer": 2})
    caught.value.__cause__.schema["enum"].append(2)
    assert schema == original
    with pytest.raises(PluginError, match="enum"):
        manifest.validate_json(schema, {"answer": 2})


def test_bounded_cache_and_large_schemas_remain_valid_uncached():
    for n in range(128 + 10):
        manifest.validate_json({"const": n}, n)
    assert manifest._schema_validator.cache_info().currsize == 128
    manifest._schema_validator.cache_clear()
    large = {"type": "integer", "description": "x" * 64 * 1024}
    manifest.validate_json(large, 1)
    with pytest.raises(PluginError, match="type"):
        manifest.validate_json(large, "1")
    assert manifest._schema_validator.cache_info().currsize == 0


def test_boolean_schemas_and_local_references():
    manifest.validate_json(True, {"anything": 1})
    with pytest.raises(PluginError):
        manifest.validate_json(False, 1)
    schema = {"$defs": {"answer": {"type": "integer"}}, "$ref": "#/$defs/answer"}
    manifest.validate_json(schema, 1)
    with pytest.raises(PluginError, match="type"):
        manifest.validate_json(schema, "1")
