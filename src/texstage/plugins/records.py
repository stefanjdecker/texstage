# SPDX-License-Identifier: Apache-2.0
"""Opt-in, item/epoch-scoped actor records with bounded hook projections."""
from . import PluginError
from .contracts import resource_schema
from .manifest import canonical, read_json, validate_json

VALUE_BYTES = 4096
SUMMARY_BYTES = 512


class ActorRecords:
    def __init__(self, db, catalog):
        self.db, self.catalog = db, catalog
        db.executescript("""
          CREATE TABLE IF NOT EXISTS actor_records (
            sid TEXT, kind TEXT, item TEXT, epoch INTEGER, actor TEXT,
            number INTEGER, value TEXT, summary TEXT,
            PRIMARY KEY(sid,kind,item,epoch,actor),
            UNIQUE(sid,kind,item,epoch,number));
        """)

    def policy(self, kind):
        return self.catalog.capability(kind)[1].get("actor_records")

    @staticmethod
    def identity(row):
        return row["sid"], row["kind"], row["item"], row["epoch"]

    def count(self, row):
        return self.db.execute(
            "SELECT count(*) FROM actor_records WHERE sid=? AND kind=? AND item=? AND epoch=?",
            self.identity(row)).fetchone()[0]

    @staticmethod
    def actor(value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 256 or
                len(canonical(value)) > 1024):
            raise PluginError("invalid actor record identity")
        return value

    def context(self, row, *, actor=None, role="system"):
        policy = self.policy(row["kind"])
        if not policy:
            return {}
        count = self.count(row)
        own = None
        if actor is not None:
            self.actor(actor)
            own = self.db.execute(
                "SELECT number,value FROM actor_records WHERE sid=? AND kind=? AND item=? AND epoch=? AND actor=?",
                (*self.identity(row), actor)).fetchone()
        context = {"records": {"count": count, "actor": actor,
                              "number": own["number"] if own else count + 1,
                              "value": read_json(own["value"]) if own else None}}
        if role == "presenter":
            state = read_json(row["state"])
            page = state.get(policy["page_field"], 0)
            if type(page) is not int or page < 0:
                raise PluginError("invalid actor record page")
            size = policy["page_size"]
            pages = max(1, (count + size - 1) // size)
            page = min(page, pages - 1)
            rows = self.db.execute(
                """SELECT actor,number,summary FROM actor_records
                   WHERE sid=? AND kind=? AND item=? AND epoch=?
                   ORDER BY number LIMIT ? OFFSET ?""",
                (*self.identity(row), size, page * size)).fetchall()
            context["record_page"] = {"page": page, "pages": pages, "total": count,
                                     "rows": [{"actor": r["actor"], "number": r["number"],
                                               "summary": read_json(r["summary"])} for r in rows]}
        return context

    def prepare(self, row, effects, actor):
        saves = [e for e in effects if isinstance(e, dict) and e.get("kind") == "save-actor"]
        if not saves:
            return None
        policy = self.policy(row["kind"])
        if not policy or len(saves) != 1 or actor is None:
            raise PluginError("actor record write is not authorized")
        self.actor(actor)
        effect = saves[0]
        if set(effect) != {"kind", "value", "summary"}:
            raise PluginError("invalid actor record effect")
        provider, _ = self.catalog.capability(row["kind"])
        for field, limit in (("value", VALUE_BYTES), ("summary", SUMMARY_BYTES)):
            if len(canonical(effect[field])) > limit:
                raise PluginError("actor record exceeds resource budget")
            validate_json(resource_schema(provider, policy[field + "_schema"]), effect[field],
                          label="actor record " + field)
        return actor, effect

    def apply(self, row, prepared, *, reset=False):
        # Called only within the same transaction as item CAS, jobs and receipt.
        if reset:
            self.db.execute("DELETE FROM actor_records WHERE sid=? AND kind=? AND item=?",
                            self.identity(row)[:3])
        if prepared is None:
            return
        if reset:
            raise PluginError("reset cannot write an actor record")
        actor, effect = prepared
        old = self.db.execute(
            "SELECT number FROM actor_records WHERE sid=? AND kind=? AND item=? AND epoch=? AND actor=?",
            (*self.identity(row), actor)).fetchone()
        if old is None:
            count = self.count(row)
            if count >= self.policy(row["kind"])["capacity"]:
                raise PluginError("actor record capacity reached", code="actor-capacity")
            number = count + 1
        else:
            # Saving feedback or replacing an answer never changes admission or
            # response order. Keep the existing slot without recounting the class.
            number = old["number"]
        self.db.execute(
            """INSERT INTO actor_records VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(sid,kind,item,epoch,actor)
               DO UPDATE SET value=excluded.value,summary=excluded.summary""",
            (*self.identity(row), actor, number,
             canonical(effect["value"]).decode(), canonical(effect["summary"]).decode()))
