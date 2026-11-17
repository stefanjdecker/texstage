# SPDX-License-Identifier: Apache-2.0
"""Build sdist/wheel offline, compare wheel contents, and write artifact hashes - texstage's and those of
the kinds of live activities beside it (kinds/*: packages of their own, installed after texstage).

Install requirements/build.txt first. The output directory must be empty/new.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd):
    subprocess.run([sys.executable, *args], cwd=cwd, check=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


def packages():
    """texstage, then each kind's package (kinds/*/pyproject.toml)."""
    return [ROOT, *(path.parent for path in sorted((ROOT / "kinds").glob("*/pyproject.toml")))]


def leftovers(source):
    """What a build leaves in a source folder: build/ and the *.egg-info metadata - an old one hides the
    installed package's entry points wherever its folder comes first on sys.path (the kinds' too)."""
    return {source / "build", *source.glob("*.egg-info"), *source.glob("src/*.egg-info")}


@contextlib.contextmanager
def cleaned(source):
    """What a build leaves in the source folder goes again once it is done - or has failed -, unless it was
    there before: a developer's build/ or editable install's metadata stays."""
    there = {p for p in leftovers(source) if p.exists()}
    try:
        yield
    finally:
        for path in leftovers(source) - there:
            shutil.rmtree(path, ignore_errors=True)


def one(paths, what):
    assert len(paths) == 1, f"expected one {what}, found {sorted(p.name for p in paths)}"
    return paths[0]


def artifacts(source, output):
    """A package's wheel and source archive, built into output; a wheel built again from that archive must
    be the same, member for member. What the build left in the source folder goes again."""
    before = set(output.iterdir())
    with cleaned(source):
        run("-m", "build", "--no-isolation", "--sdist", "--wheel", "--outdir", str(output), cwd=source)
    new = set(output.iterdir()) - before
    wheel = one([p for p in new if p.suffix == ".whl"], f"wheel of {source.name}")
    sdist = one([p for p in new if p.name.endswith(".tar.gz")], f"source archive of {source.name}")
    with tempfile.TemporaryDirectory(prefix="sdist-rebuild-") as tmp:
        target = Path(tmp)
        with tarfile.open(sdist) as archive:
            archive.extractall(target, filter="data")
        unpacked = one(list(target.iterdir()), f"folder in {sdist.name}")
        if source == ROOT:
            run("maintenance/lock_dependencies.py", "--check", cwd=unpacked)
        run("-m", "build", "--no-isolation", "--wheel", "--outdir", str(target / "wheels"), cwd=unpacked)
        rebuilt = one(list((target / "wheels").glob("*.whl")), f"wheel rebuilt from {sdist.name}")
        with zipfile.ZipFile(wheel) as a, zipfile.ZipFile(rebuilt) as b:
            assert set(a.namelist()) == set(b.namelist()), f"{wheel.name}: wheel inventory differs after sdist rebuild"
            assert not [name for name in a.namelist() if a.read(name) != b.read(name)], \
                f"{wheel.name}: wheel contents differ after sdist rebuild"
            assert not any("__pycache__" in n or n.endswith(".env") for n in a.namelist()), \
                f"{wheel.name}: bytecode or an .env file in the wheel"
            assert any(n.endswith("/NOTICE") for n in a.namelist()), f"{wheel.name}: no NOTICE"
    return wheel, sdist


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assert not list(output.iterdir()), "Use a new output folder; old artifacts are never deleted"
    run("maintenance/lock_dependencies.py", "--check", cwd=ROOT)
    built = [artifacts(source, output) for source in packages()]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for pair in built for p in pair}
    (output / "SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in hashes.items()), encoding="utf-8")
    (output / "validation.json").write_text(json.dumps({"artifacts": hashes, "sdist_rebuild": "all wheel members byte-identical"}, indent=2) + "\n", encoding="utf-8")
    names = [tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"]
             for source in packages()]
    print(f"PASS: wheel and sdist of {', '.join(names)} built, source rebuilds match, SHA256SUMS written")


if __name__ == "__main__":
    main()
