# SPDX-License-Identifier: Apache-2.0
"""Check an installed texstage wheel outside the source checkout (needs pdflatex) - with the wheels of the
kinds of live activities beside it (kinds/*): found by their entry points, their kit passes, and a deck with
an activity of each of texstage's kinds builds and is served (check_kinds_served.py --every)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import texstage
from texstage.api import LATEX_FILES, latex_resources
import texstage_kinds_rdf
import texstage_kinds_sql

for module in (texstage, texstage_kinds_rdf, texstage_kinds_sql):
    assert "site-packages" in Path(module.__file__).parts, module.__file__
# an activity of each of texstage's kinds - the kinds' packages' and texstage's own -, seeds and references in
# the body: the build runs the references with their kinds, in a pool's process, as the server will
ACTIVITIES = r"""\documentclass{beamer}
\usepackage{texactivity}
\begin{document}
\begin{frame}[t]{Triples}
  \begin{activity}[id=crowd,kind=triples,fields={Subject,Predicate,Object}]
    \prompt{A triple about Alice?}
  \end{activity}
\end{frame}
\begin{frame}[t,fragile]{SQL}
  \begin{activity}[id=names-sql,kind=sql-query]
    \prompt{The names?}
    \seed{CREATE TABLE person (name TEXT); INSERT INTO person VALUES ('Alice');}
    \reference{SELECT name FROM person}
  \end{activity}
\end{frame}
\begin{frame}[t,fragile]{SPARQL}
  \begin{activity}[id=names-sparql,kind=sparql-query]
    \prompt{The names?}
    \seed{@prefix : <http://example.org/> . :alice :name "Alice" .}
    \reference{SELECT ?n WHERE { ?p :name ?n }}
  \end{activity}
\end{frame}
\begin{frame}[t,fragile]{Turtle}
  \begin{activity}[id=knows,kind=turtle-graph]
    \prompt{Alice knows Bob?}
    \seed{@prefix ex: <http://example.org/> .}
    \reference{ex:alice ex:knows ex:bob .}
  \end{activity}
\end{frame}
\begin{frame}[t,fragile]{Choice}
  \begin{activity}[id=colour,kind=choice,options={Red,Green,Blue}]
    \prompt{The colour of grass?}
    \reference{Green}
  \end{activity}
\end{frame}
\begin{frame}[t,fragile]{Number}
  \begin{activity}[id=answer,kind=number]
    \prompt{Six times seven?}
    \reference{42}
  \end{activity}
\end{frame}
\begin{frame}[t,fragile]{Text}
  \begin{activity}[id=language,kind=text]
    \prompt{The query language of RDF?}
    \reference{SPARQL}
  \end{activity}
\end{frame}
\end{document}
"""
KINDS = {"triples": "texstage-kinds-rdf", "sparql-query": "texstage-kinds-rdf", "turtle-graph": "texstage-kinds-rdf",
         "sql-query": "texstage-kinds-sql", "choice": "texstage", "number": "texstage", "text": "texstage"}
with latex_resources() as resources:
    assert "site-packages" in resources.parts
    assert {p.name for p in resources.glob("*.sty")} == set(LATEX_FILES)
with tempfile.TemporaryDirectory(prefix="texstage-wheel-") as tmp:
    scratch = Path(tmp)
    source = scratch / "demo.tex"
    source.write_text(r"\documentclass{beamer}\usepackage{texquiz}\begin{document}\quizjoinframe\begin{quiz}[id=two]{Two plus two?}\choice*{Four}\choice{Five}\end{quiz}\end{document}")
    console = Path(sys.executable).with_name("texstage.exe" if os.name == "nt" else "texstage")
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "TEXINPUTS")}
    result = subprocess.run([str(console), "build", str(source), "--data", str(scratch / "data"),
                             "--key", "synthetic-test-key", "--no-check"], cwd=scratch, env=env,
                            capture_output=True, text=True, errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    bundle, = (scratch / "texquiz-out").glob("*.bundle")
    assert json.loads((bundle / "deck.json").read_text())["deck"] == "demo"
    assert list((scratch / "texquiz-out").glob("*.pptx"))
    plain = scratch / "plain.tex"
    plain.write_text(r"\documentclass{beamer}\usepackage{pgfpages}\begin{document}\begin{frame}{Plain}Hello.\note{Installed converter.}\end{frame}\end{document}")
    result = subprocess.run([str(console), "pptx", str(plain), "--target-height", "240"],
                            cwd=scratch, env=env, capture_output=True, text=True, errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    from pptx import Presentation
    from texstage.api import convert_beamer_to_pptx
    assert callable(convert_beamer_to_pptx)
    converted = Presentation(plain.with_suffix(".pptx"))
    assert len(converted.slides) == 1
    assert converted.slides[0].notes_slide.notes_text_frame.text == "Installed converter."
    from texstage.api import compile_latex, LatexResult
    result = compile_latex(plain, engine="latexmk", output_dir=scratch / "plain-pdf")
    assert isinstance(result, LatexResult) and result.returncode == 0, result.stdout + result.stderr
    assert result.pdf.is_file() and result.aux.is_file() and result.log_text
    # the kinds, from their wheels: their kit on the fixtures they carry, a deck of their activities built
    # and served by a server of the core's type
    result = subprocess.run([str(console), "kinds", "check"], cwd=scratch, env=env, capture_output=True,
                            text=True, errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    live = scratch / "live"
    live.mkdir()
    (live / "activities.tex").write_text(ACTIVITIES, encoding="utf-8")
    result = subprocess.run([str(console), "build", "activities.tex", "--data", str(scratch / "data"),
                             "--key", "synthetic-test-key", "--no-check"], cwd=live, env=env,
                            capture_output=True, text=True, errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    bundle, = (live / "texquiz-out").glob("*.bundle")
    kinds = json.loads((bundle / "deck.json").read_text())["kinds"]
    assert {k: v["package"] for k, v in kinds.items()} == KINDS, kinds
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("check_kinds_served.py")),
                             "--bundles", str(live / "texquiz-out"), "--every"], env=env, capture_output=True,
                            text=True, errors="replace")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"checked a phone's entry of {len(KINDS)} of their {len(KINDS)} activities" in result.stdout, result.stdout
print("PASS: installed console, resources, live deck, PowerPoint conversion, generic compilation API, "
      "and the kinds: their kit, a deck with an activity of each kind built and served")
