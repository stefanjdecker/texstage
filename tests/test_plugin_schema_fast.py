# SPDX-License-Identifier: Apache-2.0
"""Differential acceptance checks against the authoritative JSON Schema validator."""
import copy
import itertools

import pytest
from jsonschema import Draft202012Validator

from texstage.plugins import PluginError
from texstage.plugins.manifest import validate_json, validate_json_many
from texstage.plugins.schema_fast import compile_predicate


VALUES = [None, False, True, -2, 0, 1, 1.0, 1.5, 2, '', 'a', 'ab', '\U0001f30d',
          [], [1], [True], [1, 2], [1, 'a'], {}, {'n': 1}, {'n': True},
          {'n': 'a'}, {'n': 1, 'private': 42}]
SCHEMAS = [True, False, {}, {'type': 'integer'}, {'type': ['object', 'null']},
    {'enum': [False, 1, 'a']}, {'const': True},
    {'type': 'number', 'minimum': 0, 'exclusiveMaximum': 2},
    {'exclusiveMinimum': 0, 'maximum': 1},
    {'type': 'string', 'minLength': 1, 'maxLength': 1},
    {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 1, 'maxItems': 2},
    {'properties': {'n': {'type': 'integer'}}, 'required': ['n'], 'additionalProperties': False},
    {'additionalProperties': {'type': 'integer'}, 'minProperties': 1, 'maxProperties': 2},
    {'anyOf': [{'type': 'null'}, {'type': 'object', 'required': ['n'],
                              'properties': {'n': {'type': 'integer'}}}]},
    {'oneOf': [{'type': 'integer'}, {'minimum': 1}]},
    {'allOf': [{'type': 'integer'}, {'minimum': 1}]},
    # Keywords of different types coexist and apply only to that type.
    {'minProperties': 2, 'maxProperties': 3, 'minItems': 1, 'maxItems': 1,
     'minLength': 0, 'maxLength': 1},
]


@pytest.mark.parametrize('schema', SCHEMAS)
def test_supported_acceptance_matches_draft(schema):
    Draft202012Validator.check_schema(schema)
    fast = compile_predicate(schema)
    assert fast is not None
    authoritative = Draft202012Validator(schema)
    values = VALUES + [{'n': v} for v in VALUES] + [list(v) for v in itertools.product([None, 1, 'a'], repeat=2)]
    for value in values:
        assert fast(value) == authoritative.is_valid(value), (schema, value)
        if authoritative.is_valid(value):
            validate_json(schema, value)
        else:
            with pytest.raises(PluginError):
                validate_json(schema, value)


@pytest.mark.parametrize('schema', [
    {'pattern': '^x$'}, {'uniqueItems': True}, {'multipleOf': 2},
    {'not': {'const': 0}}, {'if': {'const': 0}, 'then': False},
    {'$defs': {'n': {'type': 'integer'}}, '$ref': '#/$defs/n'},
    {'properties': {'n': {'pattern': '^x$'}}},
    {'anyOf': [{'type': 'null'}, {'pattern': '^x$'}]},
    {'const': {'nested': True}}, {'enum': [[1], [2]]},
    {'unevaluatedProperties': False}, {'dependentRequired': {'n': ['other']}},
])
def test_unsupported_constraint_falls_back_completely(schema):
    assert compile_predicate(schema) is None
    for value in VALUES:
        if Draft202012Validator(schema).is_valid(value):
            validate_json(schema, value)
        else:
            with pytest.raises(PluginError): validate_json(schema, value)


def test_private_predicates_and_batch_errors_do_not_share_schema():
    schema = {'properties': {'n': {'enum': [1]}}, 'additionalProperties': False}
    fast = compile_predicate(copy.deepcopy(schema))
    with pytest.raises(PluginError) as caught:
        validate_json_many(schema, [{'n': 1}, {'n': 2}])
    caught.value.__cause__.schema['enum'].append(2)
    schema['properties']['n']['enum'].append(2)
    assert not fast({'n': 2})
    with pytest.raises(PluginError):
        validate_json({'properties': {'n': {'enum': [1]}}}, {'n': 2})


def test_non_json_python_subclasses_use_authoritative_fallback():
    class CustomDict(dict): pass
    class CustomInt(int): pass
    for schema, value in [({'required': ['n']}, CustomDict()),
                          ({'minimum': 2}, CustomInt(1))]:
        assert not compile_predicate(schema)(value)
        with pytest.raises(PluginError): validate_json(schema, value)
