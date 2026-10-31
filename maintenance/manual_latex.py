# SPDX-License-Identifier: Apache-2.0
"""Render the illustrated texstage manual as a conventional LaTeX article."""
from __future__ import annotations

import re


def literal(text):
    """Escape prose, including CLI flags, paths and LaTeX examples."""
    replacements = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def breakable(text, code=False):
    """Allow long identifiers and paths to wrap without adding printed characters."""
    result=[]
    letters=0
    for index, char in enumerate(text):
        result.append(literal(char))
        letters = letters + 1 if char.isalnum() else 0
        if index + 1 < len(text) and (char in "/_.-\\\\{}=" or (code and letters >= 10)):
            result.append(r"\allowbreak{}")
            letters=0
    return "".join(result)


def inline(text):
    tokens = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)")
    parts = []
    start = 0
    for token in tokens.finditer(text):
        parts.append(breakable(text[start:token.start()]))
        code, bold, label, url = token.groups()
        if code is not None:
            parts.append(r"\texttt{" + breakable(code, code=True) + "}")
        elif bold is not None:
            parts.append(r"\textbf{" + inline(bold) + "}")
        else:
            target = literal(url)
            if not re.match(r"[a-zA-Z][\w+.-]*:", url):
                target = r"\manualdocroot " + target
            parts.append(r"\href{" + target + "}{" + inline(label) + "}")
        start = token.end()
    parts.append(breakable(text[start:]))
    return "".join(parts)


def blocks(items):
    result = []
    for item in items:
        if "p" in item:
            result += [inline(item["p"]) + r"\par", ""]
        elif "heading" in item:
            result += [r"\manualsubheading{" + inline(item["heading"]) + "}"]
        elif "bullets" in item:
            result += [r"\begin{itemize}"]
            result += [r"\item " + inline(text) for text in item["bullets"]]
            result += [r"\end{itemize}", ""]
        elif "code" in item:
            keep_together = len(item["code"].splitlines()) <= 30
            if keep_together:
                result += [r"\par\noindent\begin{minipage}{\linewidth}"]
            result += [r"\begin{Verbatim}", item["code"], r"\end{Verbatim}"]
            if keep_together:
                result += [r"\end{minipage}\par\smallskip"]
            result += [""]
        elif "table" in item:
            table = item["table"]
            widths = table.get("widths", [1 / len(table["headers"])] * len(table["headers"]))
            columns = "".join(
                r">{\raggedright\arraybackslash}p{\dimexpr"
                + f"{width:.6f}" + r"\linewidth-2\tabcolsep\relax}"
                for width in widths
            )
            result += [r"{\small", r"\begin{longtable}{" + columns + "}", r"\toprule"]
            header = " & ".join(r"\textbf{" + inline(t) + "}" for t in table["headers"]) + r" \\"
            result += [header, r"\midrule", r"\endfirsthead",
                       r"\toprule", header, r"\midrule", r"\endhead",
                       r"\midrule", r"\endfoot", r"\bottomrule", r"\endlastfoot"]
            for row in table["rows"]:
                result += [" & ".join(inline(t) for t in row) + r" \\ \addlinespace[3pt]"]
            result += [r"\end{longtable}}", ""]
        else:
            raise ValueError(f"Unknown manual block: {item}")
    return result

def picture(spec, phone=False):
    assert re.fullmatch(r"images/manual/[a-zA-Z0-9._-]+", spec["file"]), spec["file"]
    width=r"0.40\linewidth" if phone else r"\linewidth"
    return [
        r"\begin{figure}[!htbp]", r"\centering",
        r"\includegraphics[width="+width+r",height=0.45\textheight,keepaspectratio]{../"+spec["file"]+"}",
        r"\caption{"+inline(spec["caption"])+"}", r"\end{figure}",
    ]


def gallery(images, title):
    count=len(images)
    fraction=0.96/count
    lines=[r"\begin{figure}[!htbp]",r"\centering"]
    for i,spec in enumerate(images):
        assert re.fullmatch(r"images/manual/[a-zA-Z0-9._-]+",spec["file"]),spec["file"]
        if i: lines += [r"\hfill"]
        lines += [r"\begin{subfigure}[t]{"+f"{fraction:.3f}"+r"\linewidth}",
                  r"\centering",
                  r"\includegraphics[width=\linewidth,height=0.43\textheight,keepaspectratio]{../"+spec["file"]+"}",
                  r"\caption{"+inline(spec["caption"])+"}",
                  r"\end{subfigure}"]
    lines += [r"\caption{"+inline(title)+"}",r"\end{figure}"]
    return lines


def latex(data):
    cover=data["pages"][0]
    lines=[
        "% SPDX-License-Identifier: Apache-2.0",
        "% Generated from docs/manual-content.json by maintenance/build_manual.py.",
        r"\providecommand{\manualdocroot}{../}",
        r"\documentclass[a4paper,11pt]{article}",r"\usepackage{manual}",
        r"\newcommand{\manualversion}{"+literal(data["version"])+"}",
        r"\newcommand{\manualdate}{"+literal(data["date"])+"}",
        r"\hypersetup{pdftitle={"+literal(data["title"])+r"},pdfauthor={texstage project}}",
        r"\title{"+inline(cover["title"])+r"\\[0.5em]\large "+inline(cover["subtitle"])+"}",
        r"\author{texstage project}",r"\date{\manualdate\\Version \manualversion}",
        r"\begin{document}",r"\maketitle",r"\begin{abstract}",
        *blocks(cover["blocks"]),r"\end{abstract}",r"{\small\setlength{\parskip}{0pt}\tableofcontents}",r"\clearpage",
        *gallery(cover["images"],"Presenter and participant interfaces"),
    ]
    reference_started = False
    for page in data["pages"][1:]:
        if page.get("reference") and not reference_started:
            lines += [r"\FloatBarrier"]
            reference_started = True
        lines += [r"\manualsection{"+inline(page["title"])+"}",*blocks(page["blocks"])]
        if page["layout"]=="gallery":
            lines += gallery(page["images"],page["title"])
        else:
            for index,spec in enumerate(page["images"]):
                lines += picture(spec,phone=(page["layout"]=="mixed" and index==0))
    return "\n".join(lines+[r"\end{document}",""])
