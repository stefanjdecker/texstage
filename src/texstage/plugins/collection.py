# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Optional discovery catalog. No network calls during build, serve or discovery."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
from email.parser import BytesParser
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import urllib.parse
import urllib.request
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from . import PluginError
from .manifest import QUALIFIED, canonical, digest, load_manifest, read_json, resource_path
from .policy import write_json


def validate_index(index):
    if not isinstance(index, dict) or set(index) != {"format", "releases"} or index["format"] != 1 or not isinstance(index["releases"], list):
        raise PluginError("unsupported plugin collection index")
    seen = set()
    for r in index["releases"]:
        expected = {"id", "version", "distribution", "plugin_api", "payload", "url", "sha256", "license", "withdrawn"}
        if not isinstance(r, dict) or set(r) != expected or type(r["plugin_api"]) is not int or r["plugin_api"] != 1 or type(r["withdrawn"]) is not bool:
            raise PluginError("invalid catalog release")
        if not all(isinstance(r[k], str) for k in expected - {"plugin_api", "withdrawn"}):
            raise PluginError("invalid catalog string")
        if not QUALIFIED.fullmatch(r["id"]) or r["id"].startswith(("texstage.", "org.texstage.")):
            raise PluginError("invalid catalog provider ID")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", r["distribution"]):
            raise PluginError("invalid catalog distribution")
        try:
            if str(Version(r["version"])) != r["version"]:
                raise InvalidVersion(r["version"])
        except InvalidVersion as exc:
            raise PluginError("invalid catalog version") from exc
        if (r["id"], r["version"]) in seen: raise PluginError("duplicate catalog release")
        seen.add((r["id"], r["version"]))
        if any(not re.fullmatch(r"[a-f0-9]{64}", r[k]) for k in ("sha256", "payload")):
            raise PluginError("invalid catalog digest")
        url = urllib.parse.urlsplit(r["url"])
        if url.scheme != "https" or not url.hostname or url.username or url.fragment or not url.path.endswith("-py3-none-any.whl"):
            raise PluginError("catalog artifacts must be portable wheels at HTTPS URLs")
    return index


def download(url, *, limit):
    if urllib.parse.urlsplit(url).scheme != "https": raise PluginError("HTTPS is required")
    with urllib.request.urlopen(url, timeout=20) as response:
        if urllib.parse.urlsplit(response.url).scheme != "https": raise PluginError("insecure download redirect")
        raw = response.read(limit + 1)
    if len(raw) > limit: raise PluginError("download exceeds size budget")
    return raw


def update(data, *, url=None, file=None):
    if url:
        if not re.fullmatch(r"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/[a-f0-9]{40}/catalog/index\.json", url):
            raise PluginError("catalog URL must pin a complete GitHub commit SHA")
        raw = download(url, limit=1024 * 1024)
        provenance = url
    else:
        raw = Path(file).read_bytes()
        provenance = "local:" + hashlib.sha256(raw).hexdigest()
    index = validate_index(read_json(raw))
    old_path = Path(data) / "plugin-catalog.json"
    if old_path.exists():
        old = read_json(old_path.read_bytes())["index"]
        by_key = {(r["id"], r["version"]): r for r in index["releases"]}
        for r in old["releases"]:
            newer = by_key.get((r["id"], r["version"]))
            if newer is None or {k:v for k,v in r.items() if k != "withdrawn"} != {k:v for k,v in newer.items() if k != "withdrawn"} \
                    or (r["withdrawn"] and not newer["withdrawn"]):
                raise PluginError("catalog updates must preserve releases; withdrawals cannot be reversed")
    write_json(old_path, {"source": provenance, "index": index})
    return index


def cached(data):
    path = Path(data) / "plugin-catalog.json"
    if not path.exists(): raise PluginError("no cached catalog: use plugins catalog update --url or --file")
    return validate_index(read_json(path.read_bytes())["index"])


def install(data, pin, *, requirements: Path, offline=False):
    try: pid, version = pin.split("==")
    except ValueError: raise PluginError("install requires ID==version") from None
    release = next((r for r in cached(data)["releases"] if (r["id"], r["version"]) == (pid, version)), None)
    if release is None or release["withdrawn"]: raise PluginError("release is missing or withdrawn")
    try: existing = metadata.version(release["distribution"])
    except metadata.PackageNotFoundError: existing = None
    if existing is not None: raise PluginError("distribution already installed; use a new environment for upgrades")
    name = Path(urllib.parse.urlsplit(release["url"]).path).name
    cache = Path(data) / "plugin-wheels" / release["sha256"] / name
    if not cache.exists():
        if offline: raise PluginError("wheel is not cached; offline installation cannot continue")
        raw = download(release["url"], limit=64 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != release["sha256"]: raise PluginError("wheel hash mismatch")
        cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(raw)
    if hashlib.sha256(cache.read_bytes()).hexdigest() != release["sha256"]: raise PluginError("cached wheel hash mismatch")
    with zipfile.ZipFile(cache) as wheel:
        if len(set(wheel.namelist())) != len(wheel.namelist()): raise PluginError("duplicate wheel entries")
        names = [n for n in wheel.namelist() if n.endswith(".dist-info/texstage-plugin.json")]
        if len(names) != 1: raise PluginError("wheel has no unique plugin manifest")
        manifest = load_manifest(wheel.read(names[0]))
        if (manifest["id"], manifest["version"], digest(manifest)) != (pid, version, release["payload"]):
            raise PluginError("wheel disagrees with catalog provider pin")
        prefix = names[0].rsplit("/", 1)[0]
        if wheel.read(prefix + "/WHEEL").decode().count("Tag: py3-none-any") != 1 or \
                "Root-Is-Purelib: true" not in wheel.read(prefix + "/WHEEL").decode():
            raise PluginError("wheel is not portable pure Python")
        inventory = manifest["resources"]
        payload_names = {n for n in wheel.namelist() if not n.endswith("/") and not n.startswith(prefix + "/")}
        if payload_names != set(inventory): raise PluginError("wheel inventory is incomplete")
        for name, spec in inventory.items():
            resource_path(name)
            if name.startswith("texstage/") or any(part.endswith(".data") for part in name.split("/")):
                raise PluginError("plugin wheel cannot overwrite host files or relocate payload")
            info = wheel.getinfo(name)
            if info.file_size != spec["size"] or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise PluginError("invalid wheel resource")
            if hashlib.sha256(wheel.read(name)).hexdigest() != spec["sha256"]:
                raise PluginError("wheel resource digest mismatch")
            if (Path(sysconfig.get_path("purelib")) / name).exists():
                raise PluginError("plugin wheel would overwrite an existing package; use a fresh environment")
        package = BytesParser().parsebytes(wheel.read(prefix + "/METADATA"))
        if canonicalize_name(package["Name"]) != canonicalize_name(release["distribution"]) or package["Version"] != version:
            raise PluginError("wheel distribution identity mismatch")
        for requirement in package.get_all("Requires-Dist", []):
            dep = Requirement(requirement)
            if dep.marker and not dep.marker.evaluate(): continue
            try: installed = metadata.version(dep.name)
            except metadata.PackageNotFoundError: installed = None
            if dep.url or installed is None or installed not in dep.specifier:
                raise PluginError(f"dependency {dep} is not satisfied; prepare a separate environment using its dependency lock")
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text(f"{cache.resolve().as_uri()} --hash=sha256:{release['sha256']}\n", encoding="utf-8")
    # pip only unpacks the verified wheel, never a source package or dependency upgrade.
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", "--require-hashes",
                    "--only-binary=:all:", "-r", str(requirements)], check=True)
    return release
