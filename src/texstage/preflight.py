# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""texstage check: is a live deck ready to present on this PC? (docs/design.md, section 5.4)

    texstage check deck.pptx

reads what the deck's live slides carry (server, key, deck, bundle) and checks, in the
order things would fail in front of the class: the server's add-in is registered on this
PC, the server answers, it accepts the deck's key, it has the deck (or the join slide will
bring it), the phones' address leads to it (a tunnel: tried over the internet), PowerPoint
can load Office.js (internet). Ends with "ready" or what to do; exit status 1 if something
is missing.
"""
from __future__ import annotations

import ipaddress
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from texstage import __version__
from texstage.builds import CARRY_MAX

NS_WE = "{http://schemas.microsoft.com/office/webextensions/webextension/2010/11}"
OFFICE_JS = "https://appsforoffice.microsoft.com/lib/1/hosted/office.js"


@dataclass
class Deck:
    """What the live slides of a PPTX carry."""
    live: int = 0
    addins: set[str] = field(default_factory=set)
    servers: set[str] = field(default_factory=set)
    keys: set[str] = field(default_factory=set)
    decks: set[str] = field(default_factory=set)
    bundles: set[str] = field(default_factory=set)
    carries: bool = False                      # a join slide carries the bundle
    carried: int = 0                           # its size, base64 characters
    first: bool = False                        # a first slide prepares the live slides (since 2026-10-10)


def read_deck(pptx: Path) -> Deck:
    d = Deck()
    with zipfile.ZipFile(pptx) as z:
        for name in z.namelist():
            if not (name.startswith("ppt/webextensions/webextension") and name.endswith(".xml")):
                continue
            root = ET.fromstring(z.read(name))
            ref = root.find(f"{NS_WE}reference")
            props = {p.get("name"): p.get("value") for p in root.iter(f"{NS_WE}property")}
            if ref is None or "bundle" not in props:
                continue                       # not a texstage object
            value = lambda k: json.loads(props[k]) if k in props else None   # noqa: E731
            if value("phase") == "prepare":
                d.first = True                 # (not one of the deck's slides)
            else:
                d.live += 1
            d.addins.add(ref.get("id"))
            for attr, k in (("servers", "server"), ("keys", "key"), ("decks", "deck"), ("bundles", "bundle")):
                if value(k):
                    getattr(d, attr).add(value(k))
            if "texquizBundle" in props:
                d.carries = True
                d.carried = max(d.carried, len(value("texquizBundle") or ""))
    return d


def get(url: str, key: str | None = None, timeout: float = 5):
    headers = {"User-Agent": f"texquiz/{__version__}"} | ({"X-Texquiz-Key": key} if key else {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.status, r.read()


def in_this_network(url: str) -> bool:
    """An address of this machine or the local network: only a phone in the room can try it."""
    host = urlsplit(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False                                   # a name on the internet
    return ip.is_private or ip.is_loopback or ip.is_link_local


def check(pptx: Path, say=print, registry_key: str | None = None, office_js: str | None = OFFICE_JS) -> bool:
    """Prints the checks; True if the deck is ready."""
    from texstage import addin
    from texstage.build.powerpoint import addin_id

    ok = True

    def line(good: bool | None, text: str):
        nonlocal ok
        ok &= good is not False
        say(f"  {'ok     ' if good else 'PROBLEM' if good is False else '       '}  {text}")

    try:
        d = read_deck(pptx)
    except (OSError, zipfile.BadZipFile, ET.ParseError) as err:
        say(f"{pptx}: cannot read it ({err})")
        return False
    static = pptx.with_name(pptx.stem + "-static.pptx")
    if d.live == 0:
        say(f"{pptx}: no live slides - a deck without the quiz, it plays anywhere")
        return True
    if len(d.servers) != 1 or len(d.addins) != 1 or len(d.bundles) != 1:
        say(f"{pptx}: its live slides disagree (servers {sorted(d.servers)}, bundles {sorted(d.bundles)}) - "
            f"build it again")
        return False
    server, bundle, aid = next(iter(d.servers)), next(iter(d.bundles)), next(iter(d.addins))
    key = next(iter(d.keys), None)
    say(f"{pptx.name}: {d.live} live slides, deck {next(iter(d.decks), '?')}, quiz server {server}")
    if not d.first:
        line(None, "built before 2026-10-10: the join slide prepares the quiz slides when it is first shown - "
                   "build it again for a first slide that does it when the slideshow starts")
    if aid != addin_id(server):
        line(False, f"the slides reference another add-in than {server}'s (an older build?) - "
                    f"texstage retarget {pptx.name} --server {server}")
        aid = addin_id(server)               # what retarget makes them reference

    # 1. the add-in on this PC
    if sys.platform == "win32":
        installed = addin.installed(registry_key) if registry_key else addin.installed()
        name = server.split("://", 1)[1]
        if aid in installed and Path(installed[aid]).is_file():
            line(True, f'add-in "texstage ({name})" registered on this PC')
        else:
            line(False, f'add-in "texstage ({name})" not registered on this PC - the live slides would be '
                        f"blank: texstage addin install --url {server}, then restart PowerPoint")
    else:
        line(None, "add-in registration: only checked on Windows")

    # 2. the server
    try:
        _, body = get(f"{server}/api/status")
        status = json.loads(body)
        line(True, f"the server answers (texstage {status.get('version', '?')})")
    except (urllib.error.URLError, OSError, ValueError) as err:
        reason = getattr(err, "reason", err)
        local = any(h in server for h in ("localhost", "127.0.0.1", "[::1]"))
        line(False, f"the server does not answer ({reason}) - "
                    + ("start it: python tools/scripts/texstage-serve.py (or texstage serve)" if local
                       else "is the hosted server up, and this PC online?"))
        status = None

    # 3. the key and 4. the deck
    if status is not None:
        if not key:
            line(False, "the deck carries no presenter key - the slides would ask for it: build it with --key")
        else:
            try:
                _, body = get(f"{server}/api/decks", key)
                line(True, "the server accepts the deck's presenter key")
                there = {d_["bundle"]: d_ for d_ in json.loads(body)}
                publish = f"texstage publish <its .bundle folder> --url {server}"
                if bundle in there:
                    line(True, "the server has this deck")
                elif d.carries and d.carried > CARRY_MAX:          # a file built before 2026-10-09
                    line(False, f"the server does not have this deck, and the {d.carried / 1e6:.1f} MB its join slide "
                                f"carries are more than PowerPoint keeps (2 MB) - build it again: the build hands "
                                f"the deck over (or {publish})")
                elif d.carries:
                    line(True, "the server does not have the deck yet - the join slide brings it")
                else:
                    line(False, "the server does not have this deck - its build hands it over: the quiz server on "
                                "the laptop that built it finds it by itself (build it again there, if that was "
                                f"before 2026-10-09), any other gets it when the deck is built for it; or {publish}")
            except urllib.error.HTTPError as err:
                line(False, "the server does not accept the deck's presenter key - build or retarget the deck "
                            "again (the server's key changed?)" if err.code == 403 else f"the server: {err}")
            except (urllib.error.URLError, OSError, ValueError) as err:
                line(False, f"the server: {getattr(err, 'reason', err)}")
        join = status.get("join")
        if join:
            from texstage.build.powerpoint import origin
            from texstage.server.tunnel import reaches
            try:
                there = origin(join)
            except ValueError:
                there = None
            if there is None or there == origin(server) or in_this_network(there) or not status.get("instance"):
                line(None, f"phones join at {join} - open it on a phone in the room to be sure")
            else:                                      # a tunnel, or a proxy: try it as the phones will
                good, why = reaches(there, status["instance"], get=lambda url: get(url, timeout=10)[1])
                line(good, f"phones reach the server at {join} (checked over the internet)" if good else
                           f"phones would join at {join}, but it does not reach this server: {why} - "
                           f"start the server with its tunnel (texstage serve --tunnel <name>)")

    # 5. Office.js
    if office_js:
        try:
            get(office_js, timeout=8)
            line(True, "Office.js reachable (PowerPoint needs it for the live slides)")
        except (urllib.error.URLError, OSError) as err:
            line(False, f"Office.js not reachable ({getattr(err, 'reason', err)}) - this PC needs the internet")

    if ok:
        line(None, "before the class watches: start the slideshow and show the join slide once - it "
                   "prepares the live slides, so that they do not flicker in the lecture")
        say("ready")
    else:
        say("not ready" + (f" - without the quiz, present {static.name}" if static.exists() else ""))
    return ok
