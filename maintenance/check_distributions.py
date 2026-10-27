# SPDX-License-Identifier: Apache-2.0
"""Build sdist/wheel offline, compare wheel contents, and write artifact hashes.

Install requirements/build.txt first. The output directory must be empty/new.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd):
    subprocess.run([sys.executable, *args], cwd=cwd, check=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assert not list(output.iterdir()), "Use a new output folder; old artifacts are never deleted"
    run("maintenance/lock_dependencies.py", "--check", cwd=ROOT)
    run("-m", "build", "--no-isolation", "--sdist", "--wheel", "--outdir", str(output), cwd=ROOT)
    wheel, = output.glob("*.whl")
    sdist, = output.glob("*.tar.gz")
    with tempfile.TemporaryDirectory(prefix="sdist-rebuild-") as tmp:
        target = Path(tmp)
        with tarfile.open(sdist) as archive:
            archive.extractall(target, filter="data")
        unpacked, = target.iterdir()
        run("maintenance/lock_dependencies.py", "--check", cwd=unpacked)
        run("-m", "build", "--no-isolation", "--wheel", "--outdir", str(target / "wheels"), cwd=unpacked)
        rebuilt, = (target / "wheels").glob("*.whl")
        with zipfile.ZipFile(wheel) as a, zipfile.ZipFile(rebuilt) as b:
            assert set(a.namelist()) == set(b.namelist()), "Wheel inventory differs after sdist rebuild"
            assert not [name for name in a.namelist() if a.read(name) != b.read(name)], "Wheel contents differ after sdist rebuild"
            assert not any("__pycache__" in n or n.endswith(".env") for n in a.namelist())
            assert any(n.endswith("/NOTICE") for n in a.namelist())
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel, sdist)}
    (output / "SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in hashes.items()), encoding="utf-8")
    (output / "validation.json").write_text(json.dumps({"artifacts": hashes, "sdist_rebuild": "all wheel members byte-identical"}, indent=2) + "\n", encoding="utf-8")
    print("PASS: wheel/sdist built, source rebuild matches, SHA256SUMS written")


if __name__ == "__main__":
    main()
