# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""Command line: texstage present | pdf | pptx | build | check | retarget | serve | lecturer | publish |
addin; `texstage <deck>` without a command is `texstage present <deck>`. (Until 2026-10-10 the
command was texquiz.)

`texstage present` is what starts a lecture: the deck built if needed (with its stage PDF, as
every build), the quiz server of this machine used or started, and the deck opened - in
texstage's presenter window, or with --powerpoint its live PowerPoint file.

The build's modules (LaTeX, PDFium, python-pptx) load only for the commands that build: the
server - texstage serve, the Docker image - never loads them."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from texstage import SERVER_NAMES, DEFAULT_DATA, DEFAULT_PORT, DEFAULT_SERVER


def cmd_pdf(args: argparse.Namespace) -> int:
    from texstage.build.latex import LatexError, compile_deck
    tex = Path(args.tex)
    if not tex.is_file():
        print(f"texstage: no such file: {tex}", file=sys.stderr)
        return 2
    out_dir = Path(args.output_dir) if args.output_dir else tex.parent / "texquiz-out"
    try:
        result = compile_deck(tex, args.mode, out_dir, passes=args.passes)
    except LatexError as err:
        print(f"texstage: LaTeX failed\n{err}", file=sys.stderr)
        return 1
    note = f", {result.overfull} overfull boxes" if result.overfull else ""
    print(f"{result.pdf}{note}")
    return 0


def cmd_pptx(args: argparse.Namespace) -> int:
    from texstage.build.beamer import convert_beamer_to_pptx
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        convert_beamer_to_pptx(
            args.tex, args.output, target_height=args.target_height, dpi=args.dpi,
            standard=args.standard, note_side=args.note_side,
            legacy_two_pass_notes=args.legacy_two_pass_notes,
            allow_note_mismatch=args.allow_note_mismatch, keep_artifacts=args.keep_artifacts,
        )
    except (OSError, ValueError) as error:
        print(f"texstage pptx: {error}", file=sys.stderr)
        return 2
    except RuntimeError as error:
        print(f"texstage pptx: {error}", file=sys.stderr)
        return 1
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from texstage.build.builder import BuildError, BuildOptions, build
    from texstage.build.latex import LatexError
    from texstage.build.powerpoint import origin
    tex = Path(args.tex)
    if not tex.is_file():
        print(f"texstage: no such file: {tex}", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):      # a cp1252 console and LaTeX sources
        sys.stdout.reconfigure(errors="replace")
    out_dir = Path(args.output_dir) if args.output_dir else tex.parent / "texquiz-out"
    data = Path(args.data) if args.data else DEFAULT_DATA
    key = args.key
    if key is None and args.data and on_this_machine(args.server):
        # a second quiz server on this machine, with a data folder of its own (a dry run's, say):
        # the live slides carry its key - not the one in the default folder, the other server's
        from texstage.keys import find_key
        key = find_key(args.server, path=data / "servers.json", data_dir=data)
    opts = BuildOptions(server=args.server, key=key, deck_id=args.deck, height=args.height,
                        check=not args.no_check, max_shrink=args.max_shrink, passes=args.passes,
                        stage=not args.no_stage)            # the stage PDF: for PowerPoint and texstage alike
    try:
        r = build(tex, out_dir, opts)
    except LatexError as err:
        print(f"texstage: LaTeX failed\n{err}", file=sys.stderr)
        return 1
    except (BuildError, FileExistsError) as err:
        print(f"texstage: {err}", file=sys.stderr)
        return 1
    live = sum(1 for s in r.slides if s.live)
    boards = sum(1 for s in r.slides if s.phase == "leaderboard")
    print(f"{r.pptx}: {len(r.slides)} slides, {live} live ({r.quizzes} quizzes, {boards} leaderboards), "
          f"quiz server {origin(opts.server)}" + (" - and before them a first slide that prepares the live "
                                                   "ones: start the slideshow there" if r.first else ""))
    print(f"{r.static}: the same slides without the quiz (any PC, no server)")
    print(f"{r.bundle}: deck {r.deck_id}, bundle {r.bundle_id}")
    acts = r.activities
    if acts is not None and acts.items:
        kinds = ", ".join(f"{name} ({k['package']} {k['version']})" for name, k in acts.kinds.items())
        n, refs = len(acts.items), acts.references
        from texstage.activities.kit import kb
        print(f"  {n} live {'activity' if n == 1 else 'activities'} of the kind{'' if len(acts.kinds) == 1 else 's'} "
              f"{kinds}: {refs} {'reference runs' if refs == 1 else 'references run'} as the server runs them; a phone "
              f"loads {kb(acts.phone_bytes)} of the kinds' own files")
    print(f"{r.zip}: the same as one file - a server without the deck takes it in its deck list (Upload a deck)")
    if r.stage is not None:
        notes = sum(p.note is not None for p in r.stage.pages)
        print(f"{r.stage.pdf}: the stage PDF for texstage, {len(r.stage.pages)} slide pages and {notes} "
              f"note pages (in the bundle as {r.stage.file})")
    for w in r.warnings:
        print(f"  warning: {w}")
    for said in deliver(r.bundle, out_dir, origin(opts.server), opts.key, data):
        print(f"  {said}")
    if opts.check:
        for f in r.findings:
            print(f"  {'CHECK' if f.problem else 'note'}: {f}")
        print("  check: quiz and answer frames " + ("FAILED" if r.problems else "OK")
              + " (present and solutions builds)")
    return 1 if r.problems else 0


def on_this_machine(server: str) -> bool:
    """Whether a deck's quiz server is the one on this machine: it finds the builds by itself."""
    from urllib.parse import urlsplit

    from texstage.keys import LOCAL
    return (urlsplit(server).hostname or "") in LOCAL


def deliver(bundle: Path, out_dir: Path, server: str, key: str | None, data: Path) -> list[str]:
    """Every deck reaches its quiz server through its build (docs/design.md, section 4) - the
    PowerPoint file carries none: recorded for the server on this machine (builds.json - it
    finds the deck by itself, also when it starts later), uploaded to any other one (texstage
    publish). What happened, for the build's output."""
    from texstage.builds import remember_build
    from texstage.keys import find_key
    from texstage.publish import PublishError, find_bundles, publish
    said: list[str] = []
    try:
        remember_build(out_dir, data)
    except OSError as err:
        said.append(f"warning: the quiz server on this machine will not find the deck by itself ({err})")
    if on_this_machine(server):
        return said
    try:
        key = key or find_key(server)
        if not key:
            raise PublishError("no presenter key: --key, or TEXSTAGE_KEY")
        bundles, _ = find_bundles([bundle])
        publish(bundles, server, key, say=said.append)
    except PublishError as err:
        said.append(f"warning: the deck is not on {server} ({err}) - texstage publish {bundle} --url {server} "
                    f"once it can be reached")
    return said


def cmd_serve(args: argparse.Namespace) -> int:
    import threading

    import uvicorn

    from texstage.server import tunnel as cf
    from texstage.server import types as stage_types
    from texstage.server.app import ServerConfig, create_app, lan_addresses, listen, load_presenter_key
    data = Path(args.data) if args.data else DEFAULT_DATA
    if args.no_tunnel:
        cf.remember(data, None)
    name, kept_url = (args.tunnel, None) if args.tunnel else cf.remembered(data)
    public_url = args.public_url or kept_url
    try:
        plan = cf.plan(name, args.port, public_url) if name else None
    except cf.TunnelError as err:
        print(f"texstage: the tunnel {name}: {err}" + ("" if args.tunnel else "\n(--no-tunnel serves without it)"),
              file=sys.stderr)
        return 2
    if args.tunnel:
        cf.remember(data, args.tunnel, args.public_url)
    addresses = lan_addresses()
    public = plan.public_url if plan else (public_url or f"http://{addresses[0]}:{args.port}").rstrip("/")
    host = args.host or ("127.0.0.1" if plan else "0.0.0.0")    # through a tunnel, phones come from here
    from texstage.server.game import Settings
    most = getattr(args, "max_players", None)
    config = ServerConfig(bundles=[Path(b) for b in args.bundles] or [Path.cwd()], data_dir=data,
                          public_url=public, presenter_key=args.key or load_presenter_key(data),
                          owner=own_name(args.owner), settings=Settings(max_players=most) if most else Settings(),
                          checks=getattr(args, "checks", None) or "browser", workers=getattr(args, "workers", None),
                          activities=getattr(args, "activities", None) or stage_types.DEFAULT)
    app = create_app(config)
    server = app.state.server
    for b in sorted(server.bundles.bundles.values(), key=lambda b: (b.deck, str(b.path))):
        print(f"bundle {b.id}  {b.name}: {len(b.quizzes)} quizzes  ({b.path})")
    for problem in server.bundles.problems:
        print(f"  skipped: {problem}")
    if not server.bundles.bundles:
        print("no bundles yet - build a deck (texstage build); it is found while the server runs")
    # the key in full only when asked: a terminal is often on a shared screen or in a recording
    key = config.presenter_key if args.show_key else f"{config.presenter_key[:4]}… (--show-key: all of it)"
    print(f"phones join at {public}/play   presenter key: {key} ({config.owner})   data: {data}")
    others = [n for n in server.lecturers.names() if n != config.owner]
    if others:
        print(f"  lecturers with keys of their own: {', '.join(others)} (texstage lecturer list)")
    if config.activities != stage_types.DEFAULT:            # F1's type: its --checks, as before the core
        print(f"  live activities: F1's type (--activities {config.activities})"
              + ("" if config.checks == "browser" else f" - the server checks their texts (--checks {config.checks}"
                 + (": the presenter window's results count, the differences go to checks-compare.csv)"
                    if config.checks == "both" else ")")))
    elif getattr(args, "checks", None) in ("browser", "both"):     # the core's: the server checks, whatever it says
        print(f"  --checks {args.checks}: for F1's type (--activities f1) - the core's type checks the activities' "
              "texts on the server")
    if plan:
        kept = "remembered - --no-tunnel serves without it" if not args.tunnel else "remembered for the next start"
        print(f"  through the Cloudflare tunnel {name} ({kept}); PowerPoint and the host page use "
              f"http://localhost:{args.port}", flush=True)
    else:
        if not public_url and len(addresses) > 1:
            print(f"  other addresses of this machine: {', '.join(addresses[1:])} - if the phones are on one of "
                  f"those networks (e.g. a hotspot), give it: --public-url http://<address>:{args.port}")
        print(f"  phones in the room reach the server if {public}/api/status opens on one", flush=True)
    sockets = listen(host, args.port)                      # IPv4 and IPv6: see listen()
    tunnel = cf.Tunnel(plan, data / "cloudflared.log") if plan else None
    if tunnel:
        threading.Thread(target=tunnel.watch, args=(server.instance,), daemon=True).start()
    stage = f"http://localhost:{args.port}/stage"
    print(f"  texstage, the browser presenter: {stage}", flush=True)
    opener = getattr(args, "opener", None)                 # texstage present: the deck, or its PowerPoint file
    if opener or args.present:
        threading.Thread(target=open_when_up, args=(stage, opener), daemon=True).start()
    try:
        http = uvicorn.Server(uvicorn.Config(app, host=host, port=args.port, ws_max_size=64 * 1024,
                                            log_level=args.log_level, proxy_headers=True,
                                            forwarded_allow_ips=args.forwarded_allow_ips))
        run_server(http, sockets)
    finally:
        if tunnel:
            tunnel.stop()
    return 0


def run_server(server, sockets):
    if sys.platform == "win32":
        import asyncio

        from texstage.server.windows_loop import ProactorEventLoop
        with asyncio.Runner(loop_factory=ProactorEventLoop) as runner:
            runner.run(server.serve(sockets=sockets))
    else:
        server.run(sockets=sockets)


def open_when_up(url: str, opener=None, wait_s: float = 15.0):
    """Once the server answers: texstage's presenter window in the browser (url), or what
    `opener` opens (texstage present: the deck, or its PowerPoint file)."""
    import time
    import urllib.request
    import webbrowser
    status = url.rsplit("/", 1)[0] + "/api/status"
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(status, timeout=1):
                break
        except OSError:
            time.sleep(0.2)
    (opener or (lambda: webbrowser.open(url)))()


# ---------------------------------------------------------------------- texstage present
SOURCES = {".tex", ".sty", ".cls", ".bib", ".png", ".jpg", ".jpeg", ".svg", ".eps", ".pdf"}
SKIP = {"build", "texquiz-out", ".git", "__pycache__", ".ipynb_checkpoints"}


def deck_files(out: Path, name: str | None = None) -> list[Path]:
    """The deck.json files of a build folder's builds: of the deck `name` alone (its <name>.bundle,
    build/bundle.py deck_name), or every one in it."""
    if name is not None:
        own = out / f"{name}.bundle" / "deck.json"
        return [own] if own.is_file() else []
    return list(out.glob("*.bundle/deck.json"))


def needs_build(folder: Path, out: Path, ignore: tuple[str, ...] = (), name: str | None = None) -> str | None:
    """Why the deck of `folder` must be built before it is presented, or None: its build in
    `out` is there, has the stage PDF and is newer than every source - a .tex, .sty, .bib or
    picture of the folder and its subfolders (not the builds in them). A PDF in the folder
    itself is a compiled deck, not a source; `ignore`: files written from the sources (a
    chapter's slides.tex). `name`: the deck's own build (<name>.bundle) - several decks of one
    folder share its texquiz-out, and another deck's build is not this one's; without it, the
    newest build in `out` (a chapter's build folder holds its deck alone)."""
    import json
    decks = deck_files(out, name)
    if not decks:
        return "not built yet"
    newest = max(decks, key=lambda p: p.stat().st_mtime)
    try:
        if "pdf" not in json.loads(newest.read_text(encoding="utf-8")):
            return "built without the stage PDF"
    except (OSError, ValueError):
        return "its build cannot be read"
    built = newest.stat().st_mtime
    folder, out = folder.resolve(), out.resolve()
    for p in folder.rglob("*"):
        rel = p.relative_to(folder)
        if (p.suffix.lower() not in SOURCES or p.name in ignore or any(part in SKIP for part in rel.parts[:-1])
                or out in p.parents or (p.suffix.lower() == ".pdf" and len(rel.parts) == 1)):
            continue
        try:
            if p.is_file() and p.stat().st_mtime > built:
                return f"{rel.as_posix()} changed since the build"
        except OSError:
            continue
    return None


def built_deck(out: Path, name: str | None = None) -> tuple[str | None, Path | None]:
    """The deck of a build folder - the one named (its <name>.bundle), else the newest: its bundle
    ID and its live PowerPoint file."""
    bid, _, pptx = built(out, name)
    return bid, pptx


def built(out: Path, name: str | None = None) -> tuple[str | None, str | None, Path | None]:
    """As built_deck, with the deck's ID between: (bundle ID, deck ID, live PowerPoint file)."""
    import json
    decks = sorted(deck_files(out, name), key=lambda p: p.stat().st_mtime)
    if not decks:
        return None, None, None
    try:
        deck = json.loads(decks[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        deck = {}
    deck = deck if isinstance(deck, dict) else {}
    pptx = out / (decks[-1].parent.name.removesuffix(".bundle") + ".pptx")
    return deck.get("bundle"), deck.get("deck"), pptx if pptx.is_file() else None


def bundle_here(folder: Path) -> tuple[str | None, str | None, Path | None]:
    """A build folder itself (its deck.json in it - <name>.bundle, a server's kept copy, an upload):
    (bundle ID, deck ID, the live PowerPoint file beside a <name>.bundle)."""
    import json
    try:
        deck = json.loads((folder / "deck.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        deck = {}
    deck = deck if isinstance(deck, dict) else {}
    pptx = folder.parent / (folder.name.removesuffix(".bundle") + ".pptx") if folder.name.endswith(".bundle") else None
    return deck.get("bundle"), deck.get("deck"), pptx if pptx is not None and pptx.is_file() else None


def server_up(port: int) -> bool:
    """Whether a texstage server already answers on this machine's port."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/status", timeout=1.5) as r:
            return json.loads(r.read()).get("server") in SERVER_NAMES
    except (OSError, ValueError):
        return False


def local_api(port: int, path: str, key: str | None = None, timeout: float = 10.0) -> tuple[int | None, object]:
    """A GET of the quiz server on this machine's port: (HTTP status, its JSON answer) - (None, None)
    when it cannot be reached or does not answer in JSON."""
    import json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"http://localhost:{port}{path}", headers={"X-Texquiz-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as err:
        return err.code, None
    except (OSError, ValueError):
        return None, None


def server_status(port: int) -> dict | None:
    """The /api/status of the server that answers on this machine's port, or None."""
    code, status = local_api(port, "/api/status", timeout=1.5)
    return status if code == 200 and isinstance(status, dict) else None


def server_checks(port: int) -> str | None:
    """Who checks the activities' texts of the server that answers on this machine's port (its
    /api/status), or None."""
    status = server_status(port)
    return None if status is None else status.get("checks") or "browser"


# what texstage present hands to a server it starts - and a server that runs already does not take
STARTING = (("tunnel", "--tunnel"), ("no_tunnel", "--no-tunnel"), ("public_url", "--public-url"), ("host", "--host"))


def running_notes(args: argparse.Namespace, more: list[str], bid: str | None, deck: str | None) -> list[str]:
    """What texstage present says of the quiz server that runs already on its port, which it uses as it
    is: the options given for a server it starts (the review of 2026-11-14: --activities, the tunnel's
    and the addresses' went unsaid), an activity type that is not the default when none was given, and -
    this deck's build - whether that server has it, or why not, and the game of the deck that the build
    would end (deck_notes)."""
    notes = []
    mode = server_checks(args.port) if args.checks or args.workers or args.max_players else None
    if mode is not None and ((args.checks and args.checks != mode) or args.workers or args.max_players):
        notes.append(f"it checks with --checks {mode}: --checks, --workers and --max-players are for a server "
                     "that present starts")                 # (the package 4 review: they went unsaid)
    running = (server_status(args.port) or {}).get("activities")
    if running and args.activities and running != args.activities:
        notes.append(f"it runs the activity type {running}: --activities {args.activities} is for a server that present "
                     "starts - stop the running server (Ctrl+C in its window), then present again")
    elif running and not args.activities:                 # (package 14: one started before the core's became the
        from texstage.server.types import DEFAULT          # default runs F1's - a lecturer would not see why)
        if running != DEFAULT:
            notes.append(f"it runs the activity type {running}, not the default, {DEFAULT} - for the default, stop the "
                         "running server (Ctrl+C in its window), then present again")
    given = [flag for attr, flag in STARTING if getattr(args, attr, None)]
    if given:
        notes.append(f"{', '.join(given)}: for a server that present starts - the running one keeps its own")
    if more:
        notes.append(f"it serves what it was started with and the builds recorded in its data folder, not "
                     f"{', '.join(more)}")
    if bid:
        notes += deck_notes(args.port, bid, deck, powerpoint=args.powerpoint)
    return notes


def deck_notes(port: int, bid: str, deck: str | None, powerpoint: bool = False) -> list[str]:
    """Whether the quiz server on this machine's port has the build `bid` on its deck list - or why
    not: a deck it does not play (GET /api/skipped), a build it has but does not list, one it does not
    have -, and the game of the deck on another build that this build would end. Asked with this
    machine's presenter key (GET /api/presenter-key: only to the machine itself); a server that gives
    none, or is older than these routes, is not asked."""
    import time
    code, given = local_api(port, "/api/presenter-key", timeout=2)
    key = given.get("key") if code == 200 and isinstance(given, dict) else None
    code, decks = local_api(port, "/api/decks", key) if key else (None, None)
    if code != 200 or not isinstance(decks, list):
        return []
    notes = []
    if not any(isinstance(d, dict) and d.get("bundle") == bid for d in decks):
        code, skipped = local_api(port, "/api/skipped", key)
        why = next((s.get("error") for s in skipped if isinstance(s, dict) and s.get("bundle") == bid), None) \
            if code == 200 and isinstance(skipped, list) else None
        if why:
            notes.append(f"it does not play this deck: {why}")
        else:
            code, _ = local_api(port, f"/api/deck/{bid}", key)
            if code == 200:
                notes.append("it has this build but does not list it - an older build of the deck than its newest, or "
                             "the deck was taken off the list: the presenter window opens it all the same")
            elif code == 404:
                notes.append("it does not have this build: it serves the folders it was started with and the builds "
                             "recorded in its own data folder - is it started with another --data (present's is for a "
                             "server it starts)? Or upload the deck's .bundle.zip in its deck list")
    game = next((d for d in decks if isinstance(d, dict) and d.get("deck") == deck and d.get("bundle") != bid
                 and isinstance(d.get("game"), dict) and d["game"].get("players")), None)
    if game is not None:
        when = time.strftime("%H:%M", time.localtime(game.get("built", 0) / 1000))
        n = game["game"]["players"]
        notes.append(f"a game of this deck runs on its build of {when} (PIN {game['game'].get('pin')}, "
                     f"{n} {'player' if n == 1 else 'players'}): "
                     + ("the live slides of this PowerPoint file end it - the phones join the new game with a new PIN"
                        if powerpoint else "the presenter window asks before this build replaces it"))
    return notes


def open_file(path: Path):
    """A file in the program the system opens it with (the PowerPoint file: PowerPoint)."""
    import os
    import subprocess
    if sys.platform == "win32":
        os.startfile(path)                                    # noqa: S606 (the lecturer's own file)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def cmd_present(args: argparse.Namespace) -> int:
    import webbrowser
    targets = args.targets or ["."]
    first, *more = targets
    path = Path(first)
    if path.suffix.lower() == ".tex":
        if not path.is_file():
            print(f"texstage: no such file: {path}", file=sys.stderr)
            return 2
        out = Path(args.output_dir) if args.output_dir else path.parent / "texquiz-out"
        from texstage.build.bundle import deck_name
        name = deck_name(path)                       # its own build: the decks of a folder share texquiz-out
        why = "asked for" if args.build else None if args.no_build else needs_build(path.parent, out, name=name)
        if why:
            print(f"texstage present: building {path.name} ({why})", flush=True)
            code = cmd_build(argparse.Namespace(
                tex=str(path), output_dir=str(out), server=f"http://localhost:{args.port}", key=None, deck=args.deck,
                height=1080, no_check=args.no_check, max_shrink=15.0, passes=2, no_stage=False, data=args.data))
            if code != 0 and needs_build(path.parent, out, name=name):
                return code                                   # LaTeX or the build failed: nothing to present
            if code != 0:
                print("texstage present: the check found problems in the quiz frames (above) - presenting the deck anyway")
    else:
        out, name = path, None
    if name is None and (out / "deck.json").is_file():       # a build folder itself: that build - an older one
        bid, deck, pptx = bundle_here(out)                     # too, a rollback (the deck page's Builds offers it)
        data = Path(args.data) if args.data else DEFAULT_DATA
        if not out.resolve().is_relative_to(data.resolve()):  # (a server's own copies and uploads it has: never
            from texstage.builds import remember_build         # one of them as a build folder - open to all)
            try:
                remember_build(out, data)                      # the server running here finds it (builds.json)
            except OSError as err:
                print(f"texstage present: the quiz server on this machine may not find {out} ({err})", file=sys.stderr)
    else:
        bid, deck, pptx = built(out, name)
    if args.powerpoint and pptx is None:
        print(f"texstage: no live PowerPoint file in {out}" + ("" if bid else " - build the deck first"), file=sys.stderr)
        return 2
    url = f"http://localhost:{args.port}/stage" + (f"?bundle={bid}" if bid else "")
    opener = (lambda: open_file(pptx)) if args.powerpoint else (lambda: webbrowser.open(url))
    if server_up(args.port):                                 # it finds the build by itself (builds.json)
        print(f"texstage present: the quiz server on this machine runs already - {pptx if args.powerpoint else url}")
        for note in running_notes(args, more, bid, deck):
            print(f"  {note}")
        opener()
        return 0
    return cmd_serve(argparse.Namespace(
        bundles=[str(out), *more], host=args.host, port=args.port, public_url=args.public_url, tunnel=args.tunnel,
        no_tunnel=args.no_tunnel, data=args.data, key=None, owner=None, show_key=False, present=False,
        opener=opener, log_level=args.log_level, forwarded_allow_ips=None, checks=args.checks,
        workers=args.workers, max_players=args.max_players, activities=args.activities))


def own_name(name: str | None) -> str:
    """The name of the server's own lecturer (its presenter-key): --owner, else the user's."""
    import getpass
    import re
    from texstage.server.lecturers import valid_name
    raw = name or re.sub(r"[^a-z0-9._-]+", "-", getpass.getuser().lower()).strip("-.") or "local"
    return valid_name(raw[:40])


def cmd_lecturer(args: argparse.Namespace) -> int:
    from texstage.server.lecturers import LecturerError, Lecturers
    data = Path(args.data) if args.data else DEFAULT_DATA
    lecturers = Lecturers(data / "lecturers.json")
    try:
        if args.action == "list":
            names = lecturers.names()
            print("\n".join(names) if names else "no lecturers yet - texstage lecturer add NAME")
            print(f"(and the server's own key, {data / 'presenter-key'}, for whoever runs the server)")
            return 0
        if not args.name:
            print("texstage: which lecturer? texstage lecturer add NAME", file=sys.stderr)
            return 2
        if args.action == "remove":
            print(f"lecturer {args.name} removed." if lecturers.remove(args.name) else f"no lecturer {args.name}.")
            return 0
        key = lecturers.add(args.name) if args.action == "add" else lecturers.renew(args.name)
    except LecturerError as err:
        print(f"texstage: {err}", file=sys.stderr)
        return 1
    print(f"presenter key of {args.name.strip().lower()} (shown only now - the server keeps a hash):\n\n    {key}\n")
    print("Give it to the lecturer. They build their decks with it once:\n"
          "    texstage build <deck>.tex --server <this server's address> --key=<key>\n"
          "(or remember it: texstage publish --url <address> --key=<key> --remember). A running server "
          "takes the change at once.")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from texstage.publish import PublishError, find_bundles, find_key, publish, remember_key
    url = args.url.rstrip("/")
    bundles, problems = find_bundles([Path(p) for p in args.bundles] or [Path.cwd()])
    for problem in problems:
        print(f"  skipped: {problem}", file=sys.stderr)
    if not bundles:
        print("texstage: no bundles found - build a deck first (texstage build)", file=sys.stderr)
        return 1
    try:
        key = find_key(url, args.key)
        publish(bundles, url, key)
    except PublishError as err:
        print(f"texstage: {err}", file=sys.stderr)
        return 1
    if args.remember and args.key:
        remember_key(url, args.key)
        print(f"presenter key for {url} remembered (~/{DEFAULT_DATA.name}/servers.json)")
    return 0


def cmd_addin(args: argparse.Namespace) -> int:
    from texstage import addin
    from texstage.build.powerpoint import origin
    try:
        url = origin(args.url)
    except ValueError as err:
        print(f"texstage: {err}", file=sys.stderr)
        return 2
    if args.action == "manifest":
        sys.stdout.write(addin.manifest(url))
        return 0
    if sys.platform != "win32":
        print("texstage: registering is for PowerPoint on Windows; use `texstage addin manifest` for a catalog",
              file=sys.stderr)
        return 2
    if args.action == "install":
        path = addin.install(url, Path(args.data) if args.data else DEFAULT_DATA)
        print(f"texstage ({url}) registered for this user: {path}. Restart PowerPoint.")
    elif args.action == "list":
        found = addin.installed()
        for aid, path in sorted(found.items(), key=lambda kv: kv[1]):
            print(f"{addin.manifest_server(path) or '?'}   add-in {aid}   {path}")
        if not found:
            print("no texstage add-in registered - texstage addin install [--url ...]")
    else:
        removed = addin.uninstall(None if args.all else url)
        print(f"removed {len(removed)} texstage add-in(s)." if removed else "no such texstage add-in registered.")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from texstage.preflight import OFFICE_JS, check
    pptx = Path(args.pptx)
    if not pptx.is_file():
        print(f"texstage: no such file: {pptx}", file=sys.stderr)
        return 2
    return 0 if check(pptx, office_js=None if args.offline else OFFICE_JS) else 1


def cmd_retarget(args: argparse.Namespace) -> int:
    from texstage.build.powerpoint import origin, retarget
    from texstage.keys import find_key
    pptx = Path(args.pptx)
    try:
        server = origin(args.server)
        key = find_key(server, args.key)
        n = retarget(pptx, server, key)
    except ValueError as err:
        print(f"texstage: {err}", file=sys.stderr)
        return 2
    except PermissionError:
        print(f"texstage: {pptx} is locked - probably open in PowerPoint; close it first", file=sys.stderr)
        return 1
    print(f"{pptx}: {n} live slides now use {server} (its add-in: texstage addin install --url {server}, "
          f"once per PC)")
    if not key:
        print(f"  warning: no presenter key for {server}: the live slides will ask for it once - give it with --key")
    return 0


COMMANDS = ("present", "pdf", "pptx", "build", "check", "retarget", "serve", "lecturer", "publish", "addin", "kinds", "data")


def amount(n: int) -> str:
    """Bytes as people read them: 812 kB, 33.2 MB, 3.4 GB."""
    for unit, size in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= size:
            return f"{n / size:.1f} {unit}" if n < 100 * size else f"{n / size:.0f} {unit}"
    return f"{n} B"


def cmd_data(args: argparse.Namespace) -> int:
    """texstage data: what the data folder holds per deck - nothing is deleted by itself; texstage data clean
    --before DATE removes, as asked, ended lectures (rows and archive folders), recordings alone, or copies kept
    for games - never an open game's - and lists them first: --yes deletes."""
    import datetime

    from texstage.server import datafolder
    data = Path(args.data) if args.data else DEFAULT_DATA
    if not data.is_dir():
        print(f"texstage: no data folder {data}", file=sys.stderr)
        return 2
    if args.action != "clean":
        decks = datafolder.overview(data)
        if not decks:
            print(f"nothing of decks in {data}")
            return 0
        rows = [("deck", "uploads", "copies", "lectures", "archive", "recordings", "total")]
        for d in decks:
            rows.append((d.deck, f"{d.uploads} ({amount(d.uploads_bytes)})" if d.uploads else "-",
                         f"{d.copies} ({amount(d.copies_bytes)})" if d.copies else "-", str(d.lectures or "-"),
                         amount(d.archive_bytes) if d.archive_bytes else "-",
                         f"{d.recordings} ({amount(d.recordings_bytes)})" if d.recordings else "-", amount(d.total)))
        widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
        for r in rows:
            print("  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))))
        store = data / datafolder.STORE
        print(f"\n{amount(sum(d.total for d in decks))} for {len(decks)} decks in {data}"
              + (f" (and the store of games, {store.name}: {amount(store.stat().st_size)})" if store.is_file() else ""))
        print("Nothing is deleted by itself but a deck's builds beyond its newest ten. To clean by hand, e.g.: "
              "texstage data clean --before 2026-04-01 "
              "--recordings (lists what would go; --yes deletes)")
        return 0
    if not args.before:
        print("texstage data clean: --before DATE, e.g. --before 2026-04-01 (what ended or was built before it)",
              file=sys.stderr)
        return 2
    if not (args.lectures or args.recordings or args.copies):
        print("texstage data clean: say what goes - --lectures (ended lectures: their results, ink, questions, "
              "recordings), --recordings (their recordings alone), --copies (copies kept for games)", file=sys.stderr)
        return 2
    try:
        day = datetime.date.fromisoformat(args.before)
    except ValueError:
        print(f"texstage data clean: --before {args.before} is no date (YYYY-MM-DD)", file=sys.stderr)
        return 2
    before = int(datetime.datetime.combine(day, datetime.time()).timestamp() * 1000)    # (local midnight)
    gone = datafolder.plan(data, before, lectures=args.lectures, recordings=args.recordings, copies=args.copies,
                           deck=args.deck)
    words = {"lecture": "lecture", "empty": "games", "recording": "recording", "copy": "copy"}
    going = [g for g in gone if g.kind != "held"]
    for g in going:
        print(f"  {words[g.kind]:9}  {g.deck}  {g.what}  ({amount(g.bytes)})")
    for g in gone:
        if g.kind == "held":
            print(f"  left alone {g.deck}  {g.what}")
    if not going:
        print(f"nothing to clean before {day} in {data}")
        return 0
    total = sum(g.bytes for g in going)
    if not args.yes:
        print(f"{len(going)} to clean, {amount(total)} - nothing deleted yet: the same command with --yes deletes them"
              + (" (lectures: their results, ink, the audience's questions and recordings, for good)" if args.lectures else ""))
        return 0
    freed, failed = datafolder.clean(data, going)   # (a server may run meanwhile: open games and what they use stay)
    for why in failed:
        print(f"  not cleaned: {why}", file=sys.stderr)
    print(f"{len(going) - len([f for f in failed if not f.endswith('next cleaning')])} cleaned, {amount(freed)} freed")
    return 1 if any(not f.endswith("next cleaning") for f in failed) else 0


def cmd_kinds(args: argparse.Namespace) -> int:
    """The kinds of live activities that are installed - or, with check, the kit (activities/kit.py): 0
    when every kind asked for passed it, 1 otherwise - also when there was none to check."""
    from texstage.activities import kit, registry
    found = registry.found()
    none = "no kinds are installed - a kind comes with its package, as texstage-kinds-sql brings sql-query"
    if args.action != "check":
        if not found:
            print(none)
            return 0
        width = max(len(f.name) for f in found)
        for f in found:
            api = "API ?" if f.api is None else f"API {f.api}"
            print(f"{f.name:{width}}  {f.package} {f.version}, {api}" + (f" - cannot be used: {f.fault}" if f.fault else ""))
        return 1 if any(f.fault for f in found) else 0
    names = args.names or sorted({f.name for f in found})
    if not names:
        print(f"nothing to check: {none}", file=sys.stderr)
        return 1
    known = {f.name for f in found}
    failed = False
    for name in names:
        hits = [f for f in found if f.name == name]
        if not hits:
            print(f"{name}: no kind of this name is installed (texstage kinds lists them)", file=sys.stderr)
            failed = True
        for f in hits:
            if f.kind is None:
                print(f"{f.name} ({f.package} {f.version}): cannot be used - {f.fault}")
                failed = True
                continue
            report = kit.check(f.kind, f.name, known=known)
            print(kit.said(report, f))
            failed = failed or not report.ok
    return 1 if failed else 0


class Parser(argparse.ArgumentParser):
    """texstage's command line. A presenter key made before 2026-11-17 may start with "-"
    (keys.new_key), and `--key -Abc` reads as an option: the error says how to give it."""

    def error(self, message):
        if message.startswith("argument --key: expected one argument"):
            message += ' - a key that starts with "-" goes as --key=<key>'
        super().error(message)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and argv[0] not in ("-h", "--help"):
        argv = ["present", *argv]                     # texstage deck.tex: texstage present deck.tex
    parser = Parser(prog="texstage", description="Beamer decks presented live, with their "
                    "quizzes: texstage present <deck> starts a lecture")
    sub = parser.add_subparsers(dest="command", required=True)
    pr = sub.add_parser("present", help="present a deck: built first if needed, then in texstage's presenter window "
                                        "(or --powerpoint) on the quiz server running here, or on one started now")
    present_options(pr)

    p = sub.add_parser("pdf", help="compile a deck as handout, solutions or present PDF")
    p.add_argument("tex")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--handout", dest="mode", action="store_const", const="handout",
                      help="placeholder per quiz (default; same as a plain compile)")
    mode.add_argument("--solutions", dest="mode", action="store_const", const="solutions",
                      help="questions with correct answers and explanations")
    mode.add_argument("--present", dest="mode", action="store_const", const="present",
                      help="question, reveal and leaderboard slides (preview of the live deck)")
    p.add_argument("-o", "--output-dir", help="default: texquiz-out next to the source")
    p.add_argument("--passes", type=int, default=2)
    p.set_defaults(mode="handout", func=cmd_pdf)

    p = sub.add_parser("pptx", help="convert Beamer to a static PowerPoint with speaker notes",
                       description="Beamer .tex to .pptx with images and speaker notes.")
    p.add_argument("tex", help="Path to the Beamer .tex file")
    p.add_argument("-o", "--output", help="Output .pptx (default: <tex>.pptx)")
    p.add_argument("--target-height", type=int, default=1080,
                    help="Target pixel height per slide (default 1080, matches 1080p projector)")
    p.add_argument("--dpi", type=int, default=None,
                    help="Force fixed DPI instead of computing from --target-height")
    p.add_argument("--standard", action="store_true", help="4:3 PPTX canvas instead of 16:9")
    p.add_argument("--note-side", choices=["left", "right"], default="right",
                    help="Side used for Beamer notes in default second-screen mode (default: right)")
    p.add_argument("--legacy-two-pass-notes", action="store_true",
                    help=("Use the old method: compile slides and notes as separate PDFs, "
                          "then align them by page index. Not recommended for overlays."))
    p.add_argument("--allow-note-mismatch", action="store_true",
                    help=("Only with --legacy-two-pass-notes: pad/truncate notes if slide/note "
                          "page counts differ. By default, mismatches are fatal."))
    p.add_argument("--keep-artifacts", action="store_true",
                    help="Keep generated .tex/.pdf/aux files in source dir (for debugging)")
    p.set_defaults(func=cmd_pptx)

    b = sub.add_parser("build", help="the live deck: PowerPoint file and quiz bundle, "
                                     "and a layout check of the quiz and answer frames")
    b.add_argument("tex", help="the deck, e.g. a course chapter's slides.tex")
    b.add_argument("-o", "--output-dir", help="default: texquiz-out next to the source")
    b.add_argument("--server", default=DEFAULT_SERVER,
                   help=f"the quiz server the live slides use (default {DEFAULT_SERVER}); its add-in must be "
                        "registered on the presenting PC (texstage addin install --url ...). The build hands the "
                        "deck to it: the server on this machine finds it by itself, any other gets it uploaded")
    b.add_argument("--key", help="the server's presenter key, carried by the live slides (default: TEXSTAGE_KEY, "
                                 "the remembered one, or - a server on this PC - its data folder's)")
    b.add_argument("--deck", help="deck id on the server (default: from the file or chapter name)")
    b.add_argument("--height", type=int, default=1080, help="slide pictures, pixels (default 1080)")
    b.add_argument("--max-shrink", type=float, default=15.0,
                   help="quiz frames shrunk by this many percent or more fail the check (default 15)")
    b.add_argument("--no-check", action="store_true", help="skip the solutions build and the check")
    b.add_argument("--passes", type=int, default=2)
    b.add_argument("--no-stage", action="store_true",
                   help="without the stage PDF for texstage, the browser presenter (by default the deck is compiled "
                        "once more for it, alongside, with its own note pages): a quicker build for PowerPoint alone")
    b.add_argument("--stage", action="store_true", help=argparse.SUPPRESS)    # the default since 2026-10-10
    b.add_argument("--data", help=f"the data folder of this machine's quiz server (default ~/{DEFAULT_DATA.name}): the build "
                                  "is recorded there, and the server serves it without an upload")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="run the quiz server (laptop or hosted)")
    s.add_argument("bundles", nargs="*", help="bundles, or folders with bundles (e.g. a chapter's "
                                              "build/texquiz); default: the current folder")
    s.add_argument("--host", help="address to listen on (default: all - phones in the room; with a tunnel: "
                                  "only this machine)")
    s.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    s.add_argument("--public-url", help="how phones reach the server (default http://<LAN address>:<port>, "
                                        "with a tunnel its hostname)")
    t = s.add_mutually_exclusive_group()
    t.add_argument("--tunnel", metavar="NAME", help="phones come through this Cloudflare tunnel: runs "
                                                    "cloudflared tunnel run NAME with the server (remembered)")
    t.add_argument("--no-tunnel", action="store_true", help="serve without the remembered tunnel (and forget it)")
    s.add_argument("--data", help=f"sessions database and presenter key (default ~/{DEFAULT_DATA.name})")
    s.add_argument("--key", help="presenter key (default: the one in the data folder, made on the first start)")
    s.add_argument("--owner", help="name of the lecturer the server's own key belongs to (default: your user name)")
    s.add_argument("--show-key", action="store_true",
                   help="print the presenter key in full (by default only its first characters: a terminal is "
                        "often on a shared screen; the key is in the data folder, presenter-key)")
    s.add_argument("--present", action="store_true",
                   help="open texstage's presenter window (/stage) in the browser once the server runs")
    s.add_argument("--log-level", default="warning")
    checks_options(s)
    s.add_argument("--forwarded-allow-ips", default=None,
                   help="behind a reverse proxy: the proxy addresses whose X-Forwarded-* headers are trusted "
                        "(default 127.0.0.1 and ::1 - Caddy or cloudflared on this machine; '*' in Docker, "
                        "where only the proxy reaches the server)")
    s.set_defaults(func=cmd_serve)

    lc = sub.add_parser("lecturer", help="the lecturers of a quiz server, each with a presenter key of their own")
    lc.add_argument("action", choices=["add", "list", "renew", "remove"])
    lc.add_argument("name", nargs="?", help="the lecturer's name (lowercase letters, digits, . _ -)")
    lc.add_argument("--data", help=f"the server's data folder (default ~/{DEFAULT_DATA.name}; in Docker /data)")
    lc.set_defaults(func=cmd_lecturer)

    u = sub.add_parser("publish", help="upload live decks (bundles) to a hosted quiz server")
    u.add_argument("bundles", nargs="*", help="bundles, or folders with bundles (default: the current folder)")
    u.add_argument("--url", required=True, help="the server, e.g. https://quiz.example.org")
    u.add_argument("--key", help="its presenter key (default: TEXSTAGE_KEY, or the remembered one)")
    u.add_argument("--remember", action="store_true", help=f"keep --key for this server in ~/{DEFAULT_DATA.name}/servers.json")
    u.set_defaults(func=cmd_publish)

    c = sub.add_parser("check", help="is a live deck ready to present on this PC? (add-in, server, key, deck)")
    c.add_argument("pptx")
    c.add_argument("--offline", action="store_true", help="skip the internet check (Office.js)")
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("retarget", help="point a live deck's PowerPoint file at another quiz server")
    r.add_argument("pptx")
    r.add_argument("--server", required=True, help=f"e.g. https://quiz.example.org or {DEFAULT_SERVER}")
    r.add_argument("--key", help="its presenter key (default as for texstage build)")
    r.set_defaults(func=cmd_retarget)

    a = sub.add_parser("addin", help="the PowerPoint add-in of a quiz server: register it on this PC, "
                                     "list or remove them, or print a manifest")
    a.add_argument("action", choices=["install", "uninstall", "list", "manifest"])
    a.add_argument("--url", default=DEFAULT_SERVER,
                   help=f"the quiz server (default {DEFAULT_SERVER}); every server has its own add-in")
    a.add_argument("--all", action="store_true", help="uninstall: every texstage add-in")
    a.add_argument("--data", help=f"where to put the manifest (default ~/{DEFAULT_DATA.name})")
    a.set_defaults(func=cmd_addin)

    k = sub.add_parser("kinds", help="the kinds of live activities that are installed; kinds check [name ...]: "
                                     "the kit, the test every kind passes")
    k.add_argument("action", nargs="?", choices=["check"], help="check: run the kit")
    k.add_argument("names", nargs="*", help="check: the kinds to check (default: every installed one)")
    k.set_defaults(func=cmd_kinds)

    dt = sub.add_parser("data", help="what the data folder holds per deck (uploads, copies kept for games, lectures, "
                                     "their archive and recordings); data clean --before DATE: remove by hand")
    dt.add_argument("action", nargs="?", choices=["clean"], help="clean: remove what --lectures, --recordings, "
                                                                 "--copies name (listed first; --yes deletes)")
    dt.add_argument("--before", help="clean: what ended (lectures, their recordings) or was built (copies) before "
                                     "this day, YYYY-MM-DD")
    dt.add_argument("--lectures", action="store_true", help="clean: ended lectures - their results, ink, the "
                                                            "audience's questions and recordings, for good")
    dt.add_argument("--recordings", action="store_true", help="clean: the recordings of ended lectures alone")
    dt.add_argument("--copies", action="store_true", help="clean: copies kept for games (served/) no open game plays")
    dt.add_argument("--deck", help="clean: of this deck only")
    dt.add_argument("--yes", action="store_true", help="clean: delete them (without it: listed only)")
    dt.add_argument("--data", help=f"the data folder (default ~/{DEFAULT_DATA.name})")
    dt.set_defaults(func=cmd_data)
    args = parser.parse_args(argv)
    return args.func(args)


def present_options(parser: argparse.ArgumentParser):
    parser.add_argument("targets", nargs="*", help="the deck: its .tex file (built first if its build is missing or "
                                                   "older than its sources), a build's output folder (its newest "
                                                   "build), or a build folder itself - a <name>.bundle, a server's "
                                                   "kept copy or upload: that build, an older one too; further "
                                                   "folders are served too; default: the current folder")
    parser.add_argument("--powerpoint", action="store_true",
                        help="open the deck's live PowerPoint file instead of texstage's presenter window")
    b = parser.add_mutually_exclusive_group()
    b.add_argument("--build", action="store_true", help="build the deck even if its build is up to date")
    b.add_argument("--no-build", action="store_true", help="present the build as it is")
    parser.add_argument("-o", "--output-dir", help="the deck's build folder (default: texquiz-out next to it)")
    parser.add_argument("--deck", help="building: the deck's id on the server (default: from the file name)")
    parser.add_argument("--no-check", action="store_true", help="building: skip the layout check of the quiz frames")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"the quiz server's port (default {DEFAULT_PORT})")
    parser.add_argument("--host", help="starting the server: the address to listen on (default: all - phones in the room)")
    parser.add_argument("--public-url", help="starting the server: how phones reach it (default http://<LAN address>:<port>)")
    t = parser.add_mutually_exclusive_group()
    t.add_argument("--tunnel", metavar="NAME", help="starting the server: phones come through this Cloudflare tunnel "
                                                    "(remembered)")
    t.add_argument("--no-tunnel", action="store_true", help="starting the server: without the remembered tunnel")
    parser.add_argument("--data", help=f"the quiz server's data folder (default ~/{DEFAULT_DATA.name})")
    parser.add_argument("--log-level", default="warning")
    checks_options(parser, "starting the server: ")
    parser.set_defaults(func=cmd_present)


def _positive(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("at least 1")
    return n


def checks_options(parser: argparse.ArgumentParser, starting: str = "") -> None:
    """Who checks the live activities' texts, on serve - and on present, for the server it starts
    (docs/architecture/activity-framework-plan.md, 4.6 and 4.7)."""
    parser.add_argument("--checks", choices=["server", "browser", "both"], default=None,
                        help=f"{starting}with --activities f1, who checks the live activities' queries: the server's "
                             "worker processes, the presenter window (its default), or both - the window's "
                             "results count, and every difference goes to checks-compare.csv in the game's archive "
                             "folder; the core's type always checks on the server")
    parser.add_argument("--workers", type=_positive,
                        help=f"{starting}the worker processes that check on the server (default: the cores less two)")
    parser.add_argument("--max-players", type=_positive, help=f"{starting}phones a game takes at most (default 1000)")
    parser.add_argument("--activities", choices=["core", "f1"], default=None,
                        help=f"{starting}the live activities' type: core (default) - the activity framework's, with "
                             "its kinds, the server's checks, the panel and the phone's step screen -, or f1, the type "
                             "the lectures had before, kept until a class has used the core "
                             "(docs/architecture/activity-framework-plan-f2.md, 4.12)")


if __name__ == "__main__":
    sys.exit(main())
