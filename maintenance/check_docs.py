# SPDX-License-Identifier: Apache-2.0
"""Check the maintained public documentation: its local Markdown file links, and that no text in it is UTF-8
read as Windows-1252 and saved again ("â†’" for "→", "Ã¼" for "ü")."""
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
files = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
files += list((ROOT / "docs/manual-latex").glob("*.md"))
files += list((ROOT / "examples").rglob("*.md"))

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
assert not errors, "Broken documentation links:\n" + "\n".join(errors)
assert not garbles, "Text garbled by an encoding (UTF-8 read as Windows-1252):\n" + "\n".join(garbles)
print(f"PASS: local file links and encoding in {len(files)} maintained Markdown documents")
