# SPDX-License-Identifier: Apache-2.0
"""Check the maintained public documentation: its local Markdown file links, that no text in it is UTF-8
read as Windows-1252 and saved again ("â†’" for "→", "Ã¼" for "ü"), that the files naming the current
version name pyproject.toml's, and that every docs/ path a tracked file names - the code's comments too -
is there."""
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
files = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
files += list((ROOT / "docs/manual-latex").glob("*.md"))
files += list((ROOT / "examples").rglob("*.md"))

# A docs/ path in any tracked text file - a link, a path in backticks, a comment's - must exist, relative to
# the file or to the repository. provenance/ records the source repository's own paths; besides it, only
# these name files that are not in this repository, on purpose.
ELSEWHERE = {
    "docs/demonstration.md", "docs/demonstration-transcript.md",    # kept out of it (MANIFEST.in,
    "docs/media/demo", "docs/media/demo/",                          # maintenance/check_public_content.py)
    "docs/pilot/",                                                  # the private repository's
    "docs/package-and-style-modules.md", "docs/validation-phase2.json",       # lecture-tools'
}
DOCS_PATH = re.compile(r"(?<![\w./-])((?:\.\./)*docs/[\w./-]*[\w/])")

# The files that name the current version, and where (docs/releasing.md lists them): each pattern must be
# found, and every version it finds must be pyproject.toml's.
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
V = r"(\d+(?:\.\d+)*(?:\.?(?:a|b|rc|dev|post)\d+)*)"          # a version such as 0.2.1.dev8
CURRENT = {
    "README.md": [rf"\*\*texstage {V}\*\*, the current stable release"],
    "CHANGELOG.md": [rf"\A# Changelog\s+## {V} — the current stable release"],
    "site/index.html": [rf"texstage {V} is the current stable release"],
    "docs/manual-content.json": [rf'(?m)^  "version": "{V}"', rf"Version {V} - the current stable release",
                                 rf"the version is {V} for this edition"],
    "docs/releasing.md": [rf"The current version is\s+{V}, the current stable release"],
    "docs/compilation.md": [rf"the current\s+{V}\s+release"],
    "docs/powerpoint.md": [rf"the current\s+{V}\s+release"],
    "docs/installation-advanced.md": [rf"texstage-{V}-py3-none-any\.whl"],
    "docs/development.md": [rf"texstage-{V}-py3-none-any\.whl"],
    "examples/showcase/COVERAGE.md": [rf"the current texstage\s+{V}\s+release"],
}

# A UTF-8 lead byte, then one to three continuation bytes (0x80-0xBF), each as Windows-1252 shows it.
CONTINUATION = "".join(bytes([b]).decode("cp1252", errors="ignore") or chr(b) for b in range(0x80, 0xC0))
GARBLED = re.compile("[Â-ô][" + re.escape(CONTINUATION) + "]{1,3}")


def garbled(run):
    """What `run` was before UTF-8 was read as Windows-1252 - a letter, sign or arrow a text holds -, or None."""
    raw = bytes(ord(c) if ord(c) < 0x100 else c.encode("cp1252")[0] for c in run)
    try:
        char = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return char if " " <= char <= "ɏ" or " " <= char <= "➿" else None


errors, garbles = [], []
for path in files:
    source = path.read_text(encoding="utf-8")
    for run in GARBLED.finditer(source):
        if char := garbled(run.group()):
            line = source.count("\n", 0, run.start()) + 1
            garbles.append(f"{path.relative_to(ROOT)}:{line}: {run.group()} for {char}")
    text = re.sub(r"(?ms)^(```|~~~).*?^\1[^\n]*$", "", source)
    for link in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
        url = link.split(' "', 1)[0].strip('<>')
        if re.match(r"[a-zA-Z][\w+.-]*:", url) or url.startswith('#'):
            continue
        target = unquote(url.split('#', 1)[0])
        if target and not (path.parent / target).exists():
            errors.append(f"{path.relative_to(ROOT)}: {url}")
versions = []
for name, patterns in CURRENT.items():
    source = (ROOT / name).read_text(encoding="utf-8")
    for pattern in patterns:
        found = re.findall(pattern, source)
        if not found:
            versions.append(f"{name}: nothing matches {pattern!r} - name the version as before, or change "
                            f"the pattern in maintenance/check_docs.py")
        versions += [f"{name}: {version}" for version in found if version != VERSION]
missing, texts = [], 0
tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=True)
for name in filter(None, tracked.stdout.split("\0")):
    if name.startswith("provenance/"):
        continue
    try:
        source = (ROOT / name).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        continue                                       # a picture, a PDF, a font; a file deleted here
    texts += 1
    for number, line in enumerate(source.splitlines(), 1):
        for target in DOCS_PATH.findall(line):
            bare = re.sub(r"^(\.\./)+", "", target)
            here = (ROOT / name).parent / target
            if bare not in ELSEWHERE and not here.exists() and not (ROOT / bare).exists():
                missing.append(f"{name}:{number}: {target}")
assert not errors, "Broken documentation links:\n" + "\n".join(errors)
assert not garbles, "Text garbled by an encoding (UTF-8 read as Windows-1252):\n" + "\n".join(garbles)
assert not versions, f"Not the current version, pyproject.toml's {VERSION}:\n" + "\n".join(versions)
assert not missing, ("docs/ paths that are not in the repository - correct them; another repository's file "
                     "goes into ELSEWHERE in maintenance/check_docs.py:\n" + "\n".join(missing))
print(f"PASS: local file links and encoding in {len(files)} maintained Markdown documents, "
      f"version {VERSION} in the {len(CURRENT)} files that name it, the docs/ paths in {texts} tracked texts")
