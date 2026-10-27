# SPDX-License-Identifier: Apache-2.0
"""Small shared-block renderer for the maintained reference content."""
import re

def markdown(data):
    lines = ["<!-- Generated; edit the shared reference content, then rebuild. -->",
             "# " + data["title"], "", data["subtitle"], "", "## Contents", ""]
    for page in data["pages"]:
        slug=re.sub(r"[^a-z0-9 -]", "", page["title"].lower()).replace(" ", "-")
        lines.append(f"- [{page['title']}](#{slug})")
    for page in data["pages"]:
        lines += ["", "## " + page["title"], ""]
        for b in page["blocks"]:
            if "p" in b: lines += [b["p"], ""]
            elif "heading" in b: lines += ["### " + b["heading"], ""]
            elif "code" in b: lines += ["```", b["code"], "```", ""]
            elif "bullets" in b: lines += ["- "+s for s in b["bullets"]] + [""]
            elif "table" in b:
                t=b["table"]
                lines += ["| "+" | ".join(t["headers"])+" |",
                          "| "+" | ".join("---" for _ in t["headers"])+" |"]
                lines += ["| "+" | ".join(row)+" |" for row in t["rows"]]
                lines += [""]
    return "\n".join(lines).rstrip()+"\n"
