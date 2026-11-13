# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A kind's own files for the browser (texstage/server/kindfiles.py; the plan of F2, 4.5, package 8): what a
phone loads and what the windows load besides, by the path a browser asks for in the kind's folder; the hash
of their contents, which changes with them and which the kinds of one package share - a file they share is
fetched once; each compressed once; what a page is told of a deck's kinds; the route's answer - cached for
ever, compressed where the browser takes it, nothing for a hash that is not the files' (app.py); the hints'
worker, which reaches no network."""
from __future__ import annotations

import gzip
import importlib
import itertools
import logging
import os
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from texstage.activities import kit, registry
from texstage.activities.kind import Kind
from texstage.server import kindfiles
from texstage.server.app import HINTS_POLICY, ServerConfig, create_app, gzip_taken

PACKAGES = itertools.count()
FILES = {
    "web/hint.js": 'import { cut } from "./cut.js";\nexport function hint() { return cut(); }\n',
    "web/cut.js": 'import "../../outside.js";\nexport const cut = () => null;\n',
    "web/input.js": 'import { cut } from "./cut.js";\nexport function input() { return cut(); }\n',
    "web/box.js": 'import { draw } from "./draw.js";\nimport { cut } from "./cut.js";\n'
                  "export function group(d) { return draw(d) ?? cut(); }\n",
    "web/draw.js": "export const draw = (d) => String(d);\n",
    "texts/en.js": "export default { said: 'Said.' }; // (not: import \"../__init__.py\")\n",
    "texts/de.js": "export default { said: 'Gesagt.' };\n",
    "README.md": "not for the browser\n",
}


def package(tmp_path, monkeypatch, files: dict[str, str] = FILES):
    """Two kinds of one package written for the test, with these files beside their module - and a file
    outside it, which one of them imports."""
    name = f"filekinds{next(PACKAGES)}"                  # (a module is imported once: a name for each)
    home = tmp_path / name
    home.mkdir()
    (home / "__init__.py").write_text("from texstage.activities.kind import Kind\n\n\nclass One(Kind):\n    NAME = 'one'\n\n\n"
                                      "class Two(Kind):\n    NAME = 'two'\n", encoding="utf-8")
    for rel, text in files.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_bytes(text.encode("utf-8"))
    (tmp_path / "outside.js").write_text("export const no = 1;\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    m = importlib.import_module(name)
    return home, m.One(), m.Two()


def installed(monkeypatch, *kinds) -> None:
    """These kinds are the installed ones."""
    by_name = {k.NAME: k for k in kinds}

    def kind(name):
        if name not in by_name:
            raise registry.Missing(f"no kind {name!r} is installed")
        return by_name[name]
    monkeypatch.setattr(registry, "kinds", lambda: dict(by_name))
    monkeypatch.setattr(registry, "kind", kind)


def test_a_kinds_files_for_the_phones_and_for_the_windows(tmp_path, monkeypatch):
    """A phone's: its modules, what they import from beside them, its texts; the windows' besides: box.js and its
    imports - not twice what a phone has; nothing outside the kind's folder, nothing of it that is not for the
    browser - though a comment names it as an import (the review of package 8)."""
    home, one, two = package(tmp_path, monkeypatch)
    files = kindfiles.of(one)
    assert files.phone == ["web/hint.js", "web/input.js", "web/cut.js", "texts/de.js", "texts/en.js"]
    assert files.window == ["web/box.js", "web/draw.js"]
    assert set(files.files) == set(files.phone) | set(files.window)
    data, packed, mime = files.files["web/hint.js"]
    assert data == FILES["web/hint.js"].encode() and gzip.decompress(packed) == data
    assert mime == "text/javascript; charset=utf-8"
    assert files.entry() == {"hash": files.hash, "phone": files.phone, "window": files.window}
    assert len(files.hash) == 20 and kindfiles.of(one).hash == files.hash
    assert kindfiles.of(two).hash == files.hash and kindfiles.of(two).files == files.files    # one package: one hash
    (home / "web" / "draw.js").write_text("export const draw = (d) => `${d}`;\n", encoding="utf-8")
    assert kindfiles.of(one).hash != files.hash                          # a file changed: another hash
    (home / "texts" / "fr.js").write_text("export default { said: 'Dit.' };\n", encoding="utf-8")
    assert "texts/fr.js" in kindfiles.of(one).phone                      # (every language the kind has)


def link(path, target) -> None:
    """A folder that is a link to another - a junction on Windows (no rights needed), a symlink elsewhere."""
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(target)], check=True, capture_output=True)
    else:
        os.symlink(target, path, target_is_directory=True)


def test_a_link_in_the_kinds_folder_is_served_by_the_path_a_browser_asks_for(tmp_path, monkeypatch):
    """hint.js imports ./lib/util.js, and web/lib is a link to web/real: the browser asks for web/lib/util.js,
    and that is what the server serves (the review of package 8: it served web/real/util.js)."""
    home, one, _ = package(tmp_path, monkeypatch, {
        "web/hint.js": 'import { u } from "./lib/util.js";\nexport function hint() { return u; }\n',
        "web/real/util.js": "export const u = null;\n"})
    link(home / "web" / "lib", home / "web" / "real")
    files = kindfiles.of(one)
    assert files.phone == ["web/hint.js", "web/lib/util.js"]
    assert files.files["web/lib/util.js"][0] == b"export const u = null;\n"


def test_what_a_page_is_told_of_a_decks_kinds_and_what_it_gets(tmp_path, monkeypatch, caplog):
    home, one, two = package(tmp_path, monkeypatch)
    installed(monkeypatch, one, two)
    kinds = kindfiles.Kinds()
    items = {"a": {"kind": "one"}, "b": {"kind": "two"}, "c": {"kind": "gone"}, "d": {"input": "code", "engine": "?"}}
    told = kinds.deck(items)
    assert told == {"one": kindfiles.of(one).entry(), "two": kindfiles.of(one).entry()}     # a kind it lacks: not told
    assert told["one"]["hash"] == told["two"]["hash"]                    # one package: a file comes once
    assert kinds.deck({}) == {} and kinds.deck(None) == {}
    later = type("Later", (Kind,), {"NAME": "later"})()                 # installed after the server read the kinds
    installed(monkeypatch, one, two, later)
    assert kinds.deck({"a": {"kind": "later"}, "b": {"kind": "one"}}) == {"one": kindfiles.of(one).entry()}
    installed(monkeypatch, one, two)
    h = kinds.by_name["one"].hash
    assert kinds.file(h, "texts/en.js")[0] == FILES["texts/en.js"].encode()
    assert kinds.file(h, "web/box.js") is not None
    for digest, path in (("0" * 20, "texts/en.js"), (h, "README.md"), (h, "__init__.py"), (h, "../outside.js"), (h, "")):
        assert kinds.file(digest, path) is None, (digest, path)
    nowhere = type("Nowhere", (Kind,), {"NAME": "nowhere", "__module__": "builtins"})()      # a class of no file
    installed(monkeypatch, one, nowhere)
    with caplog.at_level(logging.WARNING, logger="texstage.server"):
        kinds.reload()
    assert kinds.by_name["nowhere"].files == {} and "the kind nowhere has no files for the browser" in caplog.text
    assert kinds.deck({"a": {"kind": "nowhere"}}) == {"nowhere": {"hash": "", "phone": [], "window": []}}
    assert kinds.file("", "texts/en.js") is None


def test_the_server_serves_what_the_kit_counts():
    assert set(kindfiles.MEDIA) == set(kit.SERVED)


@pytest.mark.parametrize("header, taken", [
    ("gzip", True), ("gzip, deflate, br", True), ("br;q=1.0, gzip;q=0.8, *;q=0.1", True), ("*", True), ("GZip", True),
    ("*;q=0, gzip", True), ("", False), ("identity", False), ("deflate, br", False), ("gzip;q=0", False),
    ("gzip;q=0, *", False), ("gzip;q=0.0", False), ("gzip;q=x", False), ("br, *;q=0", False),
])
def test_whether_a_browser_takes_gzip(header, taken):
    assert gzip_taken(header) is taken


def test_the_server_serves_a_kinds_files_by_their_hash(tmp_path, monkeypatch):
    """Cached for ever - a file changed is another hash -, compressed where the browser takes it; nothing for
    another hash, a file that is not for the browser. The hints' worker reaches no network: no fetch, and no
    import but from the server (the review of package 8: an import() from elsewhere took the student's text)."""
    home, one, two = package(tmp_path, monkeypatch)
    installed(monkeypatch, one)
    (tmp_path / "bundles").mkdir()
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key="k" * 24)
    with TestClient(create_app(config)) as client:
        h = kindfiles.of(one).hash
        r = client.get(f"/kinds/{h}/web/hint.js")                   # (the test client takes gzip, and unpacks it)
        assert r.status_code == 200 and r.content == FILES["web/hint.js"].encode()
        assert r.headers["content-encoding"] == "gzip" and r.headers["vary"] == "Accept-Encoding"
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert r.headers["content-type"] == "text/javascript; charset=utf-8"
        plain = client.get(f"/kinds/{h}/texts/de.js", headers={"Accept-Encoding": "identity"})
        assert plain.content == FILES["texts/de.js"].encode() and "content-encoding" not in plain.headers
        for path in (f"/kinds/{'0' * 20}/web/hint.js", f"/kinds/{h}/README.md", f"/kinds/{h}/__init__.py",
                     f"/kinds/{h}/web/../../outside.js", f"/kinds/{h}/", f"/kinds/one/{h}/web/hint.js"):
            assert client.get(path).status_code == 404, path
        worker = client.get("/static/play/hint-worker.js")
        assert worker.status_code == 200 and worker.headers["content-security-policy"] == HINTS_POLICY
        assert HINTS_POLICY == "default-src 'none'; script-src 'self'"
        assert client.get("/static/stage/evaluator-worker.js").headers["content-security-policy"] == "connect-src 'none'"
