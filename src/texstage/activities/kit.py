# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The kit: the test every kind passes, texstage's own ones too (docs/architecture/activity-framework-
design.md, 7.5) - its Python half; the browser's - a kind's texts and modules, what a phone loads - comes
with the browser (the plan of F2, 4.9).

    texstage kinds check [name ...]

It holds the kind's class against the contract's rules (kind.py), then runs its fixtures on a thread with
a worker's stack: every build against what it must make or refuse; every entry through normalize and
check, as the core will - twice, the second time in the other order on what was prepared once, so that a
check that changes what was prepared shows; every check against the rules a check must keep (fault); and
for a kind of code, texts nested as deep as a text is long, which must come back as a check - whatever
it says. It reports each fixture's time against the kind's budget, and gives a check up that does not
come back.

A kind's fixtures are beside its module, tests/*.json - what the kind is prepared with (a setting), an
entry, and what it must give:

    {"kind": "sql-query",
     "settings": {"people": {"item": {"seed": "data/people.sql"}, "keys": {"reference": ["SELECT ..."]},
                             "files": {"data/people.sql": "CREATE TABLE ..."}}},
     "cases": [{"setting": "people", "entry": {"text": "SELECT name FROM person"},
                "check": {"status": "ok", "key": "4cc49ff7c0a1e3b2", "detail": {...}}},
               {"setting": "people", "entry": {"text": ""}, "unfit": "text"},
               {"setting": "people", "entry": {"text": ""}, "direct": true, "check": {"status": "invalid"}}],
     "builds": [{"options": {"seed": "people.sql"}, "bodies": {"references": ["SELECT ..."]},
                 "files": {"people.sql": "CREATE TABLE ..."},
                 "built": {"item": {...}, "keys": {...}, "files": {"data/0123456789abcdef.sql": "CREATE TABLE ..."}}},
                {"options": {"seed": "people.ttl"}, "refused": "the seed people.ttl - sql takes .sql files"}]}

A case's check names what it pins: the status - or the statuses it may be, where an engine's build
decides: ["ok", "error"] -, and of key, parts, verdict, credit, message (its code; its args where the
case gives them), at and detail those it lists. unfit: normalize refuses the entry, with this code.
direct: the entry goes to check as it is, as a reference does - not through normalize. language: the
step's (en). A text may be written {"repeat": n, "line": "... {i} ..."} - n lines - or {"deep": n,
"open": "(", "inside": "1", "close": ")", "before": "SELECT ", "after": ""}. A build gives the deck's keys
(options), what the environment's body held (bodies) and the deck's files, and what must come of them:
built - the item, the keys, the bundle's files as texts - or refused, the refusal's words.

A file is one kind's: a folder may hold several kinds' files, and a file for a kind that is not installed
is said - its name may be misspelt."""
from __future__ import annotations

import gzip
import inspect
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from texstage.activities import kind as contract
from texstage.activities.kind import Entry, Kind, Step, Unbuildable, Unfit
from texstage.activities.options import CORE, Option, Options

STACK = 64 * 2**20                      # a worker's (server/worker.py): parsers recurse
BUDGET_S = 10.0                         # a fixture's check may take the references' time; its own is reported
HANG_S = 30.0                           # ... and one that has not come back by then is given up
COPY_MOST = 128 * 2**20                 # as F1's pool asks for a copy
TEXT_MAX = 2000                         # the longest text a student sends (checks/cleaning.py)
PAIRS = ("()", "[]", "{}")
FILE_KEYS = {"kind", "settings", "cases", "builds", "from"}
SETTING_KEYS = {"item", "keys", "files"}
CASE_KEYS = {"setting", "entry", "check", "unfit", "direct", "language"}
CHECK_KEYS = {"status", "key", "parts", "verdict", "credit", "message", "at", "detail"}
BUILD_KEYS = {"options", "bodies", "files", "built", "refused"}


@dataclass
class Report:
    """What the kit found of one kind: its faults - with any, the kind fails -, its warnings, how many
    fixtures and builds ran, and the slowest."""
    name: str
    faults: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixtures: int = 0
    builds: int = 0
    slowest_s: float = 0.0
    slowest: str = ""
    budget_s: float = 0.0               # the kind's, which the slowest is held against

    @property
    def ok(self) -> bool:
        return not self.faults


# ------------------------------------------------------------------ the class
def _table(value) -> dict | None:
    """A kind's OPTIONS or MESSAGES: a table nobody changes (fixed), or None."""
    return dict(value) if isinstance(value, MappingProxyType) else None


def rules(kind: Kind, name: str | None = None) -> list[str]:
    """The rules of the contract a kind's class breaks, in words."""
    faults = []
    if not isinstance(kind, Kind):
        return [f"{type(kind).__name__} is no kind (a class of texstage.activities.Kind)"]
    if not isinstance(kind.NAME, str) or not contract.NAME.fullmatch(kind.NAME):
        faults.append(f"NAME {kind.NAME!r}: lower case letters and digits, with hyphens between - sql-query")
    elif name is not None and kind.NAME != name:
        faults.append(f"NAME {kind.NAME!r} is not its entry point's, {name!r}")
    if type(kind.API) is not int or kind.API != contract.API:
        faults.append(f"API {kind.API!r}: this texstage has API {contract.API}")
    if kind.INPUT not in contract.INPUTS:
        faults.append(f"INPUT {kind.INPUT!r}: one of {', '.join(contract.INPUTS)}")
    if kind.REDUCTION not in contract.REDUCTIONS:
        faults.append(f"REDUCTION {kind.REDUCTION!r}: one of {', '.join(contract.REDUCTIONS)}")
    budget = kind.BUDGET_S
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0 < budget <= contract.BUDGET_MAX_S:
        faults.append(f"BUDGET_S {budget!r}: seconds, more than 0 and at most {contract.BUDGET_MAX_S:g}")
    if type(kind.LIMIT) is not int or not 1 <= kind.LIMIT <= contract.LIMIT_MAX:
        faults.append(f"LIMIT {kind.LIMIT!r}: a student's entries, 1 to {contract.LIMIT_MAX}")
    declared = _table(kind.OPTIONS)
    if declared is None:
        faults.append("OPTIONS: a table of the deck's keys the kind takes, each with its type - fixed(...)")
    for key, option in (declared or {}).items():
        if not isinstance(key, str) or not contract.CODE.fullmatch(key):
            faults.append(f"OPTIONS: the key {key!r} - a word that starts with a lower case letter")
        elif key in CORE:
            faults.append(f"OPTIONS: the key {key} is the core's own")
        if not isinstance(option, Option):
            faults.append(f"OPTIONS: {key} is {option!r}, not a type of texstage.activities.options")
    codes = _table(kind.MESSAGES)
    if codes is None:
        faults.append("MESSAGES: a table of what its checks may say, each code with its arguments' names - fixed(...)")
    for code, names in (codes or {}).items():
        if not isinstance(code, str) or not contract.CODE.fullmatch(code):
            faults.append(f"MESSAGES: the code {code!r} - a word that starts with a lower case letter")
        if not isinstance(names, tuple) or not all(isinstance(n, str) and contract.CODE.fullmatch(n) for n in names) \
                or len(set(names)) != len(names):
            faults.append(f"MESSAGES: {code} takes {names!r} - the names of its arguments, each once")
    return faults


# ------------------------------------------------------------------ the fixtures' files
def folder_of(kind: Kind) -> Path:
    """Where a kind's fixtures are: tests/ beside its module."""
    return Path(inspect.getfile(type(kind))).parent / "tests"


# ------------------------------------------------------------------ what a phone loads of a kind
PHONE = ("web/hint.js", "web/input.js")         # a kind's modules for the phones (the design's 7.3)
IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*)["'](\.{1,2}/[^"']+)["']""")


def phone_files(kind: Kind) -> list[Path]:
    """What a phone loads of a kind (the design's 7.3): its modules for the phones, what they import from
    beside them, and its texts (texts/*.js). The four kinds have none of them yet: they come with the browser
    (the plan of F2, package 8), whose half of the kit measures them as a phone gets them."""
    home = Path(inspect.getfile(type(kind))).parent.resolve()
    todo = [home / p for p in PHONE if (home / p).is_file()]
    seen: list[Path] = []
    while todo:
        f = todo.pop(0).resolve()
        if f in seen:
            continue
        seen.append(f)
        for m in IMPORT.finditer(f.read_text(encoding="utf-8", errors="replace")):
            target = (f.parent / m.group(1)).resolve()
            if target.is_file() and home in target.parents:
                todo.append(target)
    return seen + sorted(p.resolve() for p in (home / "texts").glob("*.js"))


def phone_bytes(*kinds: Kind) -> int:
    """What a phone loads of these kinds, compressed as the server sends it (gzip): each file once - kinds of
    one package share theirs."""
    files = dict.fromkeys(f for kind in kinds for f in phone_files(kind))
    return sum(len(gzip.compress(f.read_bytes(), 9)) for f in files)


def _a_text(text) -> bool:
    if isinstance(text, str):
        return True
    if not isinstance(text, dict):
        return False
    if set(text) == {"repeat", "line"}:
        return type(text["repeat"]) is int and 0 <= text["repeat"] <= 1_000_000 and isinstance(text["line"], str)
    return {"deep", "open", "close"} <= set(text) <= {"deep", "open", "close", "inside", "before", "after"} \
        and type(text["deep"]) is int and 0 <= text["deep"] <= 1_000_000 \
        and all(isinstance(text[k], str) for k in text if k != "deep")


def text_of(text) -> str:
    """A fixture's text: as written, n numbered lines, or something nested n deep."""
    if isinstance(text, dict) and "repeat" in text:
        return "\n".join(text["line"].replace("{i}", str(i)) for i in range(text["repeat"]))
    if isinstance(text, dict) and "deep" in text:
        n = text["deep"]
        return text.get("before", "") + text["open"] * n + text.get("inside", "") + text["close"] * n + text.get("after", "")
    return text


def entry_of(written: dict) -> Entry:
    fields = written.get("fields")
    return Entry(text=text_of(written.get("text")), fields=tuple(fields) if isinstance(fields, list) else fields)


def label(case: dict) -> str:
    written = case.get("entry", {})
    text = json.dumps(written.get("text", written.get("fields")), ensure_ascii=True)
    return text if len(text) <= 60 else text[:57] + "..."


def _texts(table) -> bool:
    return isinstance(table, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in table.items())


def _wrong(data: dict) -> str | None:
    """What is wrong with a fixture file's shape, in words."""
    if set(data) - FILE_KEYS:
        return f"it has {', '.join(sorted(set(data) - FILE_KEYS))} - a file has kind, settings, cases and builds"
    settings, cases, builds = data.get("settings", {}), data.get("cases", []), data.get("builds", [])
    if not isinstance(settings, dict) or not isinstance(cases, list) or not isinstance(builds, list) or not (cases or builds):
        return "settings - what the kind is prepared with -, cases and builds, a case or a build at least"
    for name, setting in settings.items():
        if not isinstance(setting, dict) or set(setting) - SETTING_KEYS or not isinstance(setting.get("item", {}), dict) \
                or not isinstance(setting.get("keys", {}), dict) or not _texts(setting.get("files", {})):
            return f"setting {name} - an item, keys, and files as texts by their names"
    for i, c in enumerate(cases):
        if not isinstance(c, dict) or set(c) - CASE_KEYS:
            more = ", ".join(sorted(set(c) - CASE_KEYS)) if isinstance(c, dict) else "no table"
            return f"case {i} has {more} - a case has setting, entry, check or unfit, direct, language"
        entry = c.get("entry")
        if not isinstance(c.get("setting"), str) or c["setting"] not in settings:
            return f"case {i} - a setting of the file"
        if not isinstance(entry, dict) or set(entry) not in ({"text"}, {"fields"}) or ("text" in entry and not _a_text(entry["text"])):
            return f"case {i} - an entry: a text - as written, {{repeat, line}} or {{deep, open, close}} - or the fields"
        if ("unfit" in c) == ("check" in c):
            return f"case {i} - either unfit, the code it is refused with, or a check"
        if "unfit" in c and not isinstance(c["unfit"], str):
            return f"case {i} - unfit: the code it is refused with"
        if "check" in c:
            check = c["check"]
            status = check.get("status") if isinstance(check, dict) else None
            if not (isinstance(status, str) or (isinstance(status, list) and status and all(isinstance(s, str) for s in status))):
                return f"case {i} - a check with its status, or the statuses it may be"
            if set(check) - CHECK_KEYS:
                return f"case {i} - a check has no {', '.join(sorted(set(check) - CHECK_KEYS))}"
        if ("language" in c and not isinstance(c["language"], str)) or ("direct" in c and not isinstance(c["direct"], bool)):
            return f"case {i} - language is a tag, direct true or false"
    for i, b in enumerate(builds):
        if not isinstance(b, dict) or set(b) - BUILD_KEYS or ("built" in b) == ("refused" in b):
            return f"build {i} - options, bodies, files, and either built or refused"
        if not isinstance(b.get("options", {}), dict) or not isinstance(b.get("bodies", {}), dict) or not _texts(b.get("files", {})):
            return f"build {i} - options and bodies are tables, files texts by their names"
        if "refused" in b and not isinstance(b["refused"], str):
            return f"build {i} - refused: the refusal's words"
        if "built" in b and not (isinstance(b["built"], dict) and isinstance(b["built"].get("item"), dict)
                                 and set(b["built"]) <= {"item", "keys", "files"} and _texts(b["built"].get("files", {}))):
            return f"build {i} - built: the item, the keys, the bundle's files as texts"
    return None


def _pairs(pairs: list) -> dict:
    """A JSON object, each key once: a second "cases" would silently be the only one."""
    table = dict(pairs)
    if len(table) != len(pairs):
        twice = sorted({k for k, _ in pairs if sum(1 for q, _ in pairs if q == k) > 1})
        raise ValueError(f"{', '.join(twice)} twice in one table")
    return table


def load(folder: Path, name: str, known=None) -> tuple[list[dict], list[str], list[str]]:
    """The fixture files of a folder that are this kind's; what is wrong with the folder's files; and the
    files that are for a kind that is not installed (known: the installed kinds' names)."""
    files, faults, warnings = [], [], []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
        except (OSError, ValueError) as e:
            faults.append(f"{path.name}: not JSON - {e}")
            continue
        if not isinstance(data, dict) or not isinstance(data.get("kind"), str):
            faults.append(f"{path.name}: a file says which kind it is for - {{\"kind\": \"{name}\", ...}}")
            continue
        if data["kind"] != name:
            if known is not None and data["kind"] not in known:
                warnings.append(f"{path.name} is for a kind {data['kind']!r}, which is not installed - is the name misspelt?")
            continue
        wrong = _wrong(data)
        if wrong:
            faults.append(f"{path.name}: {wrong}")
            continue
        files.append({"file": path.name, **data})
    return files, faults, warnings


def differs(expected: dict, got: dict) -> str | None:
    """Where a check is not what its case pins."""
    for key, want in expected.items():
        have = got.get(key)
        if key == "message" and isinstance(want, dict) and isinstance(have, dict):
            if want.get("code") != have.get("code") or ("args" in want and want["args"] != have.get("args")):
                return f"message: {json.dumps(have)}, not {json.dumps(want)}"
        elif key == "status" and isinstance(want, list):
            if have not in want:
                return f"status: {json.dumps(have)}, none of {json.dumps(want)}"
        elif have != want:
            return f"{key}: {json.dumps(have)[:200]}, not {json.dumps(want)[:200]}"
    return None


# ------------------------------------------------------------------ running them
def _run(kind: Kind, prepared, step: Step, case: dict) -> tuple[dict, float, float, str | None]:
    """A case as the core takes an entry: what it gave - {"unfit": code} or the check as it is sent, as
    JSON has it -, its CPU time, its time on the clock, and the rule it broke."""
    cpu, clock = time.thread_time(), time.monotonic()

    def gave(got: dict, broken: str | None):
        return got, time.thread_time() - cpu, time.monotonic() - clock, broken

    entry = entry_of(case["entry"])
    if not case.get("direct"):
        try:
            entry = kind.normalize(step, entry)
            again = kind.normalize(step, entry) if isinstance(entry, Entry) else None
        except Unfit as e:
            return gave({"unfit": e.code}, None if isinstance(e.code, str) else f"normalize refused with the code {e.code!r}")
        except Exception as e:  # noqa: BLE001 - the rule: normalize refuses with Unfit, and raises nothing else
            return gave({}, f"normalize raised {type(e).__name__}: {e}")
        if not isinstance(entry, Entry):
            return gave({}, f"normalize gave {type(entry).__name__}, not an Entry")
        if again != entry:
            return gave({}, "normalize changes what it gave: a normal form is its own")
    try:
        check = kind.check(prepared, step, entry)
    except Exception as e:  # noqa: BLE001 - the rule: a check raises for nothing a student can send
        return gave({}, f"check raised {type(e).__name__}: {e}")
    broken = contract.fault(kind, check, step)
    if broken:
        return gave({}, broken)
    return gave(json.loads(json.dumps(check.sent())), None)       # (a tuple is a list there, as on a phone)


def _slow(kind: Kind, report: Report, what: str, cpu: float, clock: float) -> None:
    if cpu > report.slowest_s:
        report.slowest_s, report.slowest = cpu, what
    if max(cpu, clock) > kind.BUDGET_S:
        report.warnings.append(f"{what}: {clock:.2f} s, {cpu:.2f} s of them computing - over the kind's budget of "
                               f"{kind.BUDGET_S:g} s")


def _build(kind: Kind, where: str, i: int, build: dict, report: Report) -> None:
    given = build.get("files", {})

    def files(name: str, what: str) -> str:
        if name not in given:
            raise Unbuildable(f"the {what} {name} is not there (paths are the deck's)")
        return given[name]

    what = f"{where}, build {i}"
    report.builds += 1
    try:
        built = kind.build(Options(kind.OPTIONS, build.get("options", {}), files), build.get("bodies", {}))
    except Unbuildable as e:
        if "refused" not in build:
            report.faults.append(f"{what}: refused - {e} -, where it was to build")
        elif str(e) != build["refused"]:
            report.faults.append(f"{what}: refused with {str(e)!r}, not {build['refused']!r}")
        return
    except Exception as e:  # noqa: BLE001 - the rule: a build refuses with Unbuildable, and raises nothing else
        report.faults.append(f"{what}: build raised {type(e).__name__}: {e}")
        return
    if "refused" in build:
        report.faults.append(f"{what}: it built, where it was to refuse with {build['refused']!r}")
        return
    try:
        made = {"item": built.item, "keys": built.keys, "files": {n: data.decode("utf-8") for n, data in built.files.items()}}
        made = json.loads(json.dumps(made))
    except Exception as e:  # noqa: BLE001 - what a build gives is an item, keys and files as bytes
        report.faults.append(f"{what}: what it built is no item, keys and files - {type(e).__name__}: {e}")
        return
    want = {"item": build["built"]["item"], "keys": build["built"].get("keys", {}), "files": build["built"].get("files", {})}
    for part in ("item", "keys", "files"):
        if made[part] != want[part]:
            report.faults.append(f"{what}: {part}: {json.dumps(made[part])[:200]}, not {json.dumps(want[part])[:200]}")
            return


def _fixtures(kind: Kind, files: list[dict], report: Report, now: dict) -> None:
    def at(what: str) -> str:
        now["what"], now["since"] = what, time.monotonic()
        return what

    for data in files:
        where = data["file"]
        for i, build in enumerate(data.get("builds", [])):
            at(f"{where}, build {i}")
            _build(kind, where, i, build, report)
        prepared, steps = {}, {}
        for name, setting in data.get("settings", {}).items():
            item, keys = setting.get("item") or {}, setting.get("keys") or {}
            given = {n: text.encode("utf-8") for n, text in (setting.get("files") or {}).items()}
            what = at(f"{where}, setting {name}")
            try:
                prepared[name], _ = contract.first(kind, item, keys, given, most=COPY_MOST)
                steps[name] = Step(item, keys, budget_s=BUDGET_S)
                for i, check in enumerate(contract.referenced(kind, prepared[name], steps[name])):
                    broken = contract.fault(kind, check, steps[name])
                    if broken:
                        report.faults.append(f"{what}, reference {i + 1}: {broken}")
            except Exception as e:  # noqa: BLE001 - a setting the kind cannot be prepared with fails its cases
                prepared.pop(name, None)
                report.faults.append(f"{what}: preparing raised {type(e).__name__}: {e}")
        cases = [(i, c) for i, c in enumerate(data.get("cases", [])) if c["setting"] in prepared]
        gave: dict[int, tuple] = {}
        for order in (cases, cases[::-1]):
            for i, case in order:
                step = steps[case["setting"]]
                if case.get("language"):
                    step = Step(step.item, step.keys, case["language"], step.budget_s)
                what = at(f"{where}, case {i} ({label(case)})")
                got, cpu, clock, broken = _run(kind, prepared[case["setting"]], step, case)
                if i in gave:                              # the second time, in the other order
                    if (got, broken) != gave[i]:
                        second = broken or json.dumps(got)[:200]
                        report.faults.append(f"{what}: another check the second time - {second} -: a check changed what "
                                             f"was prepared")
                    continue
                gave[i] = (got, broken)
                report.fixtures += 1
                _slow(kind, report, what, cpu, clock)
                if broken:
                    report.faults.append(f"{what}: {broken}")
                elif "unfit" in case:
                    if got != {"unfit": case["unfit"]}:
                        report.faults.append(f"{what}: {json.dumps(got)[:200]}, not refused as {case['unfit']}")
                elif "unfit" in got:
                    report.faults.append(f"{what}: refused as {got['unfit']}, where a check was to come")
                else:
                    wrong = differs(case["check"], got)
                    if wrong:
                        report.faults.append(f"{what}: {wrong}")
        if kind.INPUT == "code" and prepared:
            name = next(iter(prepared))
            for pair in PAIRS:                              # as deep as a text is long: it must come back
                text = pair[0] * (TEXT_MAX // 2) + pair[1] * (TEXT_MAX // 2)
                what = at(f"{where}, a text nested {TEXT_MAX // 2} deep in {pair}")
                got, cpu, clock, broken = _run(kind, prepared[name], steps[name], {"entry": {"text": text}})
                if broken:
                    report.faults.append(f"{what}: {broken}")
                else:
                    _slow(kind, report, what, cpu, clock)


def check(kind: Kind, name: str | None = None, folder: Path | None = None, known=None) -> Report:
    """A kind held against the contract: its class, then its fixtures - on a thread with a worker's stack,
    which is given up when a check does not come back. known: the installed kinds' names, for the files
    of the folder that are no kind's."""
    report = Report(name or getattr(kind, "NAME", "?"))
    report.faults += rules(kind, name)
    if report.faults:
        return report                                       # a class that breaks a rule: its fixtures say nothing
    report.budget_s = kind.BUDGET_S
    try:
        folder = folder if folder is not None else folder_of(kind)
    except (TypeError, OSError):                            # a class of no file
        folder = None
    files, faults, warnings = load(folder, kind.NAME, known) if folder is not None else ([], [], [])
    report.faults += faults
    report.warnings += warnings
    if not files:
        if not faults:
            report.faults.append(f"no fixtures: {kind.NAME} has none in tests/*.json beside its module")
        return report
    now = {"what": "", "since": time.monotonic()}

    def work():
        try:
            _fixtures(kind, files, report, now)
        except BaseException as e:  # noqa: BLE001 - the kit's own failure is said, not lost with its thread
            report.faults.append(f"the kit failed at {now['what'] or 'its start'} - {type(e).__name__}: {e}")

    old = threading.stack_size(STACK)
    try:
        thread = threading.Thread(target=work, name="texstage-kit", daemon=True)
        thread.start()
    finally:
        threading.stack_size(old)
    while thread.is_alive():
        thread.join(0.1)
        if thread.is_alive() and time.monotonic() - now["since"] > HANG_S:
            report.faults.append(f"{now['what']}: not back after {HANG_S:g} s - it hangs, or takes no heed of its budget; "
                                 f"the kit gave the kind up there")
            break
    return report


def said(report: Report, found=None) -> str:
    """A report in words, for the terminal."""
    head = report.name + (f" ({found.package} {found.version}, API {found.api})" if found is not None else "")
    if report.fixtures or report.builds:
        head += f": {report.fixtures} fixtures, twice and in both orders"
        if report.builds:
            head += f", {report.builds} builds"
        if report.slowest:
            head += f"; the slowest {report.slowest_s:.3f} s of {report.budget_s:g} s - {report.slowest}"
    lines = [head] + [f"  warning: {w}" for w in report.warnings] + [f"  FAILS: {f}" for f in report.faults]
    return "\n".join(lines)
