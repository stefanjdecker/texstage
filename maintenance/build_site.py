# SPDX-License-Identifier: Apache-2.0
"""Assemble the www.texstage.org homepage from site/ and the manual's media.

Copies site/ and the screenshots and manual PDF it uses into one folder
(default _site/) and checks that every local link, image and anchor in its pages resolves.
The site shares these files with the manual instead of keeping copies of its own.
GitHub Pages publishes the folder (.github/workflows/pages.yml).
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
MEDIA = {  # published path -> source
    "images/manual": ROOT / "docs/images/manual",
    "manual.pdf": ROOT / "docs/manual.pdf",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs = set(), []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id":
                self.ids.add(value)
            elif name in ("href", "src", "poster") and value:
                self.refs.append(value)


def broken_links(output):
    errors = []
    for page in output.rglob("*.html"):
        links = Links()
        links.feed(page.read_text(encoding="utf-8"))
        for ref in links.refs:
            url = urlsplit(ref)
            if url.scheme or url.netloc:
                continue
            missing = (not (page.parent / unquote(url.path)).exists() if url.path
                       else url.fragment not in links.ids)
            if missing:
                errors.append(f"{page.relative_to(output)}: {ref}")
    return errors


def is_site_build(output):
    """Missing, empty, or holding only what a build puts there (also when half deleted)."""
    names = {path.name for path in SITE.iterdir()} | {Path(target).parts[0] for target in MEDIA}
    return not output.exists() or {path.name for path in output.iterdir()} <= names


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "_site")
    output = parser.parse_args().output_dir.resolve()
    if SITE.is_relative_to(output) or output.is_relative_to(SITE) or not is_site_build(output):
        parser.error(f"{output} is not a previous site build; choose another --output-dir")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(SITE, output, ignore=shutil.ignore_patterns("README.md"))
    for target, source in MEDIA.items():
        if source.is_dir():
            shutil.copytree(source, output / target, ignore=shutil.ignore_patterns("*.json"))
        else:
            shutil.copy2(source, output / target)
    errors = broken_links(output)
    assert not errors, "Broken links in the site:\n" + "\n".join(errors)
    print(f"PASS: site assembled in {output}; all local links resolve")


if __name__ == "__main__":
    main()
