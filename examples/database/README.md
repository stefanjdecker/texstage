# Database activity lab

**A library, two data models** is a runnable English Beamer deck about a small
campus library. It contains 31 logical slides, ten quizzes covering all nine quiz
types, and twelve activities: five SQL, three SPARQL, two Turtle and two shared
graphs. All data is fictional and supplied locally.

The [master source](database.tex) includes one slide or quiz per file in
[slides/](slides/). The [coverage map](COVERAGE.md) identifies every example.
[Teaching notes](TEACHING.md) explain expected results and common misconceptions;
the same guidance appears in the private presenter notes. The
[dataset description](data/README.md) records the modeling assumptions.

The transaction-schedule slide is a **static discussion preview**. Its interactive
plugin remains planned. The working examples use Texstage's built-in engines and
quiz types; no external plugin package or lecture-tools setup is required.

## Install and present

Follow the repository's [installation guide](../../docs/installation.md). You
need the matching Texstage environment and a TeX installation with pdfLaTeX,
Beamer, English Babel and booktabs. Texstage supplies its own style files.

From the repository root, in that environment:

    texstage present examples/database/database.tex --deck database-activities --port 8767 --data examples/database/texquiz-out/session-data --no-tunnel

Use a free port. The dedicated data directory keeps these example sessions
separate from lecture sessions. The presenter supplies the join address and PIN.
On this computer a participant can use http://127.0.0.1:8767/play; phones use the
reachable LAN address shown by Texstage. Open the Projector window for the audience.

The full lab takes about 45–60 minutes. A shorter route uses source files
00–04, 09–11, 18, 21, 24 and 29–30: introduce the data, join, discuss a key,
try SQL joins/counts, then SPARQL and Turtle, and finish with the transaction preview.
Use the presenter's overview to jump between examples.

For code activities, open participation, allow roughly two minutes for an attempt,
compare result groups, close participation and reveal the reference. The query
activities have no quiz timer. The quizzes have generous per-question timers and
award no points; correctness feedback is still available for questions with keys.

Use two independent browser profiles or devices to demonstrate the two-person
agreement threshold in the classification graph. For solo rehearsal, lower its
Minimum control to one. In the three-field graph, use the Activities panel to
approve each reviewed node and relation label before its edges appear on the projector.

## Build files for teaching

    texstage build examples/database/database.tex --deck database-activities --server http://127.0.0.1:8767
    texstage pdf --handout examples/database/database.tex
    texstage pdf --solutions examples/database/database.tex

Outputs go to examples/database/texquiz-out/:

| Output | Purpose |
| --- | --- |
| database.bundle/ and database.bundle.zip | Browser presentation and uploadable bundle |
| database-static.pptx | Static slide export |
| database.pptx | PowerPoint export with supported live quiz add-ins |
| database-handout.pdf | Student handout, created by the PDF command |
| database-solutions.pdf | Worked reference edition, created by the PDF command |

SQL, SPARQL, Turtle and shared graphs run live in Texstage's browser presenter.
Their PowerPoint/PDF exports show static activity prompts. In Texstage's handout
mode, quiz frames become neutral placeholders and activity prompts remain.
Use the solutions edition to inspect all questions, quiz answers and reference code.
Open-ended modeling and explanation tasks use the rubrics in TEACHING.md.
Generated output and session data are ignored by Git.

## Edit or add an example

1. Edit its numbered file in slides/, keeping the activity or quiz ID stable.
2. Keep seeds in data/ and executable references in answers/. Paths are relative
   to database.tex, even though each slide lives in a subfolder.
3. For a new slide, add an input line to database.tex and a coverage-map entry.
4. Rebuild and review both the handout and solution edition. Speaker notes should
   identify the expected reasoning and at least one plausible misconception.

Each SQL activity loads the fixed seed independently. Shared-graph contributions
do not feed later queries. Turtle inputs form their own result graph, with the
seed supplying prefixes. A reference match compares results on this dataset:
it is not a proof that two queries are equivalent for all databases.

## Check the executable examples

With Node 24, from the repository root:

    node examples/database/verify.mjs

The checker uses Texstage's actual sql.js and Oxigraph browser engines and
hand-derived expected outputs. It checks all ten references, alternate valid
queries, duplicate rows, NULL mistakes, resource-versus-literal mistakes, Turtle
shorthand, blank input and refused SQL mutations. Extra data adds a member with
only closed loans and a second member named Ada to expose incorrect grouping
and filtering. It validates this finite example set, not general equivalence.

For an installed package instead of a source checkout, TEXSTAGE_WEB may point to
that installation's texstage/web directory. No network data source is used.
