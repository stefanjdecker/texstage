# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""PEP 517 backend for portable plugin wheels, delegating builds to setuptools.

Use build-backend = 'texstage.plugins.sdk' and include texstage-plugin.json in
MANIFEST.in. The source manifest omits resources; the wheel inventory is generated
from the actual package bytes and inserted into dist-info with a correct RECORD.
An sdist contains the original manifest and therefore rebuilds the same payload.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile

from . import PluginError
from .manifest import canonical, load_manifest, read_json, resource_path


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    from setuptools import build_meta
    name = build_meta.build_wheel(wheel_directory, config_settings, metadata_directory)
    if not name.endswith("-py3-none-any.whl"):
        raise PluginError("API 1 plugin wheels must be py3-none-any")
    path = Path(wheel_directory) / name
    with zipfile.ZipFile(path) as wheel:
        contents = {i.filename: wheel.read(i) for i in wheel.infolist() if not i.is_dir()}
    infos = {n.split("/")[0] for n in contents if ".dist-info/" in n}
    if len(infos) != 1:
        raise PluginError("expected one dist-info directory")
    info = infos.pop()
    manifest = read_json(Path("texstage-plugin.json").read_bytes())
    resources = {n: {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
                 for n, raw in contents.items() if not n.startswith(info + "/")}
    for n in resources: resource_path(n)
    manifest["resources"] = resources
    raw = canonical(manifest)
    load_manifest(raw)
    contents[f"{info}/texstage-plugin.json"] = raw + b"\n"
    record = f"{info}/RECORD"
    contents.pop(record, None)
    rows = io.StringIO(newline="")
    writer = csv.writer(rows, lineterminator="\n")
    for filename, data in sorted(contents.items()):
        h = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow((filename, "sha256=" + h, str(len(data))))
    writer.writerow((record, "", ""))
    contents[record] = rows.getvalue().encode("utf-8")
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for filename, data in sorted(contents.items()):
            entry = zipfile.ZipInfo(filename, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            wheel.writestr(entry, data)
    temp.replace(path)
    return name


def build_sdist(sdist_directory, config_settings=None):
    from setuptools import build_meta
    return build_meta.build_sdist(sdist_directory, config_settings)


def get_requires_for_build_wheel(config_settings=None):
    return ["setuptools>=77"]


get_requires_for_build_sdist = get_requires_for_build_wheel
