# SPDX-License-Identifier: Apache-2.0
"""Host-owned fixed points: private credits and a durable publication ledger."""
from . import PluginError
from .manifest import read_json
from .records import ActorRecords

MAX_POINTS = 10000
MAX_ACTORS = 1000


def fixed_points(public, spec):
    policy = spec.get("scoring")
    if policy is None:
        return None
    value = public.get(policy["points_field"])
    if type(value) is not int or not 0 <= value <= MAX_POINTS:
        raise PluginError("activity points must be an integer from 0 to 10000")
    return value


class FixedPoints:
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

    def maximum(self, row):
        _, spec = self.catalog.capability(row["kind"])
        return fixed_points(read_json(row["spec"], limit=8*1024*1024)["public"], spec) if "scoring" in spec else None

    @staticmethod
    def key(row):
        return row["sid"], row["kind"], row["item"]

    def context(self, row, actor=None):
        maximum = self.maximum(row)
        if maximum is None:
            return {}
        round_ = self.db.execute("SELECT * FROM point_rounds WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                 (*self.key(row), row["epoch"])).fetchone()
        released = bool(round_ and round_["published"])
        own = None
        if actor is not None and released:
            own = self.db.execute("SELECT credit FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=? AND actor=?",
                                   (*self.key(row), row["epoch"], actor)).fetchone()
        awarded = (maximum * own["credit"] + 500)//1000 if own and own["credit"] is not None else None
        return {"scoring": {"maximum": maximum, "released": released, "awarded": awarded}}

    def prepare(self, row, effects, actor, role):
        selected = [e for e in effects if isinstance(e, dict) and e.get("kind") in ("set-credit", "publish-points")]
        if not selected:
            return None
        maximum = self.maximum(row)
        if maximum is None:
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
            elif role != "presenter" or set(effect) != {"kind"}:
                raise PluginError("only presenter commands can publish points")
        return maximum, actor, selected

    def apply(self, row, prepared, *, reset=False):
        # Shares the item CAS, records, jobs and receipt transaction.
        key = self.key(row)
        if reset:
            if prepared is not None:
                raise PluginError("reset cannot issue scoring effects")
            self.db.execute("DELETE FROM point_credits WHERE sid=? AND kind=? AND item=?", key)
            self.db.execute("UPDATE point_rounds SET epoch=?,revision=0,published=0 WHERE sid=? AND kind=? AND item=?",
                            (row["epoch"]+1, *key))
            return
        if prepared is None or prepared[0] == 0:
            return  # explicit practice mode never creates or changes game points
        maximum, actor, effects = prepared
        self.db.execute("INSERT OR IGNORE INTO point_rounds VALUES (?,?,?,?,0,0,?)", (*key,row["epoch"],maximum))
        for effect in effects:
            if effect["kind"] == "publish-points":
                self.db.execute("UPDATE point_rounds SET published=1 WHERE sid=? AND kind=? AND item=?",key)
            else:
                own = self.db.execute("SELECT 1 FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=? AND actor=?",
                                      (*key,row["epoch"],actor)).fetchone()
                count = self.db.execute("SELECT count(*) FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                        (*key,row["epoch"])).fetchone()[0]
                if not own and count >= MAX_ACTORS:
                    raise PluginError("activity credit capacity reached",code="actor-capacity")
                self.db.execute("INSERT INTO point_credits VALUES (?,?,?,?,?,?) ON CONFLICT(sid,kind,item,epoch,actor) DO UPDATE SET credit=excluded.credit",
                                (*key,row["epoch"],actor,effect["credit"]))
        self.db.execute("UPDATE point_rounds SET revision=revision+1 WHERE sid=? AND kind=? AND item=?", key)

    def heads(self, sid):
        return self.db.execute("SELECT * FROM point_rounds WHERE sid=?",(sid,)).fetchall()

    def snapshot(self, head):
        awards = {}
        if head["published"]:
            for row in self.db.execute("SELECT actor,credit FROM point_credits WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                       (*self.key(head),head["epoch"])):
                credit = row["credit"]
                awards[row["actor"]] = {"credit":credit,"points":(head["maximum"]*credit+500)//1000 if credit is not None else 0}
        return {"session":head["sid"], **{k:head[k] for k in ("kind","item","epoch","revision","maximum")},
                "published":bool(head["published"]),"awards":awards}
