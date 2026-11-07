# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Carry the deck locale to every plugin surface, including phone mounts."""
from types import SimpleNamespace

import pytest
from texstage.server.plugins import PluginHost


@pytest.mark.parametrize("language,expected", [("de", "de"), ("en", "en"), (None, "en")])
@pytest.mark.parametrize("role", ["participant", "presenter", "projector"])
def test_plugin_projection_includes_deck_language_without_widening_roles(language, expected, role):
    surfaces = ["participant-input", "presenter-controls", "presenter-overlay", "projector-overlay"]
    spec = {"views": {surface: surface + ".mjs" for surface in surfaces}}
    provider = SimpleNamespace(payload="a" * 64, resources={})
    public = {"title": {"de": "Höchstens eine Anmeldung", "en": "At most one registration"}}
    bundle = SimpleNamespace(deck_json={"language": language} if language else {},
                             items={"org.example.lesson": {"one": public}})
    host = object.__new__(PluginHost)
    host.catalog = SimpleNamespace(fingerprint="catalog", capability=lambda kind: (provider, spec))
    calls = []
    def project(session, kind, item, requested_role, surface, actor, *, scoring=None):
        calls.append((requested_role, surface, actor))
        assert scoring is None
        return {"epoch": 1, "revision": 0, "data": {}}
    host.runtime = SimpleNamespace(view=project)
    host.server = SimpleNamespace(engine=SimpleNamespace(sessions={"test-session": SimpleNamespace(activity_points={})}))
    host.identity = lambda connection: (role, "authenticated")
    host.sync = lambda sid: (None, bundle, [("org.example.lesson", "one")])
    result = host.view(SimpleNamespace(session="test-session"))
    assert result["language"] == expected
    assert result["plugins"]["items"][0]["public"] == public
    assert set(result["plugins"]["items"][0]["modules"]) == {s for s in surfaces if s.startswith(role + "-")}
    assert all(r == role and s.startswith(role + "-") and a == "authenticated" for r, s, a in calls)
