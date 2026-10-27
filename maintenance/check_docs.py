# SPDX-License-Identifier: Apache-2.0
"""Check local Markdown file links in maintained public documentation."""
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
files = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
files += list((ROOT / "docs/manual-latex").glob("*.md"))
files += list((ROOT / "examples").rglob("README.md"))
errors = []
for path in files:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?ms)^(```|~~~).*?^\1[^\n]*$", "", text)
    for link in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
        url = link.split(' "', 1)[0].strip('<>')
        if re.match(r"[a-zA-Z][\w+.-]*:", url) or url.startswith('#'):
            continue
        target = unquote(url.split('#', 1)[0])
        if target and not (path.parent / target).exists():
            errors.append(f"{path.relative_to(ROOT)}: {url}")
assert not errors, "Broken documentation links:\n" + "\n".join(errors)
print(f"PASS: local file links in {len(files)} maintained Markdown documents")
