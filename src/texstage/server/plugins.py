# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Authentication-aware bridge to the experimental plugin host."""
from texstage.plugins import PluginError
from pathlib import Path
from texstage.plugins.assets import public_asset, MIME
from texstage.plugins.manifest import read_json
from texstage.plugins.runtime import Runtime


class PluginHost:
    def __init__(self, server, catalog):
        self.server, self.catalog = server, catalog
        self.runtime = Runtime(server.config.data_dir / "plugins.sqlite3", catalog) if catalog.providers else None

    def close(self):
        if self.runtime: self.runtime.close()

    def sync(self, sid):
        session = self.server.engine.sessions.get(sid)
        if session is None or session.ended is not None: raise PluginError("session has ended")
        bundle = self.server.bundles.get(session.bundle)
        if bundle is None: raise PluginError("session bundle is unavailable")
        if bundle.deck_json.get("format") != 3: return session, bundle, []
        if self.runtime is None: raise PluginError("plugins are not enabled")
        current = bundle.slides.get(session.slide)
        active = []
        for kind, entries in bundle.items.items():
            if kind not in self.catalog.types: continue
            for item, public in entries.items():
                private = bundle.keys["items"][kind][item]
                self.runtime.ensure(sid, kind, item, {"public": public, **private})
                if current and item in current.shows.get(kind, ()) and not session.finished:
                    active.append((kind, item))
        self.runtime.activate(sid, set(active))
        self.runtime.drain(sid)
        return session, bundle, active

    def identity(self, conn):
        session = self.server.engine.sessions.get(conn.session)
        if session is None or session.ended is not None: raise PluginError("session has ended")
        if conn.role == "player":
            player = session.players.get(conn.player)
            if player is None or player.kicked: raise PluginError("participant is no longer in this session")
            return "participant", player.id
        if conn.role not in ("stage", "host", "display") or conn.lecturer != session.owner:
            raise PluginError("session authentication is required")
        return ("projector" if conn.role == "display" else "presenter"), "presenter:" + conn.lecturer

    def view(self, conn):
        if self.runtime is None: return {}
        role, actor = self.identity(conn)
        _, bundle, active = self.sync(conn.session)
        result = []
        for kind, item in active:
            provider, spec = self.catalog.capability(kind)
            surfaces = [s for s in spec["views"] if s.startswith(role + "-")]
            result.append({"type": kind, "item": item, "public": bundle.items[kind][item],
                           "assets": {n: f"/plugins/{provider.payload}/{n}" for n in provider.resources if Path(n).suffix.lower() in MIME}
                           | {n: f"/bundle/{bundle.id}/{path}" for n, path in bundle.items[kind][item].get("plugin_assets", {}).items()},
                           "modules": {s: f"/plugins/{provider.payload}/{spec['views'][s]}" for s in surfaces},
                           "views": {s: self.runtime.view(conn.session, kind, item, role, s, actor) for s in surfaces}})
        return {"plugins": {"catalog": self.catalog.fingerprint, "items": result}}

    def safe_view(self, conn):
        try:
            return self.view(conn)
        except PluginError as exc:
            # Preserve ordinary navigation and the static slide if a provider fails.
            return {"plugins": {"items": [], "error": str(exc) if conn.role in ("host", "stage") else "Activity unavailable"}}

    def handle(self, conn, message):
        role, actor = self.identity(conn)
        if self.runtime is None: raise PluginError("no plugins are enabled")
        _, bundle, _ = self.sync(conn.session)
        operation = message["t"]
        if operation == "plugin.command":
            envelope = message.get("command")
            if not isinstance(envelope, dict) or envelope.get("item") not in bundle.items.get(envelope.get("type"), {}):
                raise PluginError("item does not belong to this session")
            result = self.runtime.command(conn.session, actor, role, envelope)
            self.server.push(conn.session)
            return {"receipt": result}
        if operation not in ("plugin.work", "plugin.result") or conn.role != "stage":
            raise PluginError("only the presenter window can evaluate plugin jobs")
        if operation == "plugin.work":
            jobs = self.runtime.lease(conn.session, conn.key)
            for job in jobs:
                p, engine = self.catalog.capability(job["binding"]["engine"], engine=True)
                job["engine"] = engine | {"url": f"/plugins/{p.payload}/{engine['module']}",
                                           "assets": {n: f"/plugins/{p.payload}/{n}" for n in engine.get("assets", [])}}
            return {"jobs": jobs}
        accepted = self.runtime.finish(conn.session, conn.key, message.get("result"))
        self.runtime.drain(conn.session)
        self.server.push(conn.session)
        return {"accepted": accepted}

    def asset(self, payload, name):
        for provider in self.catalog.providers.values():
            if provider.payload == payload and name in provider.resources:
                return provider.resources[name], public_asset(name)
        raise PluginError("unknown plugin asset")
