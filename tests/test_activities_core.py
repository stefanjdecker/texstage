# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The activity framework's content type over WebSockets, without a browser (texstage/server/activities.py;
docs/architecture/activity-framework-plan-f2.md, package 6): a presenter window, a projector window and
phones against a server that runs the core's type - the design's messages (10.4), the step's own part
sent to every phone as one text, an entry acknowledged once it is written, the pool's checks through the
kinds, the lead window, the archive, and a restart."""
from __future__ import annotations

import concurrent.futures as cf
import contextlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
KINDS = ROOT / "kinds"
if not any(KINDS.glob("*/src")):                       # texstage's source archive has its tests, not the kinds
    pytest.skip("the kinds' packages are not here", allow_module_level=True)
for src in sorted(KINDS.glob("*/src")):
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

from test_activity import KEY, RIGHT, WRONG, World, make_activity_bundle, receive  # noqa: E402

from texstage.activities import registry  # noqa: E402
from texstage.activities.store import gid  # noqa: E402
from texstage.server import activities  # noqa: E402
from texstage.server import types as stage_types  # noqa: E402
from texstage.server.app import ServerConfig, create_app  # noqa: E402
from texstage.server.bundles import BundleStore  # noqa: E402
from texstage.server.game import Engine, GameError, Settings  # noqa: E402
from texstage.server.store import Store  # noqa: E402

pytest.importorskip("pyoxigraph")
try:
    registry.kind("sparql-query"), registry.kind("triples")
except LookupError:
    pytest.skip("the kinds are not installed: pip install --no-deps -e kinds/...", allow_module_level=True)


@pytest.fixture(autouse=True)
def f1_again():
    """The type a server runs is the process's (types.py: use): the tests after these have F1's again."""
    SEEN.clear(), ASIDE.clear()                         # (a socket's id may be an earlier test's socket's)
    yield
    stage_types.use("f1")


def config_of(tmp_path) -> ServerConfig:
    return ServerConfig(bundles=[tmp_path / "bundles"], data_dir=tmp_path / "data", public_url="http://quiz.test",
                        presenter_key=KEY, settings=Settings(get_ready_ms=0), activities="core", workers=1,
                        pool={"spare": False})


SEEN: dict[int, set] = {}                               # a socket -> the kinds of message it was sent
ASIDE: dict[int, list] = {}                             # a socket -> what came while an answer was waited for


def recv(ws, t=None, until=None, tries: int = 400):
    """The socket's next message that is as asked for - of what was put aside first, in its order."""
    aside = ASIDE.setdefault(id(ws), [])
    for _ in range(tries):
        m = aside.pop(0) if aside else receive(ws)
        SEEN.setdefault(id(ws), set()).add(m["t"])
        if (t is None or m["t"] == t) and (until is None or until(m)):
            return m
    raise AssertionError(f"no {t} message")


def ask(ws, n: int, t: str, **msg) -> dict:
    """A message and its answer - ok or error. What else comes meanwhile is put aside for the next recv, not
    dropped: a check's outcome is pushed when the pool has it, the answer to its entry is sent once the
    entry is written - either may be first (a run of 8176a03 at GitHub: the push was, and the test waited
    30 s for a state that had come)."""
    ws.send_json({"t": t, "id": n, **msg})
    aside = ASIDE.setdefault(id(ws), [])
    for _ in range(400):
        m = receive(ws)
        SEEN.setdefault(id(ws), set()).add(m["t"])
        if m.get("re") == n and m["t"] in ("ok", "error"):
            return m
        aside.append(m)
    raise AssertionError(f"no answer to {t}")


def picture(ws, n: int, activity: str, until, tries: int = 100) -> dict:
    """The activity's picture, asked for until it is as it is to be: the pool answers when it is done."""
    for i in range(tries):
        pic = ask(ws, 1000 * n + i, "activity.view", activity=activity)["picture"]
        if until(pic):
            return pic
        time.sleep(0.05)
    raise AssertionError(f"the picture never came: {pic}")


def join(stack, client, st, bid: str, names=("Ada", "Bea")):
    """The presenter window says hello; the phones join - closed with the stack, however the test ends."""
    st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "act", "bundle": bid, "id": 1})
    pin = recv(st, "welcome")["pin"]
    tokens = []
    phones = [stack.enter_context(client.websocket_connect("/ws")) for _ in names]
    for p, name in zip(phones, names):
        p.send_json({"t": "join", "pin": pin, "nickname": name, "id": "j"})
        tokens.append(recv(p, "welcome")["token"])
    return phones, tokens


def test_a_crowd_graph_over_websockets(tmp_path):
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    with TestClient(create_app(config_of(tmp_path))) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as dp, client.websocket_connect("/ws") as st2, \
            contextlib.ExitStack() as stack:
        assert stage_types.using == "core"
        (p1, p2), _ = join(stack, client, st, bid)
        for n, (w, role) in enumerate(((dp, "display"), (st2, "stage"))):
            w.send_json({"t": "hello", "role": role, "key": KEY, "deck": "act", "bundle": bid, "id": n})
            recv(w, "welcome")
        assert ask(st, 2, "slide", slide=257)["t"] == "ok"               # the frame comes: its activity opens
        step = recv(p1, "activity.step", until=lambda m: m["step"])["step"]
        assert (step["activity"], step["phase"], step["kind"], step["input"]) == ("crowd", "open", "triples", "fields")
        assert step["suggest"] == [":KG"] and step == recv(p2, "activity.step", until=lambda m: m["step"])["step"]
        mine = recv(p1, "state", until=lambda m: m.get("activity"))["activity"]["mine"]
        assert (mine["activity"], mine["entries"], mine["used"], mine["blocked"]) == ("crowd", [], 0, False)
        # an entry: its id is the phone's; the answer comes once it is written
        got = ask(p1, 3, "activity.enter", activity="crowd", entry="ada-entry-0001", fields=[":A", ":p", ":B"])
        assert got["t"] == "ok" and got["entry"] == "ada-entry-0001" and got["state"]["state"] == "in"
        assert ask(p1, 4, "activity.enter", activity="crowd", entry="ada-entry-0001", fields=[":X", ":p", ":Y"])["state"][
            "input"] == {"fields": [":A", ":p", ":B"]}                   # sent again: the one that is there
        assert ask(p2, 3, "activity.enter", activity="crowd", entry="short", fields=[":A", ":p", ":B"])["error"] == "invalid"
        assert ask(p2, 4, "activity.enter", activity="none", entry="bea-entry-0001", fields=["a", "b", "c"])["error"] == "invalid"
        pic = picture(dp, 4, "crowd", lambda pic: pic.get("edges"))
        assert [(e["s"], e["o"]) for e in pic["edges"]] == [(":A", ":B")] and "terms" not in pic
        seen = recv(dp, "state", until=lambda m: (m["stage"].get("activity") or {}).get("items", {}).get("crowd", {})
                    .get("version") == pic["version"])["stage"]["activity"]
        assert seen["current"] == "crowd" and seen["items"]["crowd"]["phase"] == "open"
        assert recv(p2, "activity.step", until=lambda m: ":A" in (m["step"] or {}).get("suggest", ()))["step"][
            "suggest"] == [":KG", ":A", ":B"]                              # what is drawn is offered
        # the projector reads; it moves nothing and moderates nothing
        for n, (t, more) in enumerate((("activity.moderate", {"act": "hide", "group": ":A"}), ("activity.close", {}),
                                       ("activity.layout", {"at": {}}))):
            assert ask(dp, 50 + n, t, activity="crowd", **more)["error"] == "read-only"
        # the lecturer's acts, each undone by its number
        act = ask(st, 5, "activity.moderate", activity="crowd", act="hide", group=":A", role="node")["act"]
        assert act == 1 and picture(dp, 6, "crowd", lambda pic: not pic["edges"])["nodes"] == []
        assert "terms" in ask(st, 7, "activity.view", activity="crowd")["picture"]
        assert ask(st, 8, "activity.undo", activity="crowd", act=act)["act"] == 1
        assert len(picture(dp, 9, "crowd", lambda pic: pic["edges"])["nodes"]) == 2
        assert ask(st, 10, "activity.moderate", activity="crowd", act="sing")["error"] == "invalid"
        # the lead window: the first that sends a layout, and no other while it does
        assert ask(st, 11, "activity.layout", activity="crowd", at={":A": [0.2, 0.3]})["lead"] is True
        assert ask(st2, 12, "activity.layout", activity="crowd", at={":A": [0.9, 0.9]})["lead"] is False
        assert ask(st, 13, "activity.view", activity="crowd")["lead"] and not ask(st2, 14, "activity.view", activity="crowd")["lead"]
        assert picture(dp, 15, "crowd", lambda pic: pic.get("at"))["at"] == {":A": [0.2, 0.3]}
        # the frame goes: closed - and what a phone sends again is still its entry
        assert ask(st, 16, "slide", slide=260)["t"] == "ok"
        assert recv(p2, "activity.step", until=lambda m: (m["step"] or {}).get("phase") == "closed")
        assert ask(p2, 17, "activity.enter", activity="crowd", entry="bea-entry-0002", fields=[":A", ":p", ":B"])["error"] == "closed"
        assert ask(p1, 18, "activity.enter", activity="crowd", entry="ada-entry-0001", fields=[":A", ":p", ":B"])["t"] == "ok"
        assert ask(st, 19, "activity.open", activity="crowd", time=0.5)["error"] == "time"
        assert ask(st, 20, "activity.open", activity="crowd", time=60)["t"] == "ok"      # the lecturer opens it again
        assert recv(p2, "activity.step", until=lambda m: (m["step"] or {}).get("phase") == "open")["step"]["time"] <= 60_000
        assert ask(p2, 21, "activity.enter", activity="crowd", entry="bea-entry-0002", fields=[":B", ":q", ":C"])["t"] == "ok"
        picture(st, 22, "crowd", lambda pic: len(pic["edges"]) == 2)
        game = recv(st, "state")["session"]["id"]
        z = client.get(f"/api/archive/{game}.zip", headers={"X-Texquiz-Key": KEY})
        files = zipfile.ZipFile(io.BytesIO(z.content))
        assert {"activity-crowd.csv", "activity-crowd.json", "activity-crowd.svg"} <= set(files.namelist())
        rows = [row for row in files.read("activity-crowd.csv").decode("utf-8-sig").splitlines() if row]
        assert rows[0] == "time,step,epoch,input,state,status,verdict" and len(rows) == 3 and "Ada" not in "".join(rows)
        # the step's part is the phones': no window is sent it
        assert "activity.step" in SEEN[id(p1)] & SEEN[id(p2)]
        assert "activity.step" not in SEEN[id(st)] | SEEN[id(dp)] | SEEN[id(st2)]


def test_queries_are_checked_by_their_kind_and_judged_at_the_reveal(tmp_path):
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    with TestClient(create_app(config_of(tmp_path))) as client, client.websocket_connect("/ws") as st, \
            contextlib.ExitStack() as stack:
        (p1, p2), _ = join(stack, client, st, bid)
        assert ask(st, 2, "slide", slide=259)["t"] == "ok"
        step = recv(p1, "activity.step", until=lambda m: m["step"])["step"]
        assert (step["activity"], step["kind"], step["feedback"], step["tokens"]) == ("query", "sparql-query", "status",
                                                                                      ["SELECT", "{", "}"])
        assert "seed" not in step and "reference" not in str(step)
        assert ask(p1, 3, "activity.enter", activity="query", entry="ada-entry-0001", text=RIGHT + "  # Ada's")["t"] == "ok"
        assert ask(p2, 3, "activity.enter", activity="query", entry="bea-entry-0001", text=WRONG)["t"] == "ok"

        def latest(p, until) -> dict:
            return recv(p, "state", until=lambda m: (m.get("activity") or {}).get("mine", {}).get("entries")
                        and until(m["activity"]["mine"]["entries"][0]))["activity"]["mine"]["entries"][0]
        right = latest(p1, lambda e: e["check"] == "checked")
        assert (right["status"], right["input"]) == ("ok", {"text": RIGHT + "  # Ada's"}) and "verdict" not in right
        wrong = latest(p2, lambda e: e["check"] == "checked")
        assert (wrong["status"], wrong["message"]["code"], wrong["at"][0]) == ("invalid", "at", 1)
        pic = picture(st, 4, "query", lambda pic: pic["checked"] == 2)
        assert [(g["status"], g["n"], g["reference"]) for g in pic["groups"]] == [("ok", 1, True), ("invalid", 1, False)]
        assert pic["groups"][0]["example"] == {"text": RIGHT}            # shown without its comment
        # a pause: nobody sends; the time waits
        assert ask(st, 5, "activity.pause", activity="query")["t"] == "ok"
        assert ask(p2, 6, "activity.enter", activity="query", entry="bea-entry-0002", text=RIGHT)["error"] == "paused"
        assert ask(st, 7, "activity.resume", activity="query")["t"] == "ok"
        assert ask(st, 8, "activity.time", activity="query", add=30)["t"] == "ok"
        assert recv(p1, "activity.step", until=lambda m: (m["step"] or {}).get("time"))["step"]["time"] <= 30_000
        assert ask(st, 9, "activity.time", activity="query", stop=True)["t"] == "ok"
        # the lecturer blocks a student: that phone learns it, and sends no more
        block = ask(st, 10, "activity.moderate", activity="query", act="block", entry="bea-entry-0001")["act"]
        assert recv(p2, "state", until=lambda m: (m.get("activity") or {}).get("mine", {}).get("blocked"))
        assert ask(p2, 11, "activity.enter", activity="query", entry="bea-entry-0003", text=RIGHT)["error"] == "blocked"
        assert ask(st, 12, "activity.undo", activity="query", act=block)["act"] == block
        # the reveal: every phone its verdict
        assert ask(st, 13, "activity.reveal", activity="query")["t"] == "ok"
        assert latest(p1, lambda e: "verdict" in e)["verdict"] == "correct"
        assert latest(p2, lambda e: "verdict" in e)["verdict"] == "incorrect"
        assert ask(st, 14, "activity.open", activity="query")["error"] == "revealed"
        assert ask(st, 15, "activity.reset", activity="query")["t"] == "ok"       # a new epoch: nothing counts any more
        assert picture(st, 16, "query", lambda pic: pic["epoch"] == 1)["entries"] == 0


def test_a_server_that_starts_again_has_the_game_as_it_was(tmp_path):
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    with TestClient(create_app(config_of(tmp_path))) as client, client.websocket_connect("/ws") as st, \
            contextlib.ExitStack() as stack:
        (p1, p2), tokens = join(stack, client, st, bid)
        assert ask(st, 2, "slide", slide=259)["t"] == "ok"
        recv(p1, "activity.step", until=lambda m: m["step"])
        assert ask(p1, 3, "activity.enter", activity="query", entry="ada-entry-0001", text=RIGHT)["t"] == "ok"
        assert ask(p2, 3, "activity.enter", activity="query", entry="bea-entry-0001", text=WRONG)["t"] == "ok"
        before = picture(st, 4, "query", lambda pic: pic["checked"] == 2)
    with TestClient(create_app(config_of(tmp_path))) as client, client.websocket_connect("/ws") as st, \
            client.websocket_connect("/ws") as p1:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "act", "bundle": bid, "id": 1})
        recv(st, "welcome")
        after = picture(st, 2, "query", lambda pic: pic["checked"] == 2 and pic["groups"][0]["reference"])
        assert after["groups"] == before["groups"] and after["phase"] == "open"         # (it had no time: it stays open)
        p1.send_json({"t": "resume", "token": tokens[0], "id": "r"})
        recv(p1, "welcome")
        assert recv(p1, "activity.step")["step"]["activity"] == "query"                 # what every phone has
        mine = recv(p1, "state", until=lambda m: m.get("activity"))["activity"]["mine"]
        assert [(e["id"], e["status"]) for e in mine["entries"]] == [("ada-entry-0001", "ok")]
        # an entry of before the restart, sent again: the one that is there - no second one
        assert ask(p1, 3, "activity.enter", activity="query", entry="ada-entry-0001", text=RIGHT)["t"] == "ok"
        assert picture(st, 4, "query", lambda pic: True)["entries"] == 2


# ------------------------------------------------------------------ the engine's part, without a server
def test_a_game_of_f1s_is_moved_when_a_server_with_the_cores_type_starts(tmp_path):
    w = World(tmp_path)                                     # F1's type: a phone's triple, as F1 stores it
    (ada,) = w.join("Ada")
    w.show(257)
    w.send(ada, "crowd", fields=[":A", ":p", ":B"])
    w.engine.store.close()
    stage_types.use("core")
    engine = Engine(BundleStore([tmp_path / "bundles"]), Store(tmp_path / "store.sqlite3"), Settings())
    pic = engine.type_message(w.s.id, "activity.view", {"activity": "crowd"}, w.now, role="stage")["picture"]
    assert [(e["s"], e["o"]) for e in pic["edges"]] == [(":A", ":B")] and pic["phase"] == "open"
    mine = engine.player_view(ada, w.now)["activity"]["mine"]
    assert [e["input"] for e in mine["entries"]] == [{"fields": [":A", ":p", ":B"]}] and mine["used"] == 1
    assert engine.sessions[w.s.id].stage["activity"]["items"]["crowd"]["count"] == 1      # F1's state: as F1 left it
    engine.store.close()
    again = Engine(BundleStore([tmp_path / "bundles"]), Store(tmp_path / "store.sqlite3"), Settings())
    assert len(again.books["activity"].plays[w.s.id].entries.held[("crowd", "main")].entries) == 1    # not moved twice
    again.store.close()


def test_a_quiz_round_pauses_the_step_that_runs_and_the_panel_says_when_nothing_is_written(tmp_path, monkeypatch):
    stage_types.use("core")
    w = World(tmp_path)
    w.stage("activity.open", activity="crowd", time=60)
    assert w.engine.pulse(w.tick(100)) == set() and w.item("crowd")["phase"] == "open"
    monkeypatch.setattr(w.engine, "round_on", lambda sid: True)
    assert w.engine.pulse(w.tick(100)) == {w.s.id}
    assert (w.item("crowd")["phase"], w.engine.take_due()) == ("paused", {w.s.id: True})
    assert '"phase":"paused"' in w.engine.take_casts()[w.s.id]            # every phone, as one text
    monkeypatch.setattr(w.engine, "round_on", lambda sid: False)
    assert w.engine.pulse(w.tick(100)) == {w.s.id} and w.item("crowd")["phase"] == "open"
    resumed = w.item("crowd")
    assert 59_000 < resumed["time"] <= 60_000 and resumed["since"] == w.now      # the time waited with it
    assert w.engine.pulse(w.tick(4000)) == set() and w.item("crowd") == resumed  # ... and runs: told once, not with every tick
    assert w.engine.books["activity"].plays[w.s.id].step("crowd").time_left < 56_500
    assert w.engine.pulse(w.tick(4000) + 60_000) == {w.s.id} and w.item("crowd")["phase"] == "paused"    # a sleep
    book = w.engine.books["activity"]
    assert "store" not in w.stage("activity.view", activity="crowd")
    book.writer.error, book.writer.failures = "OperationalError: database or disk is full", 3
    assert w.stage("activity.view", activity="crowd")["store"] == {
        "failures": 3, "error": "OperationalError: database or disk is full", "set_aside": 0}
    assert "store" not in w.stage("activity.view", window="display", activity="crowd")
    w.engine.store.close()


def test_a_deck_opens_an_activity_by_hand_where_it_says_so(tmp_path):
    stage_types.use("core")
    w = World(tmp_path, crowd={"open": "manual"})
    w.show(257)
    assert w.engine.host_view(w.s.id, w.now)["stage"]["activity"]["current"] is None and w.item("crowd")["phase"] == "ready"
    w.stage("activity.open", activity="crowd")
    w.show(260)
    assert w.item("crowd")["phase"] == "closed"
    w.show(257)                                             # going back never opens a closed step
    assert w.item("crowd")["phase"] == "closed"
    with pytest.raises(GameError) as e:
        w.stage("activity.open", activity="crowd", step="second")
    assert e.value.code == "invalid"
    w.engine.store.close()


def test_what_the_pool_says_in_its_own_words_is_a_message_of_the_kinds_or_none():
    sql, triples = registry.kind("sql-query"), registry.kind("triples")
    ok = {"status": "ok", "key": "k", "tries": 1}
    assert activities._fit(sql, ok) is ok
    memory = {"status": "error", "error": "needs more memory than a check may use", "tries": 2}
    assert activities._fit(sql, memory) == {"status": "error", "tries": 2, "message": {"code": "tooMuchMemory", "args": {}}}
    assert activities._fit(registry.kind("sparql-query"), memory)["message"] == {
        "code": "engine", "args": {"text": "needs more memory than a check may use"}}
    assert activities._fit(triples, memory) == {"status": "error", "tries": 2}
    assert activities._fit(sql, {"status": "internal", "error": "set aside: it failed twice", "set_aside": True}) == {
        "status": "internal", "set_aside": True}


def test_a_server_runs_one_activity_type():
    assert stage_types.using == "f1" and stage_types.TYPES["activity"] is stage_types.activity
    stage_types.use("core")
    assert stage_types.TYPES["activity"] is activities and "activity.enter" in stage_types.PLAYER_MESSAGES
    assert "activity.send" not in stage_types.PLAYER_MESSAGES and stage_types.READS == {"activity.view"}
    with pytest.raises(ValueError, match="activities: one of f1, core"):
        stage_types.use("f2")
    assert stage_types.using == "core"


# ------------------------------------------------------------------ after the review: a pool that answers when told
class FakePool:
    """A pool whose answers the test gives, when it wants to."""

    def __init__(self):
        self.calls, self.waiting, self.closed, self.broken, self.budgets = [], [], False, None, []

    def _take(self, *call):
        if self.closed:
            raise RuntimeError("the pool is closed")
        self.calls.append(call)
        self.waiting.append((call, cf.Future()))
        return self.waiting[-1][1]

    def prepare(self, act, engine, seed, references=(), language=None):
        return self._take("prepare", act, engine)

    def normalize(self, kind, item, keys, input, language=None):
        return self._take("normalize", kind, json.dumps(input, sort_keys=True))

    def submit(self, act, text, owner=None, budget_s=1.0, language=None):
        self.budgets.append(budget_s)
        return self._take("submit", act, text)

    def withdraw(self, act, text):
        self.calls.append(("withdraw", act, text))
        return True

    def drop(self, act):
        self.calls.append(("drop", act))

    def answer(self, what: str, value, part: str = ""):
        """The oldest call of this kind that waits - and names this part - is answered."""
        i = next(i for i, (call, _) in enumerate(self.waiting) if call[0] == what and part in call[1])
        call, fut = self.waiting.pop(i)
        fut.set_exception(value) if isinstance(value, Exception) else fut.set_result(value)
        return call

    def count(self, what: str) -> int:
        return sum(call[0] == what for call in self.calls)


class FakeChecks:
    """What the engine has of checking.py's Checks, around such a pool."""
    mode, later, again_s = "server", [], 1.0

    def __init__(self):
        self.pool, self.bundles, self.wake = FakePool(), None, lambda: None

    def release(self, bundle_id):
        pass

    def answers(self):
        return []

    def problems(self, bundle_id):
        return {}


def core_world(tmp_path, **kw):
    stage_types.use("core")
    w = World(tmp_path, checks=FakeChecks(), **kw)
    return w, w.checks.pool, w.engine.books["activity"]


def enter(w, pid: str, n: int, activity: str = "query", **sent) -> dict:
    w.tick(6000)
    return w.engine.type_player_message(pid, "activity.enter", {"activity": activity, "entry": f"entry-{n:05d}", **sent}, w.now)


def refused(code: str, call, *args, **kw):
    with pytest.raises(GameError) as e:
        call(*args, **kw)
    assert e.value.code == code, f"{e.value.code}: {e.value}"


OK1 = {"status": "ok", "key": "k1", "detail": {"kind": "select", "columns": ["?n"], "count": 1, "rows": [["Kant"]]}}


def test_a_decks_references_are_a_games_whenever_they_come(tmp_path):
    """The pool prepares a deck when its game comes - long before anybody shows an activity: the review found
    that a deck's first game then never had them, and so no verdict."""
    w, pool, book = core_world(tmp_path)
    w.join("Ada")
    assert [c[1:] for c in pool.calls] == [(f"{w.bid}/crowd", "kind:triples"), (f"{w.bid}/query", "kind:sparql-query")]
    pool.answer("prepare", [OK1], "query")
    assert w.engine.apply_checks(w.now) == {w.s.id} and book.plays == {}        # nobody touched an activity yet
    w.show(259)
    assert w.picture("query", "stage")["references"] == [{"group": gid("ok", "k1")}]
    # another game of the same build: prepared once, and the references are its own at once
    other = w.engine.open_session("act", w.bid, w.now, owner="other")
    assert pool.count("prepare") == 2
    assert w.engine.type_message(other.id, "activity.view", {"activity": "query"}, w.now, role="stage")["picture"][
        "references"] == [{"group": gid("ok", "k1")}]
    # references that come when the phones have their state: every phone gets it again - a verdict may be new
    w.show(257)
    w.engine.take_due()
    pool.answer("prepare", [], "crowd")
    assert w.engine.apply_checks(w.now) == {w.s.id, other.id} and w.engine.take_due() == {w.s.id: True, other.id: True}
    w.engine.store.close()


def test_a_refused_message_that_found_a_step_changed_tells_the_windows_and_the_phones(tmp_path):
    w, pool, book = core_world(tmp_path)
    (ada,) = w.join("Ada")
    w.stage("activity.open", activity="crowd", time=2)
    w.engine.take_due(), w.engine.take_casts()
    w.tick(3000)                                            # the time ran out; a phone's entry is the first to find it so
    refused("closed", w.engine.type_player_message, ada, "activity.enter",
            {"activity": "crowd", "entry": "entry-00001", "fields": ["a", "b", "c"]}, w.now)
    assert w.item("crowd")["phase"] == "closed" and w.engine.take_due() == {w.s.id: True}
    assert w.engine.pulse(w.tick(100)) == {w.s.id} and w.engine.pulse(w.tick(100)) == set()
    w.stage("activity.open", activity="crowd", time=2)
    w.engine.take_due()
    w.tick(3000)                                            # ... or the lecturer's Pause
    refused("closed", w.stage, "activity.pause", activity="crowd")
    assert w.engine.take_due() == {w.s.id: True} and w.engine.pulse(w.tick(100)) == {w.s.id}
    w.engine.store.close()


def test_an_activity_that_is_not_prepared_says_so_in_the_windows(tmp_path):
    w, pool, book = core_world(tmp_path)
    pool.answer("prepare", ValueError("the seed data/x.ttl: no Turtle\nand more"), "query")
    assert w.engine.apply_checks(w.now) == {w.s.id}          # (the host view has it: the game has no core yet)
    assert w.engine.host_view(w.s.id, w.now)["checks"] == {"mode": "server", "failing": {"query": "the seed data/x.ttl: no Turtle"}}
    assert w.stage("activity.view", activity="query")["failed"] == "the seed data/x.ttl: no Turtle"
    assert "failed" not in w.stage("activity.view", window="display", activity="query")
    assert "failed" not in w.stage("activity.view", activity="crowd")
    pool.broken = "three processes ended before they were ready"
    assert w.engine.host_view(w.s.id, w.now)["checks"]["failing"] == {"crowd": pool.broken, "query": pool.broken}
    w.engine.store.close()


def test_a_job_the_pool_does_not_take_leaves_its_entry_unchecked_not_waiting(tmp_path):
    w, pool, book = core_world(tmp_path)
    ada, bea = w.join("Ada", "Bea")
    w.show(259)
    pool.closed = True
    assert enter(w, ada, 1, text=RIGHT)["state"]["check"] == "waiting"
    w.engine.pulse(w.tick(100))                              # (nobody wakes the engine for it: the tick takes it)
    assert w.phone(ada)["mine"]["entries"][0]["check"] == "unchecked"
    assert w.picture("query", "stage")["unchecked"] == 1
    pool.closed = False
    enter(w, bea, 2, text=RIGHT)                            # the same text again: asked again
    assert pool.count("normalize") == 1
    pool.answer("normalize", {"input": {"text": RIGHT}})
    w.engine.apply_checks(w.now)
    act, text = pool.calls[-1][1:]
    assert pool.calls[-1][0] == "submit" and json.loads(text) == {"text": RIGHT}
    # an entry that is replaced: its check leaves the queue - unless the other student waits for it
    enter(w, bea, 3, text=WRONG)
    assert ("withdraw", act, text) not in pool.calls         # Ada's entry of the same text still waits
    enter(w, ada, 4, text=WRONG)
    assert ("withdraw", act, text) in pool.calls
    # a game that ends: what it still waited for leaves the queue, and the build's activities go
    pool.answer("normalize", {"input": {"text": WRONG}})
    w.engine.apply_checks(w.now)
    w.engine.end(w.s.id, w.now)
    assert pool.calls[-3][0] == "withdraw" and {c[1] for c in pool.calls[-2:]} == {f"{w.bid}/crowd", f"{w.bid}/query"}
    assert (book.plays, book.prepared, book.parts, book.asked, book.late) == ({}, {}, {}, {}, set())
    w.engine.store.close()


def test_an_entry_is_the_writers_and_a_muted_student_sends_none(tmp_path, monkeypatch):
    w, pool, book = core_world(tmp_path)
    (ada,) = w.join("Ada")
    w.show(259)
    saved = []
    monkeypatch.setattr(w.engine, "_save", lambda *rows: saved.extend(rows))
    reply = enter(w, ada, 1, text=RIGHT)
    assert saved == []                                      # no session stored, nothing committed, for a phone's entry
    done = []
    reply[stage_types.WRITTEN](lambda: done.append("answered"))
    assert done == [] and book.writer.pending() >= 1         # the answer waits for the row
    assert book.writer.flush() >= 1 and done == ["answered"] and book.writer.pending() == 0
    w.engine.players[ada].muted = True                       # the engine's word, as the acts' (blocked)
    refused("blocked", enter, w, ada, 2, text=WRONG)
    assert w.phone(ada)["mine"]["blocked"] is True
    w.engine.store.close()


def test_the_app_answers_an_entry_once_it_is_written_and_remembers_the_answer_then(tmp_path):
    import asyncio

    from texstage.server.app import Conn, Server
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle")
    server = Server(config_of(tmp_path))
    engine, t0 = server.engine, 1_800_000_000_000
    try:
        s = engine.open_session("act", bid, t0)
        pid = engine.join(s.pin, "Ada", t0)[0].id
        engine.type_message(s.id, "activity.open", {"activity": "crowd"}, t0, role="stage")
        conn = Conn(type("Socket", (), {"client": None})())
        conn.role, conn.player, conn.session = "player", pid, s.id
        server.conns[s.id].add(conn)
        msg = {"t": "activity.enter", "id": 7, "activity": "crowd", "entry": "entry-00001", "fields": ["a", "b", "c"]}
        asyncio.run(server.handle(conn, msg))
        assert [m for m in conn.outbox if not isinstance(m, str)] == [] and 7 not in server.replies[("player", pid)]
        asyncio.run(server.handle(conn, msg))               # the phone sends it again: asked again, the same entry
        writer = engine.books["activity"].writer
        assert writer.pending() >= 1 and writer.flush() >= 1
        answers = [m for m in conn.outbox if not isinstance(m, str)]
        assert [(m["t"], m["re"], m["entry"]) for m in answers] == [("ok", 7, "entry-00001")] * 2
        assert server.replies[("player", pid)][7] == answers[0]
    finally:
        server.store.close()


def test_the_lead_window_leads_for_fifteen_seconds_and_until_it_goes(tmp_path):
    w, pool, book = core_world(tmp_path)
    w.show(257)
    assert not w.stage("activity.view", activity="crowd", conn="w1")["lead"]
    refused("invalid", w.stage, "activity.layout", activity="crowd", conn="w2", at=[0.5, 0.5])
    refused("reduction", w.stage, "activity.layout", activity="query", conn="w2", at={})
    assert book.leads == {}                                 # a layout that is none takes no lease
    assert w.stage("activity.layout", activity="crowd", conn="w1", at={})["lead"] is True
    assert w.stage("activity.layout", activity="crowd", conn="w2", at={})["lead"] is False
    w.tick(14_000)
    assert w.stage("activity.layout", activity="crowd", conn="w1", at={})["lead"] is True       # again, with each layout
    w.tick(14_000)
    assert w.stage("activity.layout", activity="crowd", conn="w2", at={})["lead"] is False
    w.tick(1_001)                                           # fifteen seconds after w1's last one
    assert w.stage("activity.layout", activity="crowd", conn="w2", at={})["lead"] is True
    assert not w.stage("activity.view", activity="crowd", conn="w1")["lead"]
    w.engine.left("w2")                                     # the window goes: another may
    assert w.stage("activity.layout", activity="crowd", conn="w1", at={})["lead"] is True
    w.engine.store.close()


def test_the_steps_part_goes_to_the_phones_at_most_once_a_second_unless_a_step_moves(tmp_path):
    from texstage.server import worker
    w, pool, book = core_world(tmp_path)
    ada, bea = w.join("Ada", "Bea")
    w.show(257)
    assert json.loads(w.engine.take_casts()[w.s.id])["step"]["suggest"] == [":KG"]      # a step moved: at once
    of = worker._OfKind("triples")
    state = of.load({"item": book.parts[(w.bid, "crowd")].item, "keys": {}, "files": {}})

    def checked(fields: list) -> None:
        pool.answer("normalize", {"input": {"fields": fields}})
        w.engine.apply_checks(w.now)
        pool.answer("submit", of.check(state, None, pool.calls[-1][2], "en", 1.0)[0])
        w.engine.apply_checks(w.now)
    enter(w, ada, 1, activity="crowd", fields=[":A", ":p", ":B"])            # (six seconds on)
    checked([":A", ":p", ":B"])
    assert w.engine.pulse(w.tick(300)) == {w.s.id}          # the windows: a new version
    assert json.loads(w.engine.take_casts()[w.s.id])["step"]["suggest"] == [":KG", ":A", ":B"]    # the phones: what a field offers
    w.engine.type_player_message(bea, "activity.enter", {"activity": "crowd", "entry": "entry-00002",
                                                         "fields": [":C", ":p", ":D"]}, w.tick(100))
    checked([":C", ":p", ":D"])
    assert w.engine.pulse(w.tick(300)) == {w.s.id}
    assert w.engine.take_casts() == {}                      # it has grown again: not yet
    w.engine.pulse(w.tick(500))
    assert w.engine.take_casts() == {}
    w.engine.pulse(w.tick(200))                             # more than a second after the last one
    assert json.loads(w.engine.take_casts()[w.s.id])["step"]["suggest"] == [":KG", ":A", ":B", ":C", ":D"]
    w.stage("activity.close", activity="crowd")             # a step moves: at once
    assert json.loads(w.engine.take_casts()[w.s.id])["step"]["phase"] == "closed"
    w.engine.store.close()


def test_one_games_fault_in_the_tick_is_its_own(tmp_path, monkeypatch, caplog):
    w, pool, book = core_world(tmp_path)
    other = w.engine.open_session("act", w.bid, w.now, owner="other")
    for sid in (w.s.id, other.id):
        w.engine.type_message(sid, "activity.open", {"activity": "crowd", "time": 2}, w.now, role="stage")

    def broken(now):
        raise RuntimeError("a fault of the core's")
    monkeypatch.setattr(book.plays[w.s.id], "tick", broken)
    for _ in range(3):
        w.engine.pulse(w.tick(1000))
    assert w.engine.host_view(other.id, w.now)["stage"]["activity"]["items"]["crowd"]["phase"] == "closed"
    assert sum("the tick of the game" in r.message for r in caplog.records) == 1          # said once, not ten times a second
    w.engine.store.close()


def test_the_pools_words_for_too_much_memory_are_known_in_every_language():
    from texstage.checks import texts
    sql = registry.kind("sql-query")
    for language in texts.ENGINES:
        got = activities._fit(sql, {"status": "error", "error": texts.ENGINES[language]["tooMuchMemory"]})
        assert got == {"status": "error", "message": {"code": "tooMuchMemory", "args": {}}}, language


def test_a_game_of_f1s_that_does_not_move_keeps_no_other_from_moving(tmp_path, monkeypatch):
    w = World(tmp_path)                                     # F1's type: two games of the deck, a triple in each
    other = w.engine.open_session("act", w.bid, w.now, owner="other")
    w.show(257)
    w.engine.show_slide(other.id, 257, w.now)
    w.send(w.join("Ada")[0], "crowd", fields=[":A", ":p", ":B"])
    bea = w.engine.join(other.pin, "Bea", w.now)[0].id
    w.engine.type_player_message(bea, "activity.send", {"activity": "crowd", "fields": [":C", ":p", ":D"]}, w.tick())
    w.engine.store.close()
    move = activities.core.move

    def failing(db, stages, decks=None):
        if w.s.id in stages:
            raise RuntimeError("a row of this game that does not move")
        return move(db, stages, decks)
    monkeypatch.setattr(activities.core, "move", failing)
    stage_types.use("core")
    engine = Engine(BundleStore([tmp_path / "bundles"]), Store(tmp_path / "store.sqlite3"), Settings())
    plays = engine.books["activity"].plays
    assert list(plays) == [other.id] and len(plays[other.id].entries.held[("crowd", "main")].entries) == 1
    engine.store.close()


def test_without_a_pool_an_entry_is_unchecked_not_waiting(tmp_path):
    stage_types.use("core")
    w = World(tmp_path)                                     # an engine that nobody gave checks: no pool at all
    (ada,) = w.join("Ada")
    w.show(259)
    assert enter(w, ada, 1, text=RIGHT)["state"]["check"] == "waiting"
    assert w.engine.pulse(w.tick(100)) == {w.s.id}
    assert w.phone(ada)["mine"]["entries"][0]["check"] == "unchecked" and w.picture("query", "stage")["unchecked"] == 1
    w.engine.store.close()



# ------------------------------------------------------------------ what the build says since package 7
MARKED = {"shows": {257: "crowd", 258: "crowd", 259: "query", 260: "query"},
          "phases": {257: "revealed", 258: "open", 259: "open", 260: "revealed"}}


def test_the_pages_the_build_marks_open_and_reveal_their_step_with_the_decks_time(tmp_path):
    """A page says what it is of its activity (the build: \\reveal<n>): one marked open opens its step with
    the deck's time=, one marked revealed reveals it - if it was opened: paging onto the reveal of a step
    nobody answered reveals nothing, and paging back leaves a revealed step revealed. A check gets the
    deck's budget=."""
    w, pool, book = core_world(tmp_path, query={"time": 30, "budget": 300}, **MARKED)
    (ada,) = w.join("Ada")
    w.show(257)
    assert w.item("crowd")["phase"] == "ready"
    w.show(258)
    assert (w.item("crowd")["phase"], w.item("crowd")["time"]) == ("open", None)
    w.show(259)                                             # the crowd's pages go: it closes; the query opens, timed
    assert w.item("crowd")["phase"] == "closed"
    assert (w.item("query")["phase"], w.item("query")["time"]) == ("open", 30_000)
    w.engine.type_player_message(ada, "activity.enter", {"activity": "query", "entry": "entry-00001", "text": RIGHT},
                                 w.tick(100))               # (more than 5 s between two ticks: a sleep, which pauses)
    pool.answer("normalize", {"input": {"text": RIGHT}})
    w.engine.apply_checks(w.now)
    assert pool.calls[-1][0] == "submit" and pool.budgets == [0.3]
    w.show(260)
    assert w.item("query")["phase"] == "revealed"
    w.show(259)
    assert w.item("query")["phase"] == "revealed"
    w.engine.store.close()


def test_the_lecturers_open_takes_the_decks_time_the_first_time(tmp_path):
    """open=manual: the lecturer opens the step - with the deck's time=, unless they give one; opened again
    after it was closed, it goes on without, as the lecturer says (the plan of F2, 4.3)."""
    w, pool, book = core_world(tmp_path, query={"time": 30, "open": "manual"}, crowd={"time": 45})
    w.show(259)
    assert w.item("query")["phase"] == "ready"
    w.stage("activity.open", activity="query")
    assert (w.item("query")["phase"], w.item("query")["time"]) == ("open", 30_000)
    w.stage("activity.close", activity="query")
    w.stage("activity.open", activity="query")
    assert (w.item("query")["phase"], w.item("query")["time"]) == ("open", None)
    w.stage("activity.open", activity="crowd", time=10)                # the lecturer's own time comes first
    assert (w.item("crowd")["phase"], w.item("crowd")["time"]) == ("open", 10_000)
    w.engine.store.close()


def test_an_item_whose_time_or_budget_is_none_is_refused(tmp_path):
    w, pool, book = core_world(tmp_path, query={"time": 0}, crowd={"budget": 5000})
    refused("invalid", w.stage, "activity.open", activity="query")
    refused("invalid", w.stage, "activity.open", activity="crowd")
    w.engine.store.close()


def kinds_of(*names, **more) -> dict:
    """deck.json's kinds as the build writes them, of the kinds installed here."""
    found = {f.name: f for f in registry.found()}
    return {"kinds": {n: {"package": found[n].package, "version": found[n].version, "api": found[n].api} | more
                      for n in names}}


def test_a_server_of_the_cores_type_refuses_a_deck_of_a_kind_it_lacks(tmp_path, monkeypatch):
    """The deck's kinds (deck.json, the build's): a server of the core's type refuses the deck - and says
    which package to install - when it lacks one, cannot use it, has it with another API or another major
    version, or older than the build's (the design's 7.2). F1's type needs no kinds: it takes the deck."""
    from texstage.server.bundles import BundleError, load_bundle
    folder = tmp_path / "bundles" / "act.bundle"
    have = {f.name: f for f in registry.found()}["sparql-query"]
    major = int(have.version.split(".")[0])
    stage_types.use("core")
    for more, said in (
            ({}, None),
            ({"version": "0.0.1"}, None),                    # an older build: this server knows its keys
            ({"version": f"{major}.999.0"}, f"this server has {have.version} - install texstage-kinds-rdf "
                                            f"{major}.999.0 or later where the server runs"),
            ({"version": f"{major + 1}.0.0"}, f"this server has {have.version}"),
            ({"api": 1}, f"with API 1, this server's texstage-kinds-rdf {have.version} has API 0"),
            ({"version": "unknown"}, None)):
        make_activity_bundle(folder, deck_more=kinds_of("triples", "sparql-query", **more))
        if said is None:
            assert load_bundle(folder).items["activity"]
            continue
        with pytest.raises(BundleError, match="the deck's activities are of the kind") as e:
            load_bundle(folder)
        assert said in str(e.value), str(e.value)
    make_activity_bundle(folder, deck_more=kinds_of("triples", "sparql-query"))
    rest = tuple(f for f in registry.found() if f.name != "sparql-query")
    monkeypatch.setattr(registry, "found", lambda: rest)
    with pytest.raises(BundleError) as e:
        load_bundle(folder)
    assert str(e.value).endswith(f"the deck's activities are of the kind sparql-query, which this server does not have - "
                                 f"install texstage-kinds-rdf {have.version} or later where the server runs")
    monkeypatch.setattr(registry, "found", lambda: rest + (registry.Found("sparql-query", "texstage-kinds-rdf", have.version, 0,
                                                                          None, "it cannot be made - ImportError: pyoxigraph"),))
    with pytest.raises(BundleError, match="cannot be used for: it cannot be made - ImportError: pyoxigraph"):
        load_bundle(folder)
    stage_types.use("f1")
    assert load_bundle(folder).items["activity"]                    # F1's type: as before
    stage_types.use("core")
    make_activity_bundle(folder)                                       # a deck built before kinds were named: as before
    assert load_bundle(folder).items["activity"]


@pytest.mark.parametrize("server, built, refused", [
    ("2.0.0", "1.4.0", True),             # a newer major version: its keys may mean other things (the review: taken)
    ("1.2", "1.2.0", False),              # 1.2 is 1.2.0 (it was refused)
    ("1.2.0", "1.2", False),
    ("1.2.0rc1", "1.2.0", True),          # a release before the build's
    ("1.2.0", "1.2.0rc1", False),
    ("1.2.0.dev3", "1.2.0", True),
    ("0.10.0", "0.9.0", False),
    ("1.3.0+local", "1.2.0", False),
])
def test_the_versions_a_server_compares(server, built, refused, monkeypatch):
    have = {f.name: f for f in registry.found()}["sql-query"]
    found = tuple(f if f.name != "sql-query" else registry.Found(f.name, f.package, server, f.api, f.kind, f.fault)
                  for f in registry.found())
    monkeypatch.setattr(registry, "found", lambda: found)
    said = activities.refuses({"kinds": {"sql-query": {"package": have.package, "version": built, "api": 0}}})
    assert bool(said) == refused, said


def test_the_deck_list_says_a_reference_that_gives_another_result_than_at_the_build(tmp_path):
    """The build records the references' keys; the deck list says where this server's engine gives another one -
    another SQLite, say -, or where a reference does not run here (the design's 9)."""
    w, pool, book = core_world(tmp_path, query_keys={"referenceKeys": ["k1"]})
    w.join("Ada")
    pool.answer("prepare", [OK1], "query")
    w.engine.apply_checks(w.now)
    assert book.failing(w.bid) == [] == stage_types.failing(w.engine, w.s)
    w.engine.end(w.s.id, w.now)
    # a reference whose two runs at build gave two keys (random()) has none: it is not compared
    w, pool, book = core_world(tmp_path / "random", query_keys={"referenceKeys": [None]})
    w.join("Ada")
    pool.answer("prepare", [OK1], "query")
    w.engine.apply_checks(w.now)
    assert book.failing(w.bid) == []
    w.engine.end(w.s.id, w.now)
    w, pool, book = core_world(tmp_path / "again", query_keys={"referenceKeys": ["the build's"]})
    w.join("Ada")
    pool.answer("prepare", [OK1, {"status": "invalid", "message": {"code": "at", "args": {
        "line": 1, "column": 8, "message": "expected WHERE"}}, "at": [1, 8]}], "query")
    w.engine.apply_checks(w.now)
    failing = stage_types.failing(w.engine, w.s)
    assert [(f["activity"], f["reference"]) for f in failing] == [("query", 1), ("query", 2)]
    assert failing[0]["error"].startswith("it gives another result here than when the deck was built - another engine")
    assert "line 1" in failing[1]["error"] and "expected WHERE" in failing[1]["error"]
    w.engine.store.close()


def test_the_deck_list_over_http_has_the_cores_failing_references(tmp_path):
    """A server of the core's type (its pool, the kinds): the build's key of the reference is not this server's -
    the deck list says so as the game starts, before the lecture."""
    bid = make_activity_bundle(tmp_path / "bundles" / "act.bundle", query_keys={"referenceKeys": ["0000000000000000"]})
    with TestClient(create_app(config_of(tmp_path))) as client, client.websocket_connect("/ws") as st:
        st.send_json({"t": "hello", "role": "stage", "key": KEY, "deck": "act", "bundle": bid, "id": 1})
        recv(st, "welcome")
        end = time.monotonic() + 60
        while not (failing := client.get("/api/decks", headers={"X-Texquiz-Key": KEY}).json()[0]["failing"]):
            assert time.monotonic() < end, "the deck list never said so"
            time.sleep(0.05)
        assert [(f["activity"], f["reference"]) for f in failing] == [("query", 1)]
        assert "another result here" in failing[0]["error"]
