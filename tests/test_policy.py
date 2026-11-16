# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The pages' Content-Security-Policy (server/policy.py; F2 package 10): every page has its own, as written
out here - the phone's loading the least, the windows' with the video platforms' players, the presenter's
compiling F1's engines, the add-in's with Office.js -; the pages' files under /static have their page's,
every script one for when it runs as a worker (a kind's file reaches nothing then); and what a policy
refuses reaches the server's log, once and a few a minute, whatever a report holds. The policies fit what
the pages' code does (their imports: WebAssembly, workers, the players' addresses), and the pages and
texstage's scripts hold nothing a policy refuses: no inline script or handler, no javascript: address, no
eval."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from texstage.server import policy
from texstage.server.app import HINTS_POLICY, ServerConfig, create_app

WEB = Path(policy.__file__).resolve().parents[1] / "web"
PAGES = {"/play": "play", "/stage": "stage", "/stage/projector": "projector", "/host": "host", "/addin/": "addin"}
REPORT = ["/api/csp-report"]
COMMON = {"default-src": ["'self'"], "style-src": ["'self'", "'unsafe-inline'"], "img-src": ["'self'", "data:", "blob:"],
          "font-src": ["'self'", "data:"], "object-src": ["'none'"], "base-uri": ["'none'"], "form-action": ["'self'"],
          "report-uri": REPORT}
SOCKET = ["ws://testserver", "wss://testserver"]
WINDOW = {"connect-src": ["'self'", "https://vimeo.com", *SOCKET], "media-src": ["'self'", "blob:", "https:", "http:"],
          "worker-src": ["'self'"], "frame-src": ["https://www.youtube-nocookie.com", "https://player.vimeo.com"],
          "frame-ancestors": ["'self'"]}
EXPECTED = {           # (written out: a source added or dropped anywhere is a change these tests see)
    "play": {**COMMON, "script-src": ["'self'"], "connect-src": ["'self'", *SOCKET], "media-src": ["'self'", "blob:"],
             "worker-src": ["'self'"], "frame-src": ["'none'"]},
    "stage": {**COMMON, **WINDOW,
              "script-src": ["'self'", "'wasm-unsafe-eval'", "https://www.youtube.com", "https://player.vimeo.com"]},
    "projector": {**COMMON, **WINDOW, "script-src": ["'self'", "https://www.youtube.com", "https://player.vimeo.com"]},
    "host": {**COMMON, "script-src": ["'self'"], "connect-src": ["'self'", *SOCKET], "media-src": ["'self'", "blob:"],
             "worker-src": ["'none'"], "frame-src": ["'none'"], "frame-ancestors": ["'self'"]},
    "addin": {**COMMON, "script-src": ["'self'", "https://appsforoffice.microsoft.com"], "connect-src": ["'self'", *SOCKET],
              "media-src": ["'self'", "blob:"], "worker-src": ["'none'"], "frame-src": ["'none'"]},
}
SCRIPT = {"default-src": ["'none'"], "script-src": ["'self'", "'wasm-unsafe-eval'"], "connect-src": ["'self'"],
          "worker-src": ["'none'"], "report-uri": REPORT}
NOTHING = {"default-src": ["'none'"], "script-src": ["'self'"], "worker-src": ["'none'"], "report-uri": REPORT}


def directives(header: str) -> dict[str, list[str]]:
    return {d.split()[0]: d.split()[1:] for d in (p.strip() for p in header.split(";")) if d}


@pytest.fixture
def client(tmp_path):
    (tmp_path / "bundles").mkdir()
    config = ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                          presenter_key="k" * 24)
    with TestClient(create_app(config)) as c:
        yield c


def test_every_page_has_its_policy(client):
    for path, page in PAGES.items():
        r = client.get(path)
        assert r.status_code == 200, path
        assert directives(r.headers["content-security-policy"]) == EXPECTED[page], page
        assert r.headers["content-security-policy"] == policy.policy(page, "testserver")
    assert policy.policy("host").count("report-uri") == 1


def test_the_pages_files_under_static_have_their_pages_policies_and_every_script_one_as_a_worker(client):
    for file, page in policy.FILES.items():
        r = client.get(f"/static/{file}")
        assert r.status_code == 200 and directives(r.headers["content-security-policy"]) == EXPECTED[page], file
    for script in ("play/play.js", "stage/presenter.js", "vendor/pdfjs/pdf.worker.min.mjs", "vendor/katex/katex.min.js"):
        assert directives(client.get(f"/static/{script}").headers["content-security-policy"]) == SCRIPT, script
    assert client.get("/static/play/hint-worker.js").headers["content-security-policy"] == HINTS_POLICY == policy.KIND
    assert directives(HINTS_POLICY) == NOTHING
    assert directives(client.get("/static/stage/evaluator-worker.js").headers["content-security-policy"]) == \
        {"connect-src": ["'none'"], "worker-src": ["'none'"], "report-uri": REPORT}
    assert "content-security-policy" not in client.get("/static/shared/live.css").headers
    assert directives(policy.of_file("vendor/unknown.html")) == {
        "default-src": ["'none'"], "base-uri": ["'none'"], "form-action": ["'none'"], "frame-ancestors": ["'none'"],
        "report-uri": REPORT}


def test_a_kinds_file_reaches_nothing_as_a_worker(client):
    from texstage.server import kindfiles
    found = kindfiles.Kinds().by_name.get("choice")
    if not found or not found.phone:
        pytest.skip("texstage's own kinds are not installed (pip install -e .)")
    r = client.get(f"/kinds/{found.hash}/{found.phone[0]}")
    assert r.status_code == 200 and directives(r.headers["content-security-policy"]) == NOTHING


def test_the_websocket_is_named_by_the_requests_host_where_a_source_can_name_it():
    assert "ws://quiz.example.org:8470 wss://quiz.example.org:8470" in policy.policy("play", "quiz.example.org:8470")
    assert "ws://127.0.0.1:8470 " in policy.policy("host", "127.0.0.1:8470")
    assert "ws://quiz.test wss://quiz.test" in policy.of_file("stage/index.html", "quiz.test")
    for odd in ("[::1]:8470", "evil.test; script-src *", "a b", "", None, "-x.test", "x..test", "x.test:123456",
                "*", "*.test", "x.test.", "ws://x.test"):
        header = policy.policy("play", odd)
        assert directives(header)["connect-src"] == ["'self'"], odd
        assert "*" not in header and header.count(";") == len(directives(header)) - 1


def report(page="http://quiz.test/play?pin=1", directive="script-src-elem", blocked="https://evil.test/x.js", **more):
    return json.dumps({"csp-report": {"document-uri": page, "effective-directive": directive, "blocked-uri": blocked,
                                      **more}}).encode()


def test_a_refusal_is_logged_once_and_a_few_a_minute_at_most():
    now = [0.0]
    reports = policy.Reports(most=2, window=60, clock=lambda: now[0])
    assert reports.take(report(**{"source-file": "http://quiz.test/static/play/play.js?v=1#x", "line-number": 12})) == \
        "the page /play refused script-src-elem https://evil.test (play/play.js:12)"
    assert reports.take(report(blocked="https://evil.test/y.js")) is None        # the same origin: said already
    assert reports.take(report(page="http://quiz.test/stage")) == "the page /stage refused script-src-elem https://evil.test"
    assert reports.take(report(directive="connect-src")) == \
        "more than 2 new refusals in 60 s: the next are counted, not logged"   # (the first one counted says so)
    assert reports.take(report(directive="font-src")) is None
    now[0] = 61.0
    assert reports.take(report(directive="img-src")) == \
        "the page /play refused img-src https://evil.test - and 2 more reports since, not logged"
    assert reports.take(report(directive="connect-src")) == "the page /play refused connect-src https://evil.test"
    reports = policy.Reports()                                                  # (what a line says)
    assert reports.take(report(page="http://quiz.test/host", directive="script-src-attr\nforged",
                               blocked="inline\x1b[31m\u202eevil")) == "the page /host refused script-src-attr inline [31m evil"
    assert reports.take(report(page="http://quiz.test/play?pin=123456", directive="script-src-attr", blocked="inline",
                               **{"source-file": "http://quiz.test/play?pin=123456", "line-number": 3})) == \
        "the page /play refused script-src-attr inline (/play:3)"                # (no PIN in the log)
    assert reports.take(report(blocked="https://user:secret@evil.test:8443/x", directive="frame-src")) == \
        "the page /play refused frame-src https://evil.test:8443"
    assert reports.take(report(directive="media-src", **{"source-file": "http://quiz.test/x.js", "line-number": True})) \
        == "the page /play refused media-src https://evil.test"                 # (a line number is a number)


def test_a_report_that_cannot_be_read_is_none():
    reports = policy.Reports()
    for odd in (b"", b"[]", b"{}", b'{"csp-report": 3}', b"\xff\xfe", b'{"csp-report": {}}' * 2, b'{"csp-report": {}}',
                b"[" * 4000 + b"]" * 4000, b"{" * 3990, report(page="http://[x"), report(blocked="http://[x/a"),
                report(blocked="http://evil.test:99999/"), report(page="http://quiz.test/play", directive=""),
                report(page="", directive="img-src"), json.dumps({"csp-report": {"document-uri": ["x"]}}).encode(),
                report(page="http://quiz.test/" + "x" * policy.REPORT_BYTES)):
        assert reports.take(odd) is None, odd[:80]
    assert reports.take(report()) == "the page /play refused script-src-elem https://evil.test"   # (still taking)


def test_a_kinds_file_is_named_by_its_kinds_and_a_worker_as_one():
    reports = policy.Reports(kinds=lambda digest: {"0123abcd": "choice, number, text"}.get(digest, ""))
    kind = "http://quiz.test/kinds/0123abcd/web/input.js"
    assert reports.take(report(**{"source-file": kind, "line-number": 10})) == \
        "the page /play refused script-src-elem https://evil.test (choice, number, text: web/input.js:10)"
    assert reports.take(report(page=kind, directive="connect-src")) == \
        "the worker choice, number, text: web/input.js refused connect-src https://evil.test"
    assert reports.take(report(page="http://quiz.test/kinds/ffff/web/x.mjs", directive="connect-src")) == \
        "the worker a kind: web/x.mjs refused connect-src https://evil.test"
    assert reports.take(report(page="http://quiz.test/static/play/hint-worker.js", directive="script-src-elem")) == \
        "the worker play/hint-worker.js refused script-src-elem https://evil.test"


def test_the_server_logs_what_a_page_reports(client, caplog):
    with caplog.at_level(logging.WARNING, logger="texstage.server"):
        for _ in range(3):
            r = client.post(policy.REPORTS, content=report(), headers={"Content-Type": "application/csp-report"})
            assert r.status_code == 204
        for odd in (b"no report", report(page="http://[x"), b"[" * 4000 + b"]" * 4000,
                    report(page="http://quiz.test/host", **{"padding": "x" * policy.REPORT_BYTES})):
            assert client.post(policy.REPORTS, content=odd).status_code == 204
    said = [rec.getMessage() for rec in caplog.records if rec.getMessage().startswith("policy:")]
    assert said == ["policy: the page /play refused script-src-elem https://evil.test"]


# --- the policies fit what the pages' code does, as their imports say ------------------------------------

IMPORT = re.compile(r"""\bfrom\s*["']([^"']+)["']|\bimport\s*\(?\s*["']([^"']+)["']""")
SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
COMPILES = re.compile(r"WebAssembly\.(?:compile|compileStreaming|instantiate|instantiateStreaming)\s*\(|new\s+WebAssembly\.Module\s*\(")


def imported(page: str) -> dict[Path, str]:
    """The scripts a page runs: those its HTML names on the server, and what they import, statically."""
    html = (WEB / next(f for f, p in policy.FILES.items() if p == page)).read_text(encoding="utf-8")
    todo = [WEB / m[1][len("/static/"):] for m in (re.search(r'\bsrc="([^"]+)"', a) for a in SCRIPT_TAG.findall(html))
            if m and m[1].startswith("/static/")]
    found: dict[Path, str] = {}
    while todo:
        path = todo.pop().resolve()
        if path in found or not path.is_file():
            continue
        found[path] = path.read_text(encoding="utf-8")
        for m in IMPORT.finditer(found[path]):
            spec = m[1] or m[2]
            if spec.startswith("/static/"):
                todo.append(WEB / spec[len("/static/"):])
            elif spec.startswith("."):
                todo.append(path.parent / spec)
    return found


def test_the_policies_fit_what_the_pages_code_does():
    video = (WEB / "stage" / "video.js").read_text(encoding="utf-8")
    addresses = {m[1] for m in re.finditer(r"""["'`](https://[a-z0-9.-]+)""", video)}
    assert addresses == {*policy.PLAYERS, *policy.FRAMES, policy.OEMBED}, addresses
    for page in ("play", "stage", "projector", "host", "addin"):
        scripts = imported(page)
        code = "\n".join(scripts.values())
        names = {p.relative_to(WEB).as_posix() for p in scripts}
        sources = directives(policy.policy(page))
        assert ("'wasm-unsafe-eval'" in sources["script-src"]) == bool(COMPILES.search(code)), page
        assert sources["worker-src"] == (["'self'"] if "new Worker(" in code else ["'none'"]), page
        plays = "stage/video.js" in names
        assert set(policy.PLAYERS) <= set(sources["script-src"]) if plays else len(sources["script-src"]) <= 2, page
        assert sources["frame-src"] == (list(policy.FRAMES) if plays else ["'none'"]), page
        assert (policy.OEMBED in sources["connect-src"]) == plays, page
    assert "stage/evaluator.js" in {p.relative_to(WEB).as_posix() for p in imported("stage")}
    assert "kinds.js" in {p.relative_to(WEB).as_posix() for p in imported("play")}


# --- the pages and texstage's scripts hold nothing a policy refuses --------------------------------------

EVAL = re.compile(r"(?<![\w.$])eval\s*\((?![^()\n]*\)\s*\{)"       # a call of eval, not a method named so
                  r"|(?<![\w.$])(?:new\s+)?Function\s*\(|\bset(?:Timeout|Interval)\s*\(\s*[\"'`]|javascript:", re.IGNORECASE)
HANDLER = re.compile(r"<[a-z][^<>]*\son[a-z]+\s*=", re.IGNORECASE)    # an inline handler written as HTML


def test_the_pages_and_texstages_scripts_hold_nothing_their_policies_refuse():
    assert all(EVAL.search(s) for s in ("eval(x)", "new Function('a')", "Function('return this')()",
                                        "setTimeout('go()', 1)", "a.href = 'javascript:x'"))
    assert not any(EVAL.search(s) for s in ("window.eval(x)", "async eval(text, a = 1) {", "setTimeout(go, 1)",
                                            "class Function {", "isFunction(x)"))
    for file, page in policy.FILES.items():
        html = (WEB / file).read_text(encoding="utf-8")
        allowed = [a for a in directives(policy.policy(page))["script-src"] if a.startswith("https://")]
        for attributes in SCRIPT_TAG.findall(html):
            src = re.search(r'\bsrc="([^"]+)"', attributes)
            assert src, f"{file}: an inline script"
            assert src[1].startswith("/") and not src[1].startswith("//") or \
                any(src[1].startswith(a + "/") for a in allowed), f"{file}: {src[1]}"
        assert not HANDLER.search(html) and "javascript:" not in html.lower(), file
    scripts = [p for p in WEB.rglob("*.js") if "vendor" not in p.relative_to(WEB).parts]
    assert len(scripts) > 30
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        for pattern in (EVAL, HANDLER):
            assert not pattern.search(text), f"{path.relative_to(WEB)}: {pattern.search(text)[0]}"
