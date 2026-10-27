# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The PowerPoint add-in (addin.py, its routes in server/app.py, web/addin/): the manifest,
the registration, and what the server serves it. The add-in itself runs inside PowerPoint
and is tested there (tools/slideshow.ps1, docs/design.md M4)."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

import pytest
from starlette.testclient import TestClient

from fake_bundle import make_bundle
from test_server import KEY, config
from texstage import addin
from texstage.build.powerpoint import addin_id
from texstage.cli import main
from texstage.server.app import create_app

NS = {"o": "http://schemas.microsoft.com/office/appforoffice/1.1"}


def test_every_server_has_its_own_addin():
    root = ET.fromstring(addin.manifest("https://Quiz.example.org/some/path"))
    assert root.find("o:Id", NS).text == addin_id("https://quiz.example.org")
    assert root.get("{http://www.w3.org/2001/XMLSchema-instance}type") == "ContentApp"
    assert root.find("o:DisplayName", NS).get("DefaultValue") == "texstage (quiz.example.org)"
    source = root.find("o:DefaultSettings/o:SourceLocation", NS).get("DefaultValue")
    assert source == "https://quiz.example.org/addin/"
    assert root.find("o:AppDomains/o:AppDomain", NS).text == "https://quiz.example.org"
    assert root.find("o:Permissions", NS).text == "ReadDocument"
    local = ET.fromstring(addin.manifest("http://localhost:8470"))
    assert local.find("o:Id", NS).text == addin_id("http://localhost:8470") != root.find("o:Id", NS).text
    assert addin.manifest_name("http://localhost:8470") == "texstage-addin-localhost-8470.xml"
    assert addin.manifest_name("https://quiz.example.org") == "texstage-addin-quiz.example.org.xml"


def test_the_addin_kept_its_id_when_texquiz_became_texstage():
    """Every live PPTX names its add-in by ID: the ID of a server's add-in is what it was before
    the rename (2026-10-10), and the manifests written then are still found (list, uninstall)."""
    assert addin_id("http://localhost:8470") == "dcbdd854-eb80-51fe-b925-d996343c5d05"
    assert addin.MANIFEST.search(r"C:\Users\x\.texquiz\texquiz-addin-localhost-8470.xml")
    assert addin.MANIFEST.search(r"C:\Users\x\.texstage\texstage-addin-localhost-8470.xml")
    assert not addin.MANIFEST.search(r"C:\Users\x\other-addin.xml")


def test_manifest_command(capsys):
    assert main(["addin", "manifest", "--url", "http://quiz.test/"]) == 0
    root = ET.fromstring(capsys.readouterr().out)
    assert root.find("o:DefaultSettings/o:SourceLocation", NS).get("DefaultValue") == "http://quiz.test/addin/"
    assert main(["addin", "manifest", "--url", "quiz.test"]) == 2               # not an address


@pytest.mark.skipif(sys.platform != "win32", reason="sideloading is Windows only")
def test_install_and_uninstall(tmp_path):
    key = r"Software\texquiz-tests\WEF\Developer"                  # not Office's key
    import winreg
    try:
        local = addin.install("http://localhost:8470", tmp_path / "data", key=key)
        hosted = addin.install("https://quiz.example.org", tmp_path / "data", key=key)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:                # someone else's add-in
            winreg.SetValueEx(k, "other-addin", 0, winreg.REG_SZ, str(tmp_path / "other.xml"))
        assert addin.installed(key) == {addin_id("http://localhost:8470"): str(local),
                                        addin_id("https://quiz.example.org"): str(hosted)}
        assert addin.manifest_server(str(hosted)) == "https://quiz.example.org"
        assert addin.uninstall("https://quiz.example.org", key) == [addin_id("https://quiz.example.org")]
        assert addin.uninstall("https://quiz.example.org", key) == []
        addin.install("https://quiz.example.org", tmp_path / "data", key=key)
        assert len(addin.uninstall(None, key)) == 2 and addin.installed(key) == {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            assert winreg.QueryValueEx(k, "other-addin")[0]                        # left alone
    finally:
        for sub in (r"Software\texquiz-tests\WEF\Developer", r"Software\texquiz-tests\WEF", r"Software\texquiz-tests"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:              # FileNotFoundError, or a key with values left (other-addin)
                if sub.endswith("Developer"):
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_SET_VALUE) as k:
                        winreg.DeleteValue(k, "other-addin")
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)


@pytest.fixture
def client(tmp_path):
    make_bundle(tmp_path / "bundles")
    with TestClient(create_app(config(tmp_path))) as c:
        yield c


def test_the_server_serves_the_addin(client):
    page = client.get("/addin/")
    assert page.status_code == 200 and "/static/addin/addin.js" in page.text and "office.js" in page.text
    for path in ("/static/addin/addin.js", "/static/addin/addin.css", "/static/shared/live.js"):
        assert client.get(path).status_code == 200, path
    root = ET.fromstring(client.get("/addin/manifest.xml").text)    # for the address it was asked at
    assert root.find("o:DefaultSettings/o:SourceLocation", NS).get("DefaultValue") == "http://testserver/addin/"
    icon = client.get("/addin/icon-32.png")
    assert icon.status_code == 200 and icon.content.startswith(b"\x89PNG")
    assert client.get("/addin/icon-33.png").status_code == 404


def test_client_log_is_for_hosts(client, caplog):
    assert client.post("/api/client-log", content=b'{"what":"error"}').status_code == 403
    with caplog.at_level("WARNING"):
        r = client.post("/api/client-log", content=b'{"what":"error"}', headers={"X-Texquiz-Key": KEY})
    assert r.status_code == 200 and 'client (local): {"what":"error"}' in caplog.text
