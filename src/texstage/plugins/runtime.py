# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Durable plugin state, receipts and evaluation jobs.

The server authenticates a connection before calling this host. All commands,
navigation and completions serialize on the host lock. Hooks run outside write
transactions; revision compare-and-swap detects another process using the DB.
Jobs are the durable outbox: leasing and terminal delivery survive a restart.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict

from . import PluginError
from .catalog import environment_fingerprint
from .contracts import namespace, resource_schema, validate_outcome, json_data
from .manifest import canonical, digest, read_json, validate_json, validate_json_many
from .worker import Workers, VIEW_BATCH
from .records import ActorRecords
from .points import FixedPoints, fixed_points, SCORING_EFFECTS

REQUEST = re.compile(r"[A-Za-z0-9_-]{8,128}\Z")
MAX_RECEIPTS = 100000
MAX_PENDING = 1000
MAX_RECORDS = 1024
MAX_RECORD_BYTES = 4096
MAX_RECORD_READS = 32
MAX_CACHED_RESULTS = 128
MAX_CACHE_DELIVERIES = 32


class Runtime:
    def __init__(self, path, catalog, *, workers=None, fingerprint=None):
        self.catalog = catalog
        self.workers = workers or Workers(catalog)
        self.fingerprint = fingerprint or environment_fingerprint(catalog)
        self.lock = threading.RLock()
        self.changes = {}
        self.outcomes = OrderedDict()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS items (
            sid TEXT, kind TEXT, item TEXT, epoch INTEGER, revision INTEGER,
            fingerprint TEXT, state TEXT, spec TEXT, active INTEGER,
            PRIMARY KEY(sid,kind,item));
          CREATE TABLE IF NOT EXISTS receipts (
            sid TEXT, actor TEXT, request TEXT, digest TEXT, receipt TEXT,
            PRIMARY KEY(sid,actor,request));
          CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, sid TEXT, kind TEXT, item TEXT, epoch INTEGER,
            revision INTEGER, actor TEXT, binding TEXT, correlation TEXT,
            text TEXT, status TEXT, owner TEXT, generation INTEGER, deadline REAL,
            result TEXT, delivered INTEGER DEFAULT 0,
            UNIQUE(sid,kind,item,epoch,correlation));
          CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(sid,status,delivered);
          CREATE TABLE IF NOT EXISTS records (
            sid TEXT, kind TEXT, item TEXT, epoch INTEGER, key TEXT, value TEXT,
            PRIMARY KEY(sid,kind,item,epoch,key));
        """)

        self.records = ActorRecords(self.db, catalog)
        self.points = FixedPoints(self.db, catalog)

    def close(self):
        self.workers.close()
        self.db.close()

    def _item(self, sid, kind, item):
        row = self.db.execute("SELECT * FROM items WHERE sid=? AND kind=? AND item=?", (sid, kind, item)).fetchone()
        if row is None: raise PluginError("plugin item is unavailable")
        if row["fingerprint"] != self.fingerprint:
            raise PluginError("plugin runtime changed: resume this session in its original environment", code="environment-changed")
        return row

    def _ctx(self, row, *, actor=None, role="system", now=None, record_actor=None):
        return {"item": read_json(row["spec"], limit=8 * 1024 * 1024), "epoch": row["epoch"], "revision": row["revision"],
                "actor": actor, "role": role, "timestamp": time.time() if now is None else now,
                **self.records.context(row, actor=actor if role == "participant" else record_actor, role=role),
                **self.points.context(row, actor=actor if role == "participant" else None)}

    def ensure(self, sid, kind, item, spec):
        with self.lock:
            if self.db.execute("SELECT 1 FROM items WHERE sid=? AND kind=? AND item=?", (sid, kind, item)).fetchone():
                self._item(sid, kind, item)
                return
            fixed_points(spec.get("public", {}), self.catalog.capability(kind)[1])
            fresh = {"sid": sid, "kind": kind, "item": item, "epoch": 1, "state": "{}", "spec": canonical(spec).decode()}
            state = self.workers.call(kind, "initial_state", spec,
                                      {"item": spec, "epoch": 1, "revision": 0, "role": "system",
                                       "actor": None, "timestamp": time.time(),
                                       **self.records.context(fresh), **self.points.context(fresh)})
            self.db.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)",
                            (sid, kind, item, 1, 0, self.fingerprint, canonical(state).decode(), canonical(spec).decode(), 0))

    def _records_enabled(self, kind):
        return self.catalog.capability(kind)[1].get("state_records") is True

    @staticmethod
    def _record_key(key):
        return isinstance(key, str) and 0 < len(key) <= 256 and len(canonical(key)) <= 512

    def _record_context(self, row, state, event, ctx):
        if not self._records_enabled(row["kind"]):
            return ctx
        keys = self.workers.call(row["kind"], "record_keys", state, event, ctx)
        page_keys = []
        if isinstance(keys, dict):
            if set(keys) != {"keys", "page"} or not isinstance(keys["page"], dict) or set(keys["page"]) != {"offset", "limit"}:
                raise PluginError("invalid record page")
            page = keys["page"]
            if type(page["offset"]) is not int or not 0 <= page["offset"] <= MAX_RECORDS \
                    or type(page["limit"]) is not int or not 1 <= page["limit"] <= MAX_RECORD_READS:
                raise PluginError("invalid record page bounds")
            page_keys = [r[0] for r in self.db.execute(
                "SELECT key FROM records WHERE sid=? AND kind=? AND item=? AND epoch=? ORDER BY key LIMIT ? OFFSET ?",
                (row["sid"], row["kind"], row["item"], row["epoch"], page["limit"], page["offset"]))]
            keys = keys["keys"]
        if not isinstance(keys, list) or len(keys) > MAX_RECORD_READS or any(not self._record_key(k) for k in keys):
            raise PluginError("invalid record read set")
        if len(set(keys)) != len(keys):
            raise PluginError("duplicate record read key")
        keys = list(dict.fromkeys([*keys, *page_keys]))
        if len(keys) > MAX_RECORD_READS:
            raise PluginError("record read budget exceeded")
        records = {}
        for key in keys:
            value = self.db.execute("SELECT value FROM records WHERE sid=? AND kind=? AND item=? AND epoch=? AND key=?",
                                   (row["sid"], row["kind"], row["item"], row["epoch"], key)).fetchone()
            if value is not None:
                records[key] = read_json(value["value"], limit=MAX_RECORD_BYTES)
        return ctx | {"records": records, "record_page": page_keys}

    def _receipt(self, sid, actor, request, envelope_digest):
        old = self.db.execute("SELECT digest,receipt FROM receipts WHERE sid=? AND actor=? AND request=?",
                              (sid, actor, request)).fetchone()
        if old:
            if old["digest"] != envelope_digest:
                raise PluginError("request ID was reused with a changed envelope")
            return read_json(old["receipt"])

    def _save_receipt(self, sid, actor, request, envelope_digest, receipt):
        self.db.execute("INSERT INTO receipts VALUES (?,?,?,?,?)",
                        (sid, actor, request, envelope_digest, canonical(receipt).decode()))

    def command(self, sid, actor, role, envelope, *, now=None):
        received = time.time() if now is None else now
        if role not in ("presenter", "participant"):
            raise PluginError("this role cannot dispatch plugin commands")
        fields = {"type", "item", "operation", "epoch", "request_id", "expected_revision", "payload"}
        if not isinstance(envelope, dict) or set(envelope) != fields:
            raise PluginError("invalid plugin command envelope")
        if not isinstance(envelope["request_id"], str) or not REQUEST.fullmatch(envelope["request_id"]):
            raise PluginError("invalid plugin request ID")
        if any(type(envelope[k]) is not int or envelope[k] < 0 for k in ("epoch", "expected_revision")):
            raise PluginError("invalid epoch or revision")
        kind, item, op = (envelope[k] for k in ("type", "item", "operation"))
        if not all(isinstance(x, str) and len(x) <= 160 for x in (kind, item, op)):
            raise PluginError("invalid command target")
        provider, spec = self.catalog.capability(kind)
        message = spec.get("messages", {}).get(op)
        reset = op == "_reset"
        if reset:
            if role != "presenter" or envelope["payload"] != {}:
                raise PluginError("only a presenter can reset an item")
        else:
            if message is None or role not in message["from"]:
                raise PluginError("operation is not allowed for this role")
            validate_json(read_json(provider.resources[message["schema"]]), envelope["payload"], label="command payload")
        with self.lock:
            row = self._item(sid, kind, item)
            # Authentication and schema checks above also apply to receipt replay.
            ed = digest(envelope)
            if receipt := self._receipt(sid, actor, envelope["request_id"], ed): return receipt
            if self.db.execute("SELECT count(*) FROM receipts WHERE sid=?", (sid,)).fetchone()[0] >= MAX_RECEIPTS:
                raise PluginError("session receipt budget reached; create a new session", code="session-capacity")
            error = None
            if envelope["epoch"] != row["epoch"]: error = "stale-epoch"
            elif not reset and message["revision_policy"] == "exact" and envelope["expected_revision"] != row["revision"]:
                error = "stale-revision"
            elif role == "participant" and not row["active"]: error = "item-closed"
            if error:
                receipt = {"accepted": False, "error": error, "epoch": row["epoch"], "revision": row["revision"]}
                self._save_receipt(sid, actor, envelope["request_id"], ed, receipt)
                return receipt
            target = envelope["payload"].get(message.get("record_actor_field")) if (
                not reset and message.get("record_actor_field")) else None
            ctx = self._ctx(row, actor=actor, role=role, record_actor=target or None)
            if reset:
                ctx |= {"epoch": row["epoch"] + 1, "revision": 0}
                # Initial/activation hooks see the fresh epoch, never the old roster.
                fresh = dict(row) | {"epoch": row["epoch"] + 1, "state": "{}"}
                ctx.update(self.records.context(fresh, role=role))
                ctx.update(self.points.context(fresh))
                transition = {"state": self.workers.call(kind, "initial_state", ctx["item"], ctx), "effects": []}
                if row["active"]:
                    transition = self.workers.call(kind, "transition", transition["state"], {"kind": "activate"}, ctx)
            else:
                event = {"kind": "command", "operation": op, "payload": envelope["payload"],
                         "actor": actor, "request_id": envelope["request_id"]}
                state = read_json(row["state"])
                ctx = self._record_context(row, state, event, ctx)
                transition = self.workers.call(kind, "transition", state, event, ctx)
            if isinstance(transition, dict) and set(transition) == {"refusal"}:
                code = transition["refusal"]
                if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", code):
                    raise PluginError("invalid domain refusal")
                receipt = {"accepted": False, "error": code, "epoch": row["epoch"], "revision": row["revision"]}
                self._save_receipt(sid, actor, envelope["request_id"], ed, receipt)
                return receipt
            return self._commit(row, transition, actor=actor, request=envelope["request_id"],
                                envelope_digest=ed, reset=reset, audience_actor=actor if role == "participant" else None,
                                record_actor=actor if role == "participant" else None, scoring_role=role,
                                scoring_now=int(received*1000))

    def _commit(self, row, transition, *, actor="system", request=None, envelope_digest=None,
                reset=False, active=None, delivery=None, audience_actor=None, record_actor=None, scoring_role="system", scoring_now=None):
        if not isinstance(transition, dict) or set(transition) != {"state", "effects"} or not isinstance(transition["effects"], list):
            raise PluginError("transition must contain state and effects")
        if len(canonical(transition)) > 256 * 1024 or len(transition["effects"]) > 32:
            raise PluginError("transition exceeds resource budget")
        record = self.records.prepare(row, transition["effects"], record_actor)
        scoring = self.points.prepare(row, transition["effects"], record_actor, scoring_role)
        effects = [e for e in transition["effects"] if not (isinstance(e, dict) and e.get("kind") in SCORING_EFFECTS | {"save-actor"})]
        encoded_state = canonical(transition["state"]).decode()
        if delivery and not reset and active is None and not transition["effects"] and encoded_state == row["state"]:
            # A superseded/cancelled job can legitimately leave state unchanged.
            # Persist its delivery, but do not rewrite the whole class snapshot
            # or invent a visible revision. Keep the same compare-and-swap guard.
            self.db.execute("BEGIN IMMEDIATE")
            try:
                current = self.db.execute("SELECT epoch,revision FROM items WHERE sid=? AND kind=? AND item=?",
                                          (row["sid"], row["kind"], row["item"])).fetchone()
                if current is None or tuple(current) != (row["epoch"], row["revision"]):
                    raise PluginError("item changed concurrently; retry command", code="concurrent-update")
                self.db.execute("UPDATE jobs SET delivered=1 WHERE id=?", (delivery,))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            return {"accepted": True, "epoch": row["epoch"], "revision": row["revision"], "jobs": {}}
        epoch = row["epoch"] + int(reset)
        revision = 0 if reset else row["revision"] + 1
        identity = (row["sid"], row["kind"], row["item"])
        bindings = read_json(row["spec"], limit=8 * 1024 * 1024).get("evaluations", {})
        jobs, correlations, records = [], set(), {}
        for effect in effects:
            if not isinstance(effect, dict): raise PluginError("invalid effect")
            if effect.get("kind") == "put-record":
                if not self._records_enabled(row["kind"]) or set(effect) != {"kind", "key", "value"} \
                        or not self._record_key(effect["key"]) or effect["key"] in records:
                    raise PluginError("invalid record write")
                value = canonical(effect["value"])
                if len(value) > MAX_RECORD_BYTES:
                    raise PluginError("record exceeds resource budget")
                records[effect["key"]] = value.decode()
                continue
            correlation = effect.get("correlation_id")
            if not isinstance(correlation, str) or not REQUEST.fullmatch(correlation):
                raise PluginError("invalid evaluation correlation ID")
            if effect.get("kind") == "evaluate":
                if set(effect) != {"kind", "binding", "correlation_id", "text"} or effect["binding"] not in bindings \
                        or not isinstance(effect["text"], str) or len(effect["text"]) > 2000:
                    raise PluginError("invalid evaluation effect")
                if correlation in correlations or self.db.execute(
                    "SELECT 1 FROM jobs WHERE sid=? AND kind=? AND item=? AND epoch=? AND correlation=?",
                    (*identity, epoch, correlation)).fetchone():
                    raise PluginError("evaluation correlation ID already used")
                correlations.add(correlation)
                jobs.append((uuid.uuid4().hex, effect))
            elif effect.get("kind") != "cancel-evaluation" or set(effect) != {"kind", "correlation_id"}:
                raise PluginError("unknown plugin effect")
        receipt = {"accepted": True, "epoch": epoch, "revision": revision,
                   "jobs": {e["correlation_id"]: jid for jid, e in jobs}}
        self.db.execute("BEGIN IMMEDIATE")
        try:
            # Account atomically for the slots this transition actually frees.
            # A full queue must still permit replacement of an actor's old job.
            cancellations = {e["correlation_id"] for e in transition["effects"] if e["kind"] == "cancel-evaluation"}
            if jobs:
                pending = self.db.execute("SELECT count(*) FROM jobs WHERE sid=? AND status IN ('queued','leased')",
                                          (row["sid"],)).fetchone()[0]
                freed = 0
                if reset or cancellations:
                    query = "SELECT count(*) FROM jobs WHERE sid=? AND kind=? AND item=? AND epoch=? AND status IN ('queued','leased')"
                    params = (*identity, row["epoch"])
                    if not reset:
                        query += " AND correlation IN (" + ",".join("?" for _ in cancellations) + ")"
                        params += tuple(cancellations)
                    freed = self.db.execute(query, params).fetchone()[0]
                if pending - freed + len(jobs) > MAX_PENDING:
                    raise PluginError("evaluation queue is full; request can be retried", code="queue-full")
            if records:
                total = existing = 0
                if not reset:
                    scope = " FROM records WHERE sid=? AND kind=? AND item=? AND epoch=?"
                    total = self.db.execute("SELECT count(*)" + scope, (*identity, epoch)).fetchone()[0]
                    existing = self.db.execute("SELECT count(*)" + scope + " AND key IN (" +
                        ",".join("?" for _ in records) + ")", (*identity, epoch, *records)).fetchone()[0]
                if total + len(records) - existing > MAX_RECORDS:
                    raise PluginError("item record capacity reached", code="capacity")
            changed = self.db.execute("""UPDATE items SET state=?,epoch=?,revision=?,active=?
              WHERE sid=? AND kind=? AND item=? AND epoch=? AND revision=?""",
              (encoded_state, epoch, revision, row["active"] if active is None else int(active),
               *identity, row["epoch"], row["revision"])).rowcount
            if changed != 1: raise PluginError("item changed concurrently; retry command", code="concurrent-update")
            self.records.apply(row, record, reset=reset)
            self.points.apply(row, scoring, reset=reset, now=scoring_now)
            if reset:
                self.db.execute("DELETE FROM records WHERE sid=? AND kind=? AND item=?", identity)
                self.db.execute("UPDATE jobs SET status=CASE WHEN status IN ('queued','leased') THEN 'cancelled' ELSE status END,delivered=1 WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                (*identity, row["epoch"]))
            for key, value in records.items():
                self.db.execute("INSERT INTO records VALUES (?,?,?,?,?,?) ON CONFLICT(sid,kind,item,epoch,key) DO UPDATE SET value=excluded.value",
                                (*identity, epoch, key, value))
            for jid, effect in jobs:
                binding = bindings[effect["binding"]]
                provider, engine = self.catalog.capability(binding["engine"], engine=True)
                key = self._outcome_key({"sid": row["sid"], "kind": row["kind"], "item": row["item"],
                                         "epoch": epoch, "text": effect["text"]}, provider, engine, binding)
                cached = self.outcomes.get(key) if key is not None else None
                if cached is not None:
                    self.outcomes.move_to_end(key)
                self.db.execute("""INSERT INTO jobs
                  (id,sid,kind,item,epoch,revision,actor,binding,correlation,text,status,owner,generation,deadline,result)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,0,0,?)""",
                  (jid, *identity, epoch, revision, actor, effect["binding"], effect["correlation_id"], effect["text"],
                   "succeeded" if cached is not None else "queued", cached.decode() if cached is not None else None))
            for effect in effects:
                if effect["kind"] == "cancel-evaluation":
                    self.db.execute("""UPDATE jobs SET status='cancelled',result=? WHERE sid=? AND kind=? AND item=?
                      AND epoch=? AND correlation=? AND status IN ('queued','leased')""",
                      (canonical({"status": "cancelled"}).decode(), *identity, epoch, effect["correlation_id"]))
            if request: self._save_receipt(row["sid"], actor, request, envelope_digest, receipt)
            if delivery: self.db.execute("UPDATE jobs SET delivered=1 WHERE id=?", (delivery,))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK"); raise
        spec = self.catalog.capability(row["kind"])[1]
        targeted = not reset and audience_actor is not None and spec.get("participant_updates") == "actor"
        if targeted and "broadcast_fields" in spec:
            before, after = read_json(row["state"]), transition["state"]
            # Without an explicit field list, retain the existing actor-only
            # contract: providers promise peer submissions cannot change a
            # participant's projection, even if presenter-only counters change.
            targeted = (isinstance(before, dict) and isinstance(after, dict) and
                        all(before.get(field) == after.get(field) for field in spec["broadcast_fields"]))
        sid = row["sid"]
        if not targeted:
            self.changes[sid] = None
        elif self.changes.get(sid, set()) is not None:
            self.changes.setdefault(sid, set()).add(audience_actor)
        return receipt

    def take_changes(self, sid):
        """None means all participants; a set names only affected actors."""
        with self.lock:
            return self.changes.pop(sid, set())

    def _outcome_key(self, job, provider, engine, binding):
        if engine.get("result_cache") != "by-input":
            return None
        return (job["sid"], job["kind"], job["item"], job["epoch"],
                namespace(provider, binding["engine"], engine, binding), job["text"])

    def pending(self, sid):
        with self.lock:
            return self.db.execute("SELECT 1 FROM jobs WHERE sid=? AND status='queued' LIMIT 1", (sid,)).fetchone() is not None

    def activate(self, sid, active_items):
        with self.lock:
            for row in self.db.execute("SELECT * FROM items WHERE sid=?", (sid,)).fetchall():
                wanted = (row["kind"], row["item"]) in active_items
                if wanted == bool(row["active"]): continue
                self._item(sid, row["kind"], row["item"])
                state = read_json(row["state"])
                event = {"kind": "activate" if wanted else "deactivate"}
                ctx = self._record_context(row, state, event, self._ctx(row))
                transition = self.workers.call(row["kind"], "transition", state, event, ctx)
                self._commit(row, transition, active=wanted)

    def view(self, sid, kind, item, role, surface, actor=None, *, scoring=None):
        if surface not in {"presenter": ("presenter-overlay", "presenter-controls"),
                           "projector": ("projector-overlay",), "participant": ("participant-input",)}.get(role, ()):
            raise PluginError("surface not allowed for role")
        with self.lock, self.db:
            self.db.execute("BEGIN")
            row = self._item(sid, kind, item)
            state = read_json(row["state"])
            audience = {"role": role, "surface": surface, "actor": actor}
            ctx = self._record_context(row, state, {"kind": "view", "audience": audience}, self._ctx(row, actor=actor, role=role))
            if scoring is not None and role == "participant":
                ctx["scoring"] = scoring
            data = self.workers.call(kind, "view", state, audience, ctx)
            if len(canonical(data)) > 128 * 1024: raise PluginError("view exceeds output budget")
            provider, spec = self.catalog.capability(kind)
            if "view_schemas" in spec:
                if surface not in spec["view_schemas"]:
                    raise PluginError("view surface is not declared")
                json_data(data)
                validate_json(resource_schema(provider, spec["view_schemas"][surface]), data, label="surface view")
            return {"epoch": row["epoch"], "revision": row["revision"], "data": data}

    def views(self, sid, kind, item, audiences):
        """Project one committed snapshot for independently authorized audiences."""
        surfaces = {"presenter": ("presenter-overlay", "presenter-controls"),
                    "projector": ("projector-overlay",), "participant": ("participant-input",)}
        for audience in audiences:
            if audience["surface"] not in surfaces.get(audience["role"], ()):
                raise PluginError("surface not allowed for role")
        with self.lock, self.db:
            # State, actor values and roster pages share one WAL read snapshot,
            # including when another server process commits between batches.
            self.db.execute("BEGIN")
            row = self._item(sid, kind, item)
            state, ctx = read_json(row["state"]), self._ctx(row)
            provider, spec = self.catalog.capability(kind)
            schemas = {}
            if "view_schemas" in spec:
                for surface in {a["surface"] for a in audiences}:
                    if surface not in spec["view_schemas"]:
                        raise PluginError("view surface is not declared")
                    schemas[surface] = resource_schema(provider, spec["view_schemas"][surface])
            result = []
            for offset in range(0, len(audiences), VIEW_BATCH):
                batch = audiences[offset:offset + VIEW_BATCH]
                contexts, wire_audiences = [], []
                for audience in batch:
                    role, actor = audience["role"], audience["actor"]
                    wire = {k: audience[k] for k in ("role", "actor", "surface")}
                    own = self.records.context(row, actor=actor if role == "participant" else None, role=role)
                    own.update(self.points.context(row, actor=actor if role == "participant" else None))
                    if self._records_enabled(kind):
                        selected = self._record_context(row, state, {"kind": "view", "audience": wire},
                                                        ctx | own | {"role": role, "actor": actor})
                        own.update(records=selected["records"], record_page=selected["record_page"])
                    if role == "participant" and audience.get("scoring") is not None:
                        own["scoring"] = audience["scoring"]
                    contexts.append(own); wire_audiences.append(wire)
                data = self.workers.views(kind, state, wire_audiences, ctx | {"_audience_contexts": contexts})
                if len(data) != len(batch): raise PluginError("invalid view response count")
                by_surface = {}
                for audience, value in zip(batch, data):
                    if len(canonical(value)) > 128 * 1024: raise PluginError("view exceeds output budget")
                    if schemas:
                        json_data(value)
                        by_surface.setdefault(audience["surface"], []).append(value)
                    result.append({"epoch": row["epoch"], "revision": row["revision"], "data": value})
                for surface, values in by_surface.items():
                    validate_json_many(schemas[surface], values, label="surface view")
            return result


    def lease(self, sid, owner, *, now=None, limit=2, adaptive=False):
        now = time.time() if now is None else now
        with self.lock, self.db:
            if adaptive:
                # Presenter throughput policy, not an engine permission. Use at
                # most eight fresh workers for a very large backlog; small queues
                # keep the two-job batch. Count only work eligible to lease.
                waiting = self.db.execute("""SELECT count(*) FROM jobs WHERE sid=? AND
                    (status='queued' OR (status='leased' AND deadline<?))""", (sid, now)).fetchone()[0]
                limit = 8 if waiting >= 128 else 4 if waiting >= 32 else 2
            # One bounded work batch is durable before the caller sees it.
            # Preserve FULL synchronization without one fsync per cache hit.
            self.db.execute("BEGIN IMMEDIATE")
            jobs = self.db.execute("""SELECT * FROM jobs WHERE sid=? AND
               (status='queued' OR (status='leased' AND deadline<?)) ORDER BY rowid LIMIT ?""", (sid, now, limit + MAX_CACHE_DELIVERIES)).fetchall()
            result = []
            cached = 0
            for job in jobs:
                row = self._item(sid, job["kind"], job["item"])
                if job["epoch"] != row["epoch"]: continue
                if job["generation"] >= 3:
                    self.db.execute("UPDATE jobs SET status='failed',result=? WHERE id=?", ('{"status":"timeout"}', job["id"]))
                    continue
                binding = read_json(row["spec"], limit=8 * 1024 * 1024)["evaluations"][job["binding"]]
                p, engine = self.catalog.capability(binding["engine"], engine=True)
                key = self._outcome_key(job, p, engine, binding)
                if key is not None and key in self.outcomes and cached < MAX_CACHE_DELIVERIES:
                    raw = self.outcomes[key]
                    # Only validated successful outcomes from an accepted lease
                    # enter this immutable cache. Every actor still has a durable
                    # job and its own guarded transition/receipt/private projection.
                    self.db.execute("UPDATE jobs SET status='succeeded',result=?,owner=NULL,deadline=0 WHERE id=? AND status IN ('queued','leased')",
                                    (raw.decode(), job["id"]))
                    self.outcomes.move_to_end(key); cached += 1
                    if cached == MAX_CACHE_DELIVERIES:
                        break
                    continue
                if len(result) >= limit:
                    break
                generation = job["generation"] + 1
                updated = self.db.execute("""UPDATE jobs SET status='leased',owner=?,generation=?,deadline=?
                    WHERE id=? AND generation=? AND status IN ('queued','leased')""",
                    (owner, generation, now + 120, job["id"], job["generation"])).rowcount
                if not updated: continue
                result.append({"id": job["id"], "generation": generation, "epoch": job["epoch"],
                               "text": job["text"], "binding": binding,
                               "namespace": namespace(p, binding["engine"], engine, binding)})
            return result

    def release(self, sid, owner):
        """Requeue a disconnected evaluator's work; retain its retry count.

        Clearing ownership also rejects an old result before the next lease.
        Expiry remains the fallback when a disconnect cannot be observed.
        """
        with self.lock:
            return self.db.execute("""UPDATE jobs SET status='queued',owner=NULL,deadline=0
                WHERE sid=? AND owner=? AND status='leased'""", (sid, owner)).rowcount

    def finish(self, sid, owner, result, *, now=None):
        now = time.time() if now is None else now
        if not isinstance(result, dict) or set(result) != {"id", "generation", "epoch", "outcome"}:
            raise PluginError("invalid evaluation result")
        if not isinstance(result["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", result["id"]) or \
                any(type(result[k]) is not int or result[k] < 1 for k in ("epoch", "generation")):
            raise PluginError("invalid evaluation job identity")
        outcome = result["outcome"]
        if not isinstance(outcome, dict) or outcome.get("status") not in ("ok", "syntax", "error", "refused", "timeout") \
                or len(canonical(outcome)) > 12 * 1024:
            raise PluginError("invalid evaluation outcome")
        with self.lock:
            job = self.db.execute("SELECT * FROM jobs WHERE id=? AND sid=?", (result["id"], sid)).fetchone()
            if job is None: return False
            row = self._item(sid, job["kind"], job["item"])
            binding = read_json(row["spec"], limit=8 * 1024 * 1024)["evaluations"][job["binding"]]
            provider, engine = self.catalog.capability(binding["engine"], engine=True)
            validate_outcome(outcome, provider, engine,
                             namespace(provider, binding["engine"], engine, binding),
                             references=bool(binding.get("references")))
            accepted = bool(self.db.execute("""UPDATE jobs SET status=?,result=? WHERE id=? AND sid=? AND owner=?
               AND status='leased' AND generation=? AND epoch=? AND deadline>=?""",
               ("succeeded" if outcome["status"] == "ok" else "failed", canonical(outcome).decode(), result["id"],
                sid, owner, result["generation"], result["epoch"], now)).rowcount)
            key = self._outcome_key(job, provider, engine, binding)
            if accepted and outcome["status"] == "ok" and key is not None:
                self.outcomes[key] = canonical(outcome)
                self.outcomes.move_to_end(key)
                while len(self.outcomes) > MAX_CACHED_RESULTS:
                    self.outcomes.popitem(last=False)
            return accepted

    def drain(self, sid):
        with self.lock:
            for job in self.db.execute("""SELECT * FROM jobs WHERE sid=? AND delivered=0
              AND status IN ('succeeded','failed','cancelled') ORDER BY rowid""", (sid,)).fetchall():
                row = self._item(sid, job["kind"], job["item"])
                if job["epoch"] != row["epoch"]:
                    self.db.execute("UPDATE jobs SET delivered=1 WHERE id=?", (job["id"],)); continue
                event = {"kind": "evaluation.finished", "job_id": job["id"], "correlation_id": job["correlation"],
                         "actor": job["actor"], "binding": job["binding"], "outcome": read_json(job["result"])}
                state = read_json(row["state"])
                ctx = self._record_context(row, state, event, self._ctx(row, record_actor=job["actor"]))
                transition = self.workers.call(row["kind"], "transition", state, event, ctx)
                self._commit(row, transition, actor=job["actor"], delivery=job["id"], audience_actor=job["actor"], record_actor=job["actor"])

    def archive(self, sid):
        """Presenter-authorized callers only; includes private plugin state."""
        with self.lock:
            return {"format": 1, "runtime": self.fingerprint,
                    "items": [dict(r) for r in self.db.execute("SELECT * FROM items WHERE sid=?", (sid,))],
                    "jobs": [dict(r) for r in self.db.execute("SELECT * FROM jobs WHERE sid=?", (sid,))],
                    "point_rounds": [dict(r) for r in self.points.heads(sid)],
                    "point_credits": [dict(r) for r in self.db.execute("SELECT * FROM point_credits WHERE sid=?", (sid,))],
                    "records": [dict(r) for r in self.db.execute("SELECT * FROM records WHERE sid=?", (sid,))],
                    "actor_records": [dict(r) for r in self.db.execute("SELECT * FROM actor_records WHERE sid=?", (sid,))]}
