# SPDX-License-Identifier: Apache-2.0
"""Regenerate or check the hashed third-party dependency locks (Python 3.12+)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
UV_VERSION = "0.9.12"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    meta = project["project"]
    runtime = list(meta["dependencies"])
    if meta["name"] == "lecture-tools":
        pair = json.loads((ROOT / "requirements/texstage.json").read_text())
        assets = json.loads((ROOT / "texstage-assets.lock.json").read_text())
        assert pair["version"] == assets["texstage_version"]
        assert pair["artifact_sha256"] == assets["artifact_sha256"]
        for name, dependencies in meta["optional-dependencies"].items():
            if name != "dev":
                for requirement in dependencies:
                    if requirement.startswith("texstage"):
                        assert requirement == "texstage==" + pair["version"]
                    else:
                        runtime.append(requirement)
        runtime.extend(pair["requires_dist"])
    runtime = sorted(set(runtime), key=str.lower)
    build = [*project["build-system"]["requires"], "build>=1.2,<2", "uv==" + UV_VERSION]
    return {
        "runtime": "\n".join(runtime) + "\n",
        "build": "\n".join(build) + "\n",
        "dev": "-r runtime.in\n-r build.in\n-c runtime.txt\n-c build.txt\n" + "\n".join(meta["optional-dependencies"]["dev"]) + "\n",
    }


def snapshot():
    paths = ["pyproject.toml", "maintenance/lock_dependencies.py"]
    paths += ["requirements/" + profile + suffix for profile in ("runtime", "build", "dev") for suffix in (".in", ".txt")]
    if (ROOT / "requirements/texstage.json").exists():
        paths += ["requirements/texstage.json", "texstage-assets.lock.json"]
    return {name: digest(ROOT / name) for name in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Offline freshness/integrity check, no downloads or changes")
    parser.add_argument("--upgrade", action="store_true", help="Re-resolve all packages instead of preferring current pins")
    args = parser.parse_args()
    expected = inputs()
    if args.check:
        for profile, contents in expected.items():
            assert (ROOT / f"requirements/{profile}.in").read_text() == contents, f"Stale {profile}.in; regenerate locks"
        manifest = json.loads((ROOT / "requirements/lock-manifest.json").read_text())
        assert manifest["files"] == snapshot(), "Dependency inputs or locks changed; regenerate locks"
        assert manifest["resolver"] == "uv " + UV_VERSION
        for profile in expected:
            text = (ROOT / f"requirements/{profile}.txt").read_text()
            assert "--hash=sha256:" in text
            assert "file:" not in text and "https://" not in text, "Locks must not embed local paths or index credentials"
        print("Dependency inputs and lock hashes are current")
        return
    result = subprocess.run(["uv", "--version"], check=True, capture_output=True, text=True)
    assert result.stdout.split()[1] == UV_VERSION, f"Use uv {UV_VERSION}, pinned in requirements/build.txt"
    # Resolve all three profiles before replacing any checked-in file.
    with tempfile.TemporaryDirectory(prefix="dependency-locks-") as temporary:
        work = Path(temporary)
        for profile, contents in expected.items():
            (work / (profile + ".in")).write_text(contents, encoding="utf-8", newline="\n")
            old = ROOT / f"requirements/{profile}.txt"
            if old.exists():
                (work / old.name).write_bytes(old.read_bytes())
            command = ["uv", "--no-config", "pip", "compile", profile + ".in", "--universal",
                       "--python-version", "3.12", "--generate-hashes", "--no-header", "--no-annotate",
                       "--default-index", "https://pypi.org/simple", "-o", profile + ".txt", "--quiet"]
            if args.upgrade:
                command.append("--upgrade")
            subprocess.run(command, cwd=work, check=True)
        for path in work.iterdir():
            (ROOT / "requirements" / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    manifest = {"schema_version": 1, "resolver": "uv " + UV_VERSION,
                "python": ">=3.12", "universal": True, "files": snapshot()}
    (ROOT / "requirements/lock-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Updated runtime, build and dev locks; review changes and run the CI checks")


if __name__ == "__main__":
    main()
