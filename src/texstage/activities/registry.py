# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The kinds that are installed (docs/architecture/activity-framework-design.md, 7.2): each is found by
its package's entry point in the group texstage.kinds -

    [project.entry-points."texstage.kinds"]
    sql-query = "texstage_kinds_sql:SqlQuery"

- and made once. `texstage kinds` lists them: name, package, version, API. A kind that cannot be used
is listed with the reason - its module does not import, its class is no Kind, its name is not its
entry point's, it implements another API, it cannot be made (a kind of an engine whose library is not
installed), its package names it twice, another package brings a kind of the same name - and is no kind
of the server's: nothing is installed half. Whatever a package does when it is imported - raise, or
leave - is its kind's reason, not the end of the list.

    found()        every entry point, usable or not
    kinds()        the usable kinds by name
    kind(name)     one of them, or Missing - which says what to install
"""
from __future__ import annotations

import dataclasses
import functools
from dataclasses import dataclass
from importlib import metadata

from texstage.activities.kind import API, NAME, Kind

GROUP = "texstage.kinds"


class Missing(LookupError):
    """No kind of that name can be used here: the message says why, and what is installed."""


@dataclass(frozen=True)
class Found:
    """An entry point of the group: the kind it gives, or why it gives none."""
    name: str
    package: str
    version: str
    api: object = None
    kind: Kind | None = None
    fault: str | None = None


def _said(e: BaseException) -> str:
    """An exception in a line: its type and the first line of its words."""
    words = str(e).strip()
    return f"{type(e).__name__}: {words.splitlines()[0]}" if words else type(e).__name__


def _load(point) -> Found:
    dist = getattr(point, "dist", None)
    package, version = (dist.name, dist.version) if dist is not None else ("?", "?")

    def no(fault: str, api=None) -> Found:
        return Found(point.name, package, version, api, None, fault)

    try:
        cls = point.load()
    except (Exception, SystemExit) as e:  # noqa: BLE001 - whatever a package's import does is why its kind is not here
        return no(f"it does not load - {_said(e)}")
    if not (isinstance(cls, type) and issubclass(cls, Kind)):
        return no(f"{point.value} is no kind (a class of texstage.activities.Kind)")
    try:
        name, api = cls.NAME, cls.API
    except Exception as e:  # noqa: BLE001 - a class that cannot even say its name
        return no(f"its class cannot be read - {_said(e)}")
    if name != point.name:
        return no(f"its class is named {name!r}, its entry point {point.name!r}", api)
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return no("a kind's name is lower case letters and digits, with hyphens between: sql-query", api)
    if type(api) is not int or api != API:
        return no(f"it implements API {api!r}, this texstage API {API}", api)
    try:
        return Found(point.name, package, version, api, cls())
    except (Exception, SystemExit) as e:  # noqa: BLE001 - as above: its engine's library is not there, say
        return no(f"it cannot be made - {_said(e)}", api)


def read(points) -> list[Found]:
    """What a list of entry points gives, by name. A name twice - in one package, or in two - is no kind:
    which of them would a deck get?"""
    found = sorted((_load(p) for p in points), key=lambda f: (f.name, f.package))
    out = []
    for f in found:
        same = [o for o in found if o.name == f.name]
        others = sorted({o.package for o in same} - {f.package})
        if others:
            f = dataclasses.replace(f, kind=None, fault=f"{', '.join(others)} brings a kind of this name too")
        elif len(same) > 1:
            f = dataclasses.replace(f, kind=None, fault="its package names this kind twice")
        out.append(f)
    return out


@functools.cache
def found() -> tuple[Found, ...]:
    """Every entry point of the group among the installed packages, read once (forget() reads anew)."""
    return tuple(read(metadata.entry_points(group=GROUP)))


def forget() -> None:
    found.cache_clear()


def kinds() -> dict[str, Kind]:
    return {f.name: f.kind for f in found() if f.kind is not None}


def kind(name: str) -> Kind:
    for f in found():
        if f.name == name:
            if f.kind is not None:
                return f.kind
            raise Missing(f"the kind {name} of {f.package} {f.version} cannot be used: {f.fault}")
    here = ", ".join(sorted(kinds())) or "none"
    raise Missing(f"no kind {name} is installed (installed: {here}) - a kind comes with its package, "
                  f"as texstage-kinds-sql brings sql-query")
