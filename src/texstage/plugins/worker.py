# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""A killable, enabled-provider process. This is isolation, not an OS sandbox."""
from __future__ import annotations

import contextlib
import copy
import importlib
import queue
import subprocess
import sys
import threading

from . import PluginError
from .catalog import discover
from .manifest import MAX_JSON, canonical, read_json

FRAME_MAX = 8 * 1024 * 1024  # includes item data and a seed of up to 2 MiB
VIEW_BATCH = 32


class Worker:
    def __init__(self, provider):
        self.provider = provider
        self.process = None
        self.lock = threading.Lock()

    def _read(self, process, responses):
        try:
            while line := process.stdout.readline(FRAME_MAX + 2):
                responses.put(read_json(line, limit=FRAME_MAX))
        except Exception:
            responses.put({"error": "invalid worker output"})
        finally:
            responses.put({"error": "worker exited"})

    def _response(self, timeout):
        try:
            result = self.responses.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise PluginError(f"{self.provider.id}: hook timed out; worker terminated", code="worker-timeout") from None
        if "error" in result:
            self.close()
            raise PluginError(f"{self.provider.id}: {result['error']}")
        return result

    def _start(self):
        self.provider.verify()
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-m", "texstage.plugins.worker", self.provider.id,
             self.provider.version, self.provider.payload], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        self.reader = threading.Thread(target=self._read, args=(self.process, self.responses), daemon=True)
        self.reader.start()
        if self._response(10) != {"ready": self.provider.payload}:
            self.close()
            raise PluginError("worker startup identity mismatch")

    def call(self, capability, method, args, *, timeout=.25):
        with self.lock:
            if self.process is None: self._start()
            raw = canonical({"capability": capability, "method": method, "args": args})
            if len(raw) > FRAME_MAX:
                raise PluginError("hook input exceeds JSON budget")
            try:
                self.process.stdin.write(raw + b"\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.close()
                raise PluginError("plugin worker unavailable; request can be retried", code="worker-unavailable") from None
            return self._response(timeout)["result"]

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
            if self.reader is not threading.current_thread(): self.reader.join(timeout=1)
            for stream in (process.stdin, process.stdout):
                if stream: stream.close()

    def views(self, capability, state, audiences, ctx):
        """Send one snapshot; receive separately time-bounded, isolated views.

        This is private host IPC, not an additional provider hook. Every view
        still gets fresh input objects and its own ordinary 250 ms deadline.
        """
        if not 1 <= len(audiences) <= VIEW_BATCH:
            raise PluginError("invalid view batch size")
        with self.lock:
            if self.process is None: self._start()
            raw = canonical({"capability": capability, "method": "view_batch", "args": [state, audiences, ctx]})
            if len(raw) > FRAME_MAX: raise PluginError("hook input exceeds JSON budget")
            try:
                self.process.stdin.write(raw + b"\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.close()
                raise PluginError("plugin worker unavailable; request can be retried", code="worker-unavailable") from None
            result = []
            for index in range(len(audiences)):
                response = self._response(.25)
                if response.get("view") != index:
                    self.close()
                    raise PluginError("invalid view response order")
                result.append(response["result"])
            return result


class Workers:
    def __init__(self, catalog):
        self.catalog, self.workers = catalog, {}
        self.failures = {}

    def call(self, cid, method, *args):
        provider, spec = self.catalog.capability(cid)
        if self.failures.get(provider.id, 0) >= 3:
            raise PluginError(f"{provider.id}: worker quarantined after repeated failures; restart the server after fixing the provider", code="worker-unavailable")
        worker = self.workers.setdefault(provider.id, Worker(provider))
        try:
            return worker.call(cid, method, args, timeout=2 if method in ("prepare", "prepare_source") else .25)
        except PluginError:
            self.failures[provider.id] = self.failures.get(provider.id, 0) + 1
            raise

    def close(self):
        for worker in self.workers.values(): worker.close()

    def views(self, cid, state, audiences, ctx):
        provider, _ = self.catalog.capability(cid)
        if self.failures.get(provider.id, 0) >= 3:
            raise PluginError(f"{provider.id}: worker quarantined after repeated failures; restart the server after fixing the provider", code="worker-unavailable")
        worker = self.workers.setdefault(provider.id, Worker(provider))
        try:
            return worker.views(cid, state, audiences, ctx)
        except PluginError:
            self.failures[provider.id] = self.failures.get(provider.id, 0) + 1
            raise


def main():
    from texstage.plugin_api.v1 import PluginV1, json_value
    pid, version, payload = sys.argv[1:]
    providers = {p.id: p for p in discover()}
    provider = providers[pid]
    if provider.version != version or provider.payload != payload:
        raise PluginError("provider changed before worker startup")
    module, factory = provider.entry_point.split(":")
    output = sys.stdout.buffer
    with contextlib.redirect_stdout(sys.stderr):
        plugin = getattr(importlib.import_module(module), factory)()
    if not isinstance(plugin, PluginV1):
        raise PluginError("factory must return PluginV1")
    output.write(canonical({"ready": provider.payload}) + b"\n"); output.flush()
    specs = provider.manifest["capabilities"].get("content_types", {})
    while raw := sys.stdin.buffer.readline(FRAME_MAX + 2):
        try:
            request = read_json(raw, limit=FRAME_MAX)
            spec = specs[request["capability"]]
            method = request["method"]
            if method == "view_batch":
                state, audiences, ctx = request["args"]
                if not isinstance(audiences, list) or not 1 <= len(audiences) <= VIEW_BATCH:
                    raise PluginError("invalid view batch size")
                hook = plugin.state_hooks[spec["state_hook"]]
                contexts = ctx.pop("_audience_contexts", None)
                if contexts is not None and (not isinstance(contexts, list) or len(contexts) != len(audiences)
                                             or any(not isinstance(c, dict) for c in contexts)):
                    raise PluginError("invalid audience contexts")
                for index, audience in enumerate(audiences):
                    # A badly behaved view must not contaminate another actor's
                    # input. Preserve the isolation of separate ordinary calls.
                    own_ctx = copy.deepcopy(ctx)
                    if contexts is not None:
                        own_ctx.update(copy.deepcopy(contexts[index]))
                    own_ctx.update(role=audience["role"], actor=audience["actor"])
                    with contextlib.redirect_stdout(sys.stderr):
                        result = hook.view(copy.deepcopy(state), copy.deepcopy(audience), own_ctx)
                    value = json_value(result)
                    # Bound each response before streaming it, so a batch never
                    # accumulates many oversized values ahead of host validation.
                    if len(canonical(value)) > 128 * 1024:
                        raise PluginError("view exceeds output budget")
                    response = canonical({"view": index, "result": value})
                    if len(response) > FRAME_MAX: raise PluginError("hook output exceeds JSON budget")
                    output.write(response + b"\n"); output.flush()
                continue
            with contextlib.redirect_stdout(sys.stderr):
                if method == "prepare":
                    result = plugin.build_hooks[spec["build_hook"]](*request["args"])
                elif method == "prepare_source":
                    result = plugin.authoring_hooks[spec["authoring_hook"]](*request["args"])
                elif method in ("initial_state", "transition", "view", "record_keys"):
                    hook = plugin.state_hooks[spec["state_hook"]]
                    result = getattr(hook, method)(*request["args"])
                else:
                    raise PluginError("unknown hook")
            response = canonical({"result": json_value(result)})
            if len(response) > FRAME_MAX: raise PluginError("hook output exceeds JSON budget")
        except Exception as exc:
            # Never echo a student's input or reference answer into diagnostics.
            response = canonical({"error": f"hook failed ({type(exc).__name__})"})
        output.write(response + b"\n"); output.flush()


if __name__ == "__main__":
    main()
