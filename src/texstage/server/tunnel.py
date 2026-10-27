# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A Cloudflare tunnel for the quiz server on a laptop (docs/design.md, section 8): phones join
at the tunnel's address on the internet, while PowerPoint and the host page keep talking to
http://localhost. `texstage serve --tunnel NAME` runs `cloudflared tunnel run NAME` next to the
server and ends it with the server, takes the address from cloudflared's config (the hostname
its ingress rules send to the server's port) and checks over the internet that the address
leads to this very server. The data folder remembers the choice (tunnel.json)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from texstage import SERVER_NAMES, __version__

REMEMBERED = "tunnel.json"
CONFIG_DIRS = ["~/.cloudflared", "~/.cloudflare-warp", "~/cloudflare-warp"]    # where cloudflared looks
if sys.platform != "win32":
    CONFIG_DIRS += ["/etc/cloudflared", "/usr/local/etc/cloudflared"]
LOCAL = {"localhost", "127.0.0.1", "::1"}
WHY = {530: "the tunnel is not running", 502: "cloudflared cannot reach this server"}   # Cloudflare's answers
PROTOCOL = "http2"      # not cloudflared's default QUIC: that needs UDP out to port 7844, which university
                        # networks often block, and cloudflared 2026.9 tries for minutes before it falls back


class TunnelError(Exception):
    pass


def remembered(data: Path) -> tuple[str | None, str | None]:
    """The tunnel the last `--tunnel` named, and the address given with it."""
    try:
        kept = json.loads((data / REMEMBERED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    return (kept.get("tunnel"), kept.get("public_url")) if isinstance(kept, dict) else (None, None)


def remember(data: Path, name: str | None, public_url: str | None = None):
    """Keep the tunnel for the next start; None forgets it (--no-tunnel)."""
    path = data / REMEMBERED
    if name is None:
        path.unlink(missing_ok=True)
        return
    data.mkdir(parents=True, exist_ok=True)
    kept = {"tunnel": name} | ({"public_url": public_url} if public_url else {})
    path.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")


def find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found or sys.platform != "win32":
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and (Path(base) / "cloudflared" / "cloudflared.exe").is_file():
            return str(Path(base) / "cloudflared" / "cloudflared.exe")
    return None


def config_file() -> Path | None:
    """cloudflared's config, found the way cloudflared finds it."""
    for folder in CONFIG_DIRS:
        for name in ("config.yml", "config.yaml"):
            path = Path(folder).expanduser() / name
            if path.is_file():
                return path
    return None


def settings(config: Path) -> dict:
    import yaml                                         # comes with uvicorn[standard]
    try:
        doc = yaml.safe_load(config.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise TunnelError(f"cannot read cloudflared's config {config}: {err}") from err
    return doc if isinstance(doc, dict) else {}


def ingress(doc: dict) -> list[dict]:
    rules = doc.get("ingress")
    return [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []


def hostname_for(rules: list[dict], port: int) -> str | None:
    """The first hostname the ingress rules send to a server on this machine at `port`."""
    for rule in rules:
        host, service = rule.get("hostname"), rule.get("service")
        if not isinstance(host, str) or "*" in host or not isinstance(service, str):
            continue
        u = urlsplit(service)
        try:
            if u.scheme in ("http", "https") and (u.hostname or "") in LOCAL and u.port == port:
                return host
        except ValueError:                              # a port that is not a number
            continue
    return None


@dataclass
class Plan:
    name: str
    command: list[str]
    public_url: str


def plan(name: str, port: int, public_url: str | None = None) -> Plan:
    """How to run the tunnel `name` for the server at `port`, and the phones' address."""
    exe = find_cloudflared()
    if exe is None:
        raise TunnelError("cloudflared is not installed (Windows: winget install --id Cloudflare.cloudflared)")
    config = config_file()
    doc = settings(config) if config else {}
    rules = ingress(doc)
    command = [exe, "tunnel", "--no-autoupdate"]
    if "protocol" not in doc and not os.environ.get("TUNNEL_TRANSPORT_PROTOCOL"):    # the lecturer's own wins
        command += ["--protocol", PROTOCOL]
    if rules:                                           # cloudflared routes by its ingress rules
        host = hostname_for(rules, port)
        if host is None:
            raise TunnelError(f"{config} sends none of its hostnames to this server - add an ingress rule "
                              f"(before the last one):\n  - hostname: quiz.example.org\n"
                              f"    service: http://localhost:{port}")
        return Plan(name, [*command, "--config", str(config), "run", name],
                    (public_url or f"https://{host}").rstrip("/"))
    if not public_url:
        raise TunnelError(f"which address does it have? Give it once: --tunnel {name} --public-url "
                          f"https://<its hostname>")
    return Plan(name, [*command, "run", "--url", f"http://127.0.0.1:{port}", name], public_url.rstrip("/"))


def fetch(url: str, timeout: float = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"texstage/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def reaches(public_url: str, instance: str, get: Callable[[str], bytes] = fetch) -> tuple[bool, str]:
    """Does `public_url` lead to the server `instance` (its /api/status says so)? If not: why."""
    try:
        status = json.loads(get(f"{public_url}/api/status"))
    except urllib.error.HTTPError as err:
        return False, WHY.get(err.code, f"HTTP {err.code}")
    except (urllib.error.URLError, OSError, ValueError) as err:
        return False, str(getattr(err, "reason", err))
    if not isinstance(status, dict) or status.get("server") not in SERVER_NAMES:
        return False, "it leads to something else than a texstage server"
    if status.get("instance") != instance:
        return False, "it leads to another texstage server"
    return True, ""


class Tunnel:
    """cloudflared, running as long as the server does."""

    def __init__(self, plan: Plan, log: Path):
        self.plan, self.log = plan, log
        log.parent.mkdir(parents=True, exist_ok=True)
        detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
                  else {"start_new_session": True})    # Ctrl+C stops the server first, then the tunnel
        with log.open("w", encoding="utf-8") as out:
            self.proc = subprocess.Popen(plan.command, stdin=subprocess.DEVNULL, stdout=out,
                                         stderr=subprocess.STDOUT, **detach)
        self.job = end_with_this_process(self.proc)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def last_line(self) -> str:
        try:
            lines = [ln.strip() for ln in self.log.read_text(encoding="utf-8", errors="replace").splitlines()]
        except OSError:
            return ""
        return next((ln for ln in reversed(lines) if ln), "")

    def watch(self, instance: str, say: Callable[[str], None] = lambda s: print(s, flush=True),
              timeout: float = 90) -> bool:
        """Waits until the phones' address leads to this server, then says so - or why not."""
        url, reason = self.plan.public_url, "no answer"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                say(f"  PROBLEM: cloudflared stopped: {self.last_line()} (log: {self.log})")
                return False
            ok, reason = reaches(url, instance)
            if ok:
                say(f"  the tunnel works: {url} reaches this server (checked over the internet)")
                return True
            time.sleep(2)
        say(f"  PROBLEM: {url} does not reach this server: {reason} (cloudflared's log: {self.log})")
        return False


def end_with_this_process(proc: subprocess.Popen):
    """Windows: a job object that ends cloudflared when this process ends, however it ends
    (killed, its window closed) - no tunnel outlives its server. None elsewhere, or if Windows
    refuses; then stop() ends it."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):                      # JOBOBJECT_BASIC_LIMIT_INFORMATION
        _fields_ = [("user_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                    ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t), ("processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):                   # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                    ("peak_job", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x2000                           # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (job and k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
            and k32.AssignProcessToJobObject(job, int(proc._handle))):
        return None
    return job                                          # open until this process ends
