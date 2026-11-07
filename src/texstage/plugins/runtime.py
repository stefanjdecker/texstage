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

from . import PluginError
from .catalog import environment_fingerprint
from .contracts import namespace, resource_schema, validate_outcome, json_data
from .manifest import canonical, digest, read_json, validate_json
from .worker import Workers

REQUEST = re.compile(r"[A-Za-z0-9_-]{8,128}\Z")
MAX_RECEIPTS = 100000
MAX_PENDING = 1000


class Runtime:
    def __init__(self, path, catalog, *, workers=None, fingerprint=None):
        self.catalog = catalog
        self.workers = workers or Workers(catalog)
        self.fingerprint = fingerprint or environment_fingerprint(catalog)
        self.lock = threading.RLock()
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
        """)

    def close(self):
        self.workers.close()
        self.db.close()

    def _item(self, sid, kind, item):
        row = self.db.execute("SELECT * FROM items WHERE sid=? AND kind=? AND item=?", (sid, kind, item)).fetchone()
        if row is None: raise PluginError("plugin item is unavailable")
        if row["fingerprint"] != self.fingerprint:
            raise PluginError("plugin runtime changed: resume this session in its original environment", code="environment-changed")
        return row

    def _ctx(self, row, *, actor=None, role="system", now=None):
        return {"item": read_json(row["spec"], limit=8 * 1024 * 1024), "epoch": row["epoch"], "revision": row["revision"],
                "actor": actor, "role": role, "timestamp": time.time() if now is None else now}

    def ensure(self, sid, kind, item, spec):
        with self.lock:
            if self.db.execute("SELECT 1 FROM items WHERE sid=? AND kind=? AND item=?", (sid, kind, item)).fetchone():
                self._item(sid, kind, item)
                return
            state = self.workers.call(kind, "initial_state", spec,
                                      {"item": spec, "epoch": 1, "revision": 0, "role": "system",
                                       "actor": None, "timestamp": time.time()})
            self.db.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)",
                            (sid, kind, item, 1, 0, self.fingerprint, canonical(state).decode(), canonical(spec).decode(), 0))

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

    def command(self, sid, actor, role, envelope):
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
            ctx = self._ctx(row, actor=actor, role=role)
            if reset:
                ctx |= {"epoch": row["epoch"] + 1, "revision": 0}
                transition = {"state": self.workers.call(kind, "initial_state", ctx["item"], ctx), "effects": []}
                if row["active"]:
                    transition = self.workers.call(kind, "transition", transition["state"], {"kind": "activate"}, ctx)
            else:
                event = {"kind": "command", "operation": op, "payload": envelope["payload"],
                         "actor": actor, "request_id": envelope["request_id"]}
                transition = self.workers.call(kind, "transition", read_json(row["state"]), event, ctx)
            if isinstance(transition, dict) and set(transition) == {"refusal"}:
                code = transition["refusal"]
                if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", code):
                    raise PluginError("invalid domain refusal")
                receipt = {"accepted": False, "error": code, "epoch": row["epoch"], "revision": row["revision"]}
                self._save_receipt(sid, actor, envelope["request_id"], ed, receipt)
                return receipt
            return self._commit(row, transition, actor=actor, request=envelope["request_id"],
                                envelope_digest=ed, reset=reset)

    def _commit(self, row, transition, *, actor="system", request=None, envelope_digest=None,
                reset=False, active=None, delivery=None):
        if not isinstance(transition, dict) or set(transition) != {"state", "effects"} or not isinstance(transition["effects"], list):
            raise PluginError("transition must contain state and effects")
        if len(canonical(transition)) > 256 * 1024 or len(transition["effects"]) > 32:
            raise PluginError("transition exceeds resource budget")
        epoch = row["epoch"] + int(reset)
        revision = 0 if reset else row["revision"] + 1
        identity = (row["sid"], row["kind"], row["item"])
        bindings = read_json(row["spec"], limit=8 * 1024 * 1024).get("evaluations", {})
        jobs, correlations = [], set()
        for effect in transition["effects"]:
            if not isinstance(effect, dict): raise PluginError("invalid effect")
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
            pending = self.db.execute("SELECT count(*) FROM jobs WHERE sid=? AND status IN ('queued','leased')",
                                      (row["sid"],)).fetchone()[0]
            cancellations = {e["correlation_id"] for e in transition["effects"] if e["kind"] == "cancel-evaluation"}
            old_jobs = self.db.execute("""SELECT correlation FROM jobs WHERE sid=? AND kind=? AND item=?
              AND epoch=? AND status IN ('queued','leased')""", (*identity, row["epoch"])).fetchall()
            freed = len(old_jobs) if reset else sum(job["correlation"] in cancellations for job in old_jobs)
            if pending - freed + len(jobs) > MAX_PENDING:
                raise PluginError("evaluation queue is full; request can be retried", code="queue-full")
            changed = self.db.execute("""UPDATE items SET state=?,epoch=?,revision=?,active=?
              WHERE sid=? AND kind=? AND item=? AND epoch=? AND revision=?""",
              (canonical(transition["state"]).decode(), epoch, revision, row["active"] if active is None else int(active),
               *identity, row["epoch"], row["revision"])).rowcount
            if changed != 1: raise PluginError("item changed concurrently; retry command", code="concurrent-update")
            if reset:
                self.db.execute("UPDATE jobs SET status=CASE WHEN status IN ('queued','leased') THEN 'cancelled' ELSE status END,delivered=1 WHERE sid=? AND kind=? AND item=? AND epoch=?",
                                (*identity, row["epoch"]))
            for jid, effect in jobs:
                self.db.execute("""INSERT INTO jobs
                  (id,sid,kind,item,epoch,revision,actor,binding,correlation,text,status,owner,generation,deadline)
                  VALUES (?,?,?,?,?,?,?,?,?,?,'queued',NULL,0,0)""",
                  (jid, *identity, epoch, revision, actor, effect["binding"], effect["correlation_id"], effect["text"]))
            for effect in transition["effects"]:
                if effect["kind"] == "cancel-evaluation":
                    self.db.execute("""UPDATE jobs SET status='cancelled',result=? WHERE sid=? AND kind=? AND item=?
                      AND epoch=? AND correlation=? AND status IN ('queued','leased')""",
                      (canonical({"status": "cancelled"}).decode(), *identity, epoch, effect["correlation_id"]))
            if request: self._save_receipt(row["sid"], actor, request, envelope_digest, receipt)
            if delivery: self.db.execute("UPDATE jobs SET delivered=1 WHERE id=?", (delivery,))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK"); raise
        return receipt

    def activate(self, sid, active_items):
        with self.lock:
            for row in self.db.execute("SELECT * FROM items WHERE sid=?", (sid,)).fetchall():
                wanted = (row["kind"], row["item"]) in active_items
                if wanted == bool(row["active"]): continue
                self._item(sid, row["kind"], row["item"])
                transition = self.workers.call(row["kind"], "transition", read_json(row["state"]),
                                                {"kind": "activate" if wanted else "deactivate"}, self._ctx(row))
                self._commit(row, transition, active=wanted)

    def view(self, sid, kind, item, role, surface, actor=None):
        if surface not in {"presenter": ("presenter-overlay", "presenter-controls"),
                           "projector": ("projector-overlay",), "participant": ("participant-input",)}.get(role, ()):
            raise PluginError("surface not allowed for role")
        with self.lock:
            row = self._item(sid, kind, item)
            data = self.workers.call(kind, "view", read_json(row["state"]),
                                     {"role": role, "surface": surface, "actor": actor}, self._ctx(row, actor=actor, role=role))
            if len(canonical(data)) > 128 * 1024: raise PluginError("view exceeds output budget")
            provider, spec = self.catalog.capability(kind)
            if "view_schemas" in spec:
                if surface not in spec["view_schemas"]:
                    raise PluginError("view surface is not declared")
                json_data(data)
                validate_json(resource_schema(provider, spec["view_schemas"][surface]), data, label="surface view")
            return {"epoch": row["epoch"], "revision": row["revision"], "data": data}

    def lease(self, sid, owner, *, now=None, limit=2):
        now = time.time() if now is None else now
        with self.lock:
            jobs = self.db.execute("""SELECT * FROM jobs WHERE sid=? AND
               (status='queued' OR (status='leased' AND deadline<?)) ORDER BY rowid LIMIT ?""", (sid, now, limit)).fetchall()
            result = []
            for job in jobs:
                row = self._item(sid, job["kind"], job["item"])
                if job["epoch"] != row["epoch"]: continue
                if job["generation"] >= 3:
                    self.db.execute("UPDATE jobs SET status='failed',result=? WHERE id=?", ('{"status":"timeout"}', job["id"]))
                    continue
                generation = job["generation"] + 1
                updated = self.db.execute("""UPDATE jobs SET status='leased',owner=?,generation=?,deadline=?
                    WHERE id=? AND generation=? AND status IN ('queued','leased')""",
                    (owner, generation, now + 120, job["id"], job["generation"])).rowcount
                if not updated: continue
                binding = read_json(row["spec"], limit=8 * 1024 * 1024)["evaluations"][job["binding"]]
                p, engine = self.catalog.capability(binding["engine"], engine=True)
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
            return bool(self.db.execute("""UPDATE jobs SET status=?,result=? WHERE id=? AND sid=? AND owner=?
               AND status='leased' AND generation=? AND epoch=? AND deadline>=?""",
               ("succeeded" if outcome["status"] == "ok" else "failed", canonical(outcome).decode(), result["id"],
                sid, owner, result["generation"], result["epoch"], now)).rowcount)

    def drain(self, sid):
        with self.lock:
            for job in self.db.execute("""SELECT * FROM jobs WHERE sid=? AND delivered=0
              AND status IN ('succeeded','failed','cancelled') ORDER BY rowid""", (sid,)).fetchall():
                row = self._item(sid, job["kind"], job["item"])
                if job["epoch"] != row["epoch"]:
                    self.db.execute("UPDATE jobs SET delivered=1 WHERE id=?", (job["id"],)); continue
                event = {"kind": "evaluation.finished", "job_id": job["id"], "correlation_id": job["correlation"],
                         "actor": job["actor"], "binding": job["binding"], "outcome": read_json(job["result"])}
                transition = self.workers.call(row["kind"], "transition", read_json(row["state"]), event, self._ctx(row))
                self._commit(row, transition, actor=job["actor"], delivery=job["id"])

    def archive(self, sid):
        """Presenter-authorized callers only; includes private plugin state."""
        with self.lock:
            return {"format": 1, "runtime": self.fingerprint,
                    "items": [dict(r) for r in self.db.execute("SELECT * FROM items WHERE sid=?", (sid,))],
                    "jobs": [dict(r) for r in self.db.execute("SELECT * FROM jobs WHERE sid=?", (sid,))]}
