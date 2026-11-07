# SPDX-License-Identifier: Apache-2.0
"""Host-owned credits, submission clocks and a durable publication ledger."""
import time
from . import PluginError
from .manifest import read_json
from .records import ActorRecords

MAX_POINTS = 10000
MAX_ACTORS = 1000
SCORING_EFFECTS = {"set-credit", "publish-points", "points-open"}


def point_settings(public, spec):
    policy = spec.get("scoring")
    if policy is None:
        return None
    maximum = public.get(policy["points_field"])
    if type(maximum) is not int or not 0 <= maximum <= MAX_POINTS:
        raise PluginError("activity points must be an integer from 0 to 10000")
    mode = policy["policy"]
    seconds = public.get(policy["time_field"]) if mode == "quiz-v1" else 0
    if mode == "quiz-v1" and (type(seconds) is not int or not 1 <= seconds <= 3600):
        raise PluginError("activity scoring time must be an integer from 1 to 3600 seconds")
    return maximum, mode, seconds * 1000


def fixed_points(public, spec):
    """Validate the declared point policy; retain the original build helper name."""
    settings = point_settings(public, spec)
    return settings[0] if settings is not None else None


def base_points(maximum, credit, policy, answer_ms=0, limit_ms=0):
    if credit is None:
        return 0
    if policy == "quiz-v1":
        from texstage.server.scoring import speed_points
        maximum = speed_points(maximum, answer_ms, limit_ms)
    return (maximum * credit + 500) // 1000


class FixedPoints:
    """The original fixed-v1 ledger also supports timed quiz-v1 contributions."""
    def __init__(self, db, catalog):
        self.db, self.catalog = db, catalog
        db.executescript("""
          CREATE TABLE IF NOT EXISTS point_rounds (
            sid TEXT, kind TEXT, item TEXT, epoch INTEGER, revision INTEGER,
            published INTEGER, maximum INTEGER, PRIMARY KEY(sid,kind,item));
          CREATE TABLE IF NOT EXISTS point_credits (
            sid TEXT, kind TEXT, item TEXT, epoch INTEGER, actor TEXT, credit INTEGER,
            PRIMARY KEY(sid,kind,item,epoch,actor));
        """)
        additions = {
            "point_rounds": {"policy": "TEXT DEFAULT 'fixed-v1'", "limit_ms": "INTEGER DEFAULT 0",
                             "opened_ms": "INTEGER", "elapsed_ms": "INTEGER DEFAULT 0", "published_at": "INTEGER"},
            "point_credits": {"answer_ms": "INTEGER"},
        }
        for table, columns in additions.items():
            have = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
            for name, declaration in columns.items():
                if name not in have:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def settings(self, row):
        _, spec = self.catalog.capability(row["kind"])
        return point_settings(read_json(row["spec"], limit=8*1024*1024)["public"], spec) if "scoring" in spec else None

    @staticmethod
    def key(row):
        return row["sid"], row["kind"], row["item"]

    def context(self, row, actor=None):
        settings = self.settings(row)
        if settings is None:
            return {}
        maximum, policy, _ = settings
        head = self.db.execute("SELECT * FROM point_rounds WHERE sid=? AND kind=? AND item=? AND epoch=?",
                               (*self.key(row), row["epoch"])).fetchone()
        released = bool(head and head["published"])
        own = None
        if actor is not None and released:
            own = self.db.execute("SELECT credit FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=? AND actor=?",
                                  (*self.key(row), row["epoch"], actor)).fetchone()
        # Quiz totals include cross-activity streaks and come from the game engine.
        awarded = base_points(maximum, own["credit"], policy) if (
            policy == "fixed-v1" and own and own["credit"] is not None) else None
        return {"scoring": {"maximum": maximum, "released": released, "awarded": awarded}}

    def prepare(self, row, effects, actor, role):
        selected = [e for e in effects if isinstance(e, dict) and e.get("kind") in SCORING_EFFECTS]
        if not selected:
            return None
        settings = self.settings(row)
        if settings is None:
            raise PluginError("activity did not declare scoring")
        kinds = set()
        for effect in selected:
            kind = effect["kind"]
            if kind in kinds:
                raise PluginError("duplicate scoring effect")
            kinds.add(kind)
            if kind == "set-credit":
                if actor is None or set(effect) != {"kind", "credit"}:
                    raise PluginError("credit requires the authenticated event actor")
                ActorRecords.actor(actor)
                credit = effect["credit"]
                if credit is not None and (type(credit) is not int or not 0 <= credit <= 1000):
                    raise PluginError("credit must be null or an integer from 0 to 1000")
            elif kind == "points-open":
                if (settings[1] != "quiz-v1" or set(effect) != {"kind", "open"} or type(effect["open"]) is not bool
                        or role not in ("presenter", "system") or (role == "system" and effect["open"])):
                    raise PluginError("only presenter controls can open the scoring clock")
            elif role != "presenter" or set(effect) != {"kind"}:
                raise PluginError("only presenter commands can publish points")
        return settings, actor, role, selected

    def apply(self, row, prepared, *, reset=False, now=None):
        # Shares the item CAS, records, jobs and receipt transaction. Client
        # payloads and evaluator completions never supply submission timestamps.
        key = self.key(row)
        if reset:
            if prepared is not None:
                raise PluginError("reset cannot issue scoring effects")
            self.db.execute("DELETE FROM point_credits WHERE sid=? AND kind=? AND item=?", key)
            self.db.execute("""UPDATE point_rounds SET epoch=?,revision=0,published=0,
                            opened_ms=NULL,elapsed_ms=0,published_at=NULL WHERE sid=? AND kind=? AND item=?""",
                            (row["epoch"]+1, *key))
            return
        if prepared is None or prepared[0][0] == 0:
            return
        (maximum, policy, limit_ms), actor, role, effects = prepared
        now = int(time.time()*1000) if now is None else now
        self.db.execute("""INSERT OR IGNORE INTO point_rounds
          (sid,kind,item,epoch,revision,published,maximum,policy,limit_ms,elapsed_ms)
          VALUES (?,?,?,?,0,0,?,?,?,0)""", (*key,row["epoch"],maximum,policy,limit_ms))
        for effect in effects:
            head = self.db.execute("SELECT * FROM point_rounds WHERE sid=? AND kind=? AND item=?", key).fetchone()
            if effect["kind"] == "points-open":
                if head["published"]:
                    raise PluginError("reset before reopening published points")
                if effect["open"] and head["opened_ms"] is None:
                    self.db.execute("UPDATE point_rounds SET opened_ms=? WHERE sid=? AND kind=? AND item=?", (now,*key))
                elif not effect["open"] and head["opened_ms"] is not None:
                    elapsed = min(limit_ms, head["elapsed_ms"] + max(0, now-head["opened_ms"]))
                    self.db.execute("UPDATE point_rounds SET opened_ms=NULL,elapsed_ms=? WHERE sid=? AND kind=? AND item=?", (elapsed,*key))
            elif effect["kind"] == "publish-points":
                if policy == "quiz-v1" and head["opened_ms"] is not None:
                    raise PluginError("close the scoring clock before publishing points")
                self.db.execute("UPDATE point_rounds SET published=1,published_at=COALESCE(published_at,?) WHERE sid=? AND kind=? AND item=?",(now,*key))
            else:
                own = self.db.execute("SELECT answer_ms FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=? AND actor=?",
                                      (*key,row["epoch"],actor)).fetchone()
                count = self.db.execute("SELECT count(*) FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                        (*key,row["epoch"])).fetchone()[0]
                if not own and count >= MAX_ACTORS:
                    raise PluginError("activity credit capacity reached",code="actor-capacity")
                answer_ms = own["answer_ms"] if own else None
                if policy == "quiz-v1":
                    if role == "participant":
                        if head["published"] or head["opened_ms"] is None:
                            raise PluginError("the scoring clock is closed")
                        answer_ms = min(limit_ms, head["elapsed_ms"] + max(0, now-head["opened_ms"]))
                    elif answer_ms is None:
                        raise PluginError("evaluation has no timed participant submission")
                self.db.execute("""INSERT INTO point_credits (sid,kind,item,epoch,actor,credit,answer_ms) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(sid,kind,item,epoch,actor) DO UPDATE SET credit=excluded.credit,answer_ms=excluded.answer_ms""",
                    (*key,row["epoch"],actor,effect["credit"],answer_ms))
        self.db.execute("UPDATE point_rounds SET revision=revision+1 WHERE sid=? AND kind=? AND item=?", key)

    def heads(self, sid):
        return self.db.execute("SELECT * FROM point_rounds WHERE sid=?",(sid,)).fetchall()

    def snapshot(self, head):
        awards = {}
        if head["published"]:
            for row in self.db.execute("SELECT actor,credit,answer_ms FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                       (*self.key(head),head["epoch"])):
                credit, answer_ms = row["credit"], row["answer_ms"]
                award = {"credit":credit,"points":base_points(head["maximum"],credit,head["policy"],answer_ms,head["limit_ms"])}
                if head["policy"] == "quiz-v1":
                    award["answer_ms"] = answer_ms
                awards[row["actor"]] = award
        result = {"session":head["sid"], **{k:head[k] for k in ("kind","item","epoch","revision","maximum")},
                  "published":bool(head["published"]),"awards":awards}
        if head["policy"] == "quiz-v1":
            result.update(policy="quiz-v1",limit_ms=head["limit_ms"],revealed=head["published_at"])
        return result
