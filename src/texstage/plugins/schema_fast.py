# SPDX-License-Identifier: Apache-2.0
"""Compile a small JSON Schema subset to private, immutable predicates.

This is only a fast acceptance path after Draft 2020-12 schema safety checks.
Unsupported keywords or non-JSON values use the ordinary validator. A false
result also falls back, preserving its diagnostics and exception isolation.
No schema dictionaries, instance values or ValidationErrors enter the cache.
"""
from __future__ import annotations

import math

ANNOTATIONS = frozenset({'$schema', 'title', 'description', 'default', 'examples',
                         'deprecated', 'readOnly', 'writeOnly'})
KEYWORDS = ANNOTATIONS | {'type', 'enum', 'const', 'properties', 'required',
    'additionalProperties', 'minProperties', 'maxProperties', 'items',
    'minItems', 'maxItems', 'minLength', 'maxLength', 'minimum', 'maximum',
    'exclusiveMinimum', 'exclusiveMaximum', 'anyOf', 'allOf', 'oneOf'}


def _scalar_equal(value, expected):
    # Python considers True == 1; JSON Schema does not. Finite 1.0 == 1 is valid.
    if type(value) in (int, float) and type(expected) in (int, float):
        return value == expected
    return type(value) is type(expected) and value == expected


def compile_predicate(schema):
    """Return a predicate or None when any relevant constraint is unsupported."""
    if type(schema) is bool:
        return lambda value: schema
    if set(schema) - KEYWORDS:
        return None
    checks = []
    if 'type' in schema:
        types = schema['type']
        types = frozenset([types] if isinstance(types, str) else types)
        def kind(value):
            t = type(value)
            if t is int:
                return 'integer' in types or 'number' in types
            if t is float:
                return math.isfinite(value) and ('number' in types or
                    ('integer' in types and value.is_integer()))
            return {str: 'string', bool: 'boolean', dict: 'object',
                    list: 'array', type(None): 'null'}.get(t) in types
        checks.append(kind)
    for key in ('enum', 'const'):
        if key not in schema:
            continue
        values = schema[key] if key == 'enum' else [schema[key]]
        if any(type(v) not in (str, int, float, bool, type(None)) for v in values):
            return None
        choices = tuple(values)
        checks.append(lambda value, choices=choices: any(_scalar_equal(value, v) for v in choices))
    for key in ('anyOf', 'allOf', 'oneOf'):
        if key not in schema:
            continue
        children = tuple(compile_predicate(s) for s in schema[key])
        if any(child is None for child in children):
            return None
        if key == 'anyOf':
            checks.append(lambda value, children=children: any(c(value) for c in children))
        elif key == 'allOf':
            checks.append(lambda value, children=children: all(c(value) for c in children))
        else:
            checks.append(lambda value, children=children: sum(c(value) for c in children) == 1)

    object_keys = {'properties', 'required', 'additionalProperties', 'minProperties', 'maxProperties'}
    if object_keys.intersection(schema):
        properties = tuple((k, compile_predicate(v)) for k, v in schema.get('properties', {}).items())
        additional = compile_predicate(schema.get('additionalProperties', True))
        if additional is None or any(p is None for _, p in properties):
            return None
        names = frozenset(k for k, _ in properties)
        required = frozenset(schema.get('required', ()))
        lower, upper = schema.get('minProperties', 0), schema.get('maxProperties', math.inf)
        def object_value(value, lo=lower, hi=upper):
            if type(value) is not dict:
                return True
            return (lo <= len(value) <= hi and required.issubset(value) and
                    all(p(value[k]) for k, p in properties if k in value) and
                    all(additional(v) for k, v in value.items() if k not in names))
        checks.append(object_value)
    if {'items', 'minItems', 'maxItems'}.intersection(schema):
        items = compile_predicate(schema.get('items', True))
        if items is None:
            return None
        lower, upper = schema.get('minItems', 0), schema.get('maxItems', math.inf)
        checks.append(lambda value, items=items, lo=lower, hi=upper:
            type(value) is not list or (lo <= len(value) <= hi and all(items(v) for v in value)))
    if {'minLength', 'maxLength'}.intersection(schema):
        lower, upper = schema.get('minLength', 0), schema.get('maxLength', math.inf)
        checks.append(lambda value, lo=lower, hi=upper: type(value) is not str or lo <= len(value) <= hi)
    for key in ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum'):
        if key not in schema:
            continue
        bound = schema[key]
        def number(value, bound=bound, key=key):
            if type(value) not in (int, float):
                return True
            if type(value) is float and not math.isfinite(value):
                return False
            if key == 'minimum': return value >= bound
            if key == 'maximum': return value <= bound
            if key == 'exclusiveMinimum': return value > bound
            return value < bound
        checks.append(number)
    predicates = tuple(checks)
    return lambda value: (type(value) in (str, int, float, bool, dict, list, type(None))
                          and all(check(value) for check in predicates))
