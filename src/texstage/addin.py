# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The PowerPoint add-in "texstage": its manifests and their registration on a PC
(docs/design.md, sections 5.1 and 5.4).

The add-in is a content add-in: the builder puts one object of it over every live slide.
Its page is served by a quiz server at /addin/, and PowerPoint loads it from the address
in the add-in's manifest - so every server has an add-in of its own, with an ID derived
from the server's address (build/powerpoint.py: addin_id). A PPTX references the add-in
of its server (texstage build --server, texstage retarget); if that server is not running,
its live slides simply show their pictures.

    texstage addin install [--url http://localhost:8470]    register the server's add-in for this user
    texstage addin list                                     the registered texstage add-ins
    texstage addin uninstall [--url ... | --all]
    texstage addin manifest [--url ...] > manifest.xml       e.g. for a shared-folder catalog

Registering = a value in HKCU\\Software\\Microsoft\\Office\\16.0\\WEF\\Developer (name: the
add-in ID, data: the manifest's path), which PowerPoint reads at start - verified in spike S1.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from texstage.build.powerpoint import ADDIN_VERSION, addin_id, origin

DEVELOPER_KEY = r"Software\Microsoft\Office\16.0\WEF\Developer"
MANIFEST = re.compile(r"(texstage|texquiz)-addin[\w.-]*\.xml$")   # the manifests written here (texquiz-: until 2026-10-10)


def manifest(server: str) -> str:
    o = origin(server)
    name = escape(o.split("://", 1)[1])
    o = escape(o)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:type="ContentApp">
  <Id>{addin_id(server)}</Id>
  <Version>{ADDIN_VERSION}</Version>
  <ProviderName>texstage</ProviderName>
  <DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="texstage ({name})"/>
  <Description DefaultValue="Live quizzes on texstage slides with the quiz server {o}: lobby, questions, answers, leaderboard.">
    <Override Locale="de-DE" Value="Live-Quizze auf texstage-Folien mit dem Quiz-Server {o}: Lobby, Fragen, Antworten, Bestenliste."/>
  </Description>
  <IconUrl DefaultValue="{o}/addin/icon-32.png"/>
  <HighResolutionIconUrl DefaultValue="{o}/addin/icon-64.png"/>
  <SupportUrl DefaultValue="{o}/host"/>
  <AppDomains>
    <AppDomain>{o}</AppDomain>
  </AppDomains>
  <Hosts>
    <Host Name="Presentation"/>
  </Hosts>
  <DefaultSettings>
    <SourceLocation DefaultValue="{o}/addin/"/>
    <RequestedWidth>640</RequestedWidth>
    <RequestedHeight>360</RequestedHeight>
  </DefaultSettings>
  <Permissions>ReadDocument</Permissions>
  <AllowSnapshot>true</AllowSnapshot>
</OfficeApp>
"""


def manifest_name(server: str) -> str:
    """texstage-addin-localhost-8470.xml, texstage-addin-quiz.example.org.xml"""
    return "texstage-addin-" + re.sub(r"[^\w.-]+", "-", origin(server).split("://", 1)[1]).strip("-") + ".xml"


def install(server: str, data_dir: Path, key: str = DEVELOPER_KEY) -> Path:
    """Write the server's manifest into the data folder and register it for this Windows user."""
    import winreg
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / manifest_name(server)
    path.write_text(manifest(server), encoding="utf-8")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, addin_id(server), 0, winreg.REG_SZ, str(path))
    return path


def installed(key: str = DEVELOPER_KEY) -> dict[str, str]:
    """The registered texstage add-ins: {add-in ID: manifest path}."""
    if sys.platform != "win32":
        return {}
    import winreg
    found = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, value, _ = winreg.EnumValue(k, i)
                if isinstance(value, str) and MANIFEST.search(value):
                    found[name] = value
    except FileNotFoundError:
        pass
    return found


def manifest_server(path: str) -> str | None:
    """The server a manifest file names (None: unreadable)."""
    try:
        m = re.search(r'<SourceLocation DefaultValue="([^"]+)/addin/"', Path(path).read_text(encoding="utf-8"))
    except OSError:
        return None
    return m.group(1) if m else None


def uninstall(server: str | None = None, key: str = DEVELOPER_KEY) -> list[str]:
    """Removes the registration of this server's add-in, or (None) of every texstage add-in;
    returns the removed add-in IDs."""
    import winreg
    ids = [addin_id(server)] if server else list(installed(key))
    removed = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            for i in ids:
                try:
                    winreg.DeleteValue(k, i)
                    removed.append(i)
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        pass
    return removed
