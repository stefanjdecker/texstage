# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A Cloudflare tunnel for the laptop's server (server/tunnel.py, texstage serve --tunnel):
the address from cloudflared's config, the remembered choice, cloudflared's lifetime, the
check that the phones' address leads to this very server."""
from __future__ import annotations

import io
import json
import sys
import urllib.error

import pytest

from fake_bundle import make_bundle
from test_publish import running
from test_server import config
from texstage.cli import main
from texstage.server import tunnel as cf
from texstage.server.app import create_app

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]       # stands in for cloudflared
CONFIG = """\
tunnel: quiz-tunnel
credentials-file: C:\\Users\\someone\\.cloudflared\\0000.json

ingress:
  - hostname: "*.example.org"
    service: http://localhost:8470
  - hostname: other.example.org
    service: http://localhost:9000
  - hostname: quiz.example.org
    service: http://localhost:8470   # the quiz server
  - service: http_status:404
"""


@pytest.fixture
def cloudflared(tmp_path, monkeypatch):
    """cloudflared "installed", its config in a folder of the test's."""
    folder = tmp_path / ".cloudflared"
    folder.mkdir()
    monkeypatch.setattr(cf, "CONFIG_DIRS", [str(folder)])
    monkeypatch.setattr(cf, "find_cloudflared", lambda: "cloudflared")
    monkeypatch.delenv("TUNNEL_TRANSPORT_PROTOCOL", raising=False)
    return folder


def test_the_address_comes_from_cloudflareds_config(cloudflared):
    (cloudflared / "config.yml").write_text(CONFIG, encoding="utf-8")
    p = cf.plan("quiz-tunnel", 8470)
    assert p.public_url == "https://quiz.example.org"                  # not the wildcard, not port 9000
    assert p.command == ["cloudflared", "tunnel", "--no-autoupdate", "--protocol", "http2",
                         "--config", str(cloudflared / "config.yml"), "run", "quiz-tunnel"]
    assert cf.plan("quiz-tunnel", 8470, "https://given.example.org/").public_url == "https://given.example.org"
    with pytest.raises(cf.TunnelError, match="add an ingress rule") as err:
        cf.plan("quiz-tunnel", 8471)
    assert "service: http://localhost:8471" in str(err.value)
    rules = [{"hostname": "a.test", "service": "http://localhost:x"}, {"hostname": "b.test", "service": "http://[::1]:8470"}]
    assert cf.hostname_for(rules, 8470) == "b.test"
    assert cf.hostname_for([{"hostname": "c.test", "service": "http://192.168.1.2:8470"}], 8470) is None


def test_a_tunnel_without_ingress_rules(cloudflared):
    with pytest.raises(cf.TunnelError, match="--public-url"):          # no config: the address is unknown
        cf.plan("quiz-tunnel", 8470)
    p = cf.plan("quiz-tunnel", 8470, "https://quiz.example.org")
    assert p.command[-4:] == ["run", "--url", "http://127.0.0.1:8470", "quiz-tunnel"]
    (cloudflared / "config.yaml").write_text("tunnel: quiz-tunnel\n", encoding="utf-8")
    assert cf.plan("quiz-tunnel", 8470, "https://quiz.example.org").command[-2] == "http://127.0.0.1:8470"
    (cloudflared / "config.yaml").write_text("ingress: [\n", encoding="utf-8")
    with pytest.raises(cf.TunnelError, match="cannot read"):
        cf.plan("quiz-tunnel", 8470)


def test_http2_unless_the_lecturer_chose_a_protocol(cloudflared, monkeypatch):
    """QUIC needs UDP out to port 7844, which university networks often block: HTTP/2 over TCP,
    unless cloudflared's config or its environment variable says otherwise."""
    assert cf.plan("quiz-tunnel", 8470, "https://quiz.example.org").command[3:5] == ["--protocol", "http2"]
    monkeypatch.setenv("TUNNEL_TRANSPORT_PROTOCOL", "quic")
    assert "--protocol" not in cf.plan("quiz-tunnel", 8470, "https://quiz.example.org").command
    monkeypatch.delenv("TUNNEL_TRANSPORT_PROTOCOL")
    (cloudflared / "config.yml").write_text("protocol: quic\n" + CONFIG, encoding="utf-8")
    assert "--protocol" not in cf.plan("quiz-tunnel", 8470).command


def test_cloudflared_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda name: None)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    with pytest.raises(cf.TunnelError, match="not installed"):
        cf.plan("quiz-tunnel", 8470)


def test_remembered(tmp_path):
    data = tmp_path / "data"
    assert cf.remembered(data) == (None, None)
    cf.remember(data, "quiz-tunnel")
    assert cf.remembered(data) == ("quiz-tunnel", None)
    cf.remember(data, "quiz-tunnel", "https://quiz.example.org")
    assert cf.remembered(data) == ("quiz-tunnel", "https://quiz.example.org")
    cf.remember(data, None)
    assert cf.remembered(data) == (None, None) and not (data / cf.REMEMBERED).exists()


def test_reaches():
    def answering(status=None, error=None):
        def get(url):
            assert url == "https://quiz.example.org/api/status"
            if error:
                raise error
            return json.dumps(status).encode()
        return get

    url, me = "https://quiz.example.org", "abc"
    assert cf.reaches(url, me, answering({"server": "texquiz", "instance": "abc"})) == (True, "")
    assert cf.reaches(url, me, answering({"server": "texquiz", "instance": "xyz"}))[1] == "it leads to another texstage server"
    assert "something else" in cf.reaches(url, me, answering(["not", "texquiz"]))[1]
    down = urllib.error.HTTPError(url, 530, "", {}, io.BytesIO())
    assert cf.reaches(url, me, answering(error=down)) == (False, "the tunnel is not running")
    unreachable = urllib.error.HTTPError(url, 502, "", {}, io.BytesIO())
    assert cf.reaches(url, me, answering(error=unreachable)) == (False, "cloudflared cannot reach this server")
    assert cf.reaches(url, me, answering(error=urllib.error.URLError("no DNS"))) == (False, "no DNS")


def test_cloudflared_runs_with_the_server(tmp_path):
    (tmp_path / "srv").mkdir()
    app = create_app(config(tmp_path / "srv"))
    with running(app) as url:
        t = cf.Tunnel(cf.Plan("quiz-tunnel", SLEEPER, url), tmp_path / "data" / "cloudflared.log")
        try:
            said: list[str] = []
            assert t.watch(app.state.server.instance, said.append, timeout=10)
            assert said == [f"  the tunnel works: {url} reaches this server (checked over the internet)"]
            assert not t.watch("another-server", said.append, timeout=0.5)
            assert "does not reach this server: it leads to another texstage server" in said[-1]
        finally:
            t.stop()
        assert t.proc.poll() is not None
    t = cf.Tunnel(cf.Plan("quiz-tunnel", [sys.executable, "-c", "print('failed to connect')"], url),
                  tmp_path / "cloudflared.log")
    said = []
    assert not t.watch("x", said.append, timeout=10)
    assert said == [f"  PROBLEM: cloudflared stopped: failed to connect (log: {tmp_path / 'cloudflared.log'})"]


@pytest.mark.skipif(sys.platform != "win32", reason="a Windows job object")
def test_cloudflared_ends_with_the_servers_process(tmp_path):
    """However the server's process ends (killed, its window closed), its job object closes
    and takes cloudflared along - here: closing the job's handle, as the end of the process does."""
    import ctypes
    from ctypes import wintypes
    t = cf.Tunnel(cf.Plan("quiz-tunnel", SLEEPER, "https://quiz.example.org"), tmp_path / "cloudflared.log")
    try:
        assert t.job and t.proc.poll() is None
        close = ctypes.WinDLL("kernel32").CloseHandle
        close.argtypes = [wintypes.HANDLE]
        assert close(t.job)
        assert t.proc.wait(10) is not None
    finally:
        t.stop()


def test_serve_with_a_tunnel(cloudflared, tmp_path, monkeypatch, capsys):
    """texstage serve --tunnel: cloudflared runs with the server, the server listens on this
    machine only, phones join at the tunnel's address; the choice is remembered."""
    from texstage.server import app as app_module
    (cloudflared / "config.yml").write_text(CONFIG, encoding="utf-8")
    make_bundle(tmp_path / "bundles")
    served, tunnels = [], []

    class FakeTunnel:
        def __init__(self, plan, log):
            self.plan, self.log, self.stopped = plan, log, False
            tunnels.append(self)

        def watch(self, instance):
            pass

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(cf, "Tunnel", FakeTunnel)
    monkeypatch.setattr(app_module, "listen", lambda host, port: served.append(host) or [])
    monkeypatch.setattr("texstage.cli.run_server", lambda server, sockets: None)
    data = tmp_path / "data"
    serve = ["serve", str(tmp_path / "bundles"), "--data", str(data), "--port", "8470"]

    assert main([*serve, "--tunnel", "quiz-tunnel"]) == 0
    out = capsys.readouterr().out
    assert "phones join at https://quiz.example.org/play" in out
    assert "through the Cloudflare tunnel quiz-tunnel (remembered for the next start)" in out
    assert served == ["127.0.0.1"] and tunnels[0].stopped                      # ends with the server
    assert tunnels[0].plan.command[-2:] == ["run", "quiz-tunnel"] and tunnels[0].log == data / "cloudflared.log"

    assert main(serve) == 0                                                    # remembered
    out = capsys.readouterr().out
    assert "(remembered - --no-tunnel serves without it)" in out
    key = (data / "presenter-key").read_text(encoding="ascii").strip()         # the start message: not the key
    assert key not in out and f"presenter key: {key[:4]}… (--show-key: all of it)" in out
    assert len(tunnels) == 2 and served[-1] == "127.0.0.1"

    assert main([*serve, "--no-tunnel"]) == 0                                  # forgotten
    out = capsys.readouterr().out
    assert len(tunnels) == 2 and served[-1] == "0.0.0.0" and "phones in the room reach the server" in out
    assert main(serve) == 0 and len(tunnels) == 2

    assert main([*serve, "--tunnel", "quiz-tunnel", "--port", "8471"]) == 2   # no hostname for that port
    assert "add an ingress rule" in capsys.readouterr().err
    assert cf.remembered(data) == (None, None)                                 # a failed start keeps nothing
    assert main([*serve, "--show-key"]) == 0 and f"presenter key: {key} (" in capsys.readouterr().out
