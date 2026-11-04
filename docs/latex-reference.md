<!-- Generated; edit the shared reference content, then rebuild. -->
# texstage LaTeX authoring and command reference

Packages, commands, options and developer interfaces

## Contents

- [LaTeX reference: packages and loading](#latex-reference-packages-and-loading)
- [Build modes and notes](#build-modes-and-notes)
- [Quiz environments and body commands](#quiz-environments-and-body-commands)
- [Quiz types and scoring](#quiz-types-and-scoring)
- [Quiz options: identity, timing and layout](#quiz-options-identity-timing-and-layout)
- [Quiz options: answer data](#quiz-options-answer-data)
- [Setup defaults and session frames](#setup-defaults-and-session-frames)
- [Quiz display strings (1/2)](#quiz-display-strings-12)
- [Quiz display strings (2/2)](#quiz-display-strings-22)
- [Quiz theme hooks](#quiz-theme-hooks)
- [Video command and options](#video-command-and-options)
- [Video output and portability](#video-output-and-portability)
- [Activity environment and common options](#activity-environment-and-common-options)
- [Tuple activities: options and example](#tuple-activities-options-and-example)
- [Code activities: engines and data](#code-activities-engines-and-data)
- [SQL activities: permitted statements](#sql-activities-permitted-statements)
- [Code activity example and build checks](#code-activity-example-and-build-checks)
- [Activity labels and documentation helpers](#activity-labels-and-documentation-helpers)
- [Core interfaces for package developers](#core-interfaces-for-package-developers)
- [Core asset and layout helpers](#core-asset-and-layout-helpers)
- [LaTeX examples and common authoring failures](#latex-examples-and-common-authoring-failures)
- [Deck language and live labels](#deck-language-and-live-labels)

## LaTeX reference: packages and loading

Use this section as a lookup after completing the first-session tutorial in the [user manual](manual.md). Install and verify texstage with the [installation guide](installation.md); the CLI makes the packaged styles available to TeX. Authors usually begin with texquiz.sty and the complete small-quiz example earlier in the manual. Load texvideo or texactivity only when the deck uses those features.

This reference covers all four shipped LaTeX packages and their author-facing commands, environments, keys and theme hooks. Beamer, TikZ and other upstream commands retain their own upstream contracts. Core developer interfaces are identified separately. Examples target the current 0.2.1.dev3 candidate.

| Syntax / option | Meaning and default |
| --- | --- |
| `texstage.sty` | Shared mode selection, page records, geometry and phone assets. Loaded automatically by every content package; it does not select a course theme. |
| `texquiz.sty` | Quizzes, quiz/answer frame options, join/leaderboard/podium frames and customizable answer rendering. Requires the core, TikZ and pdftexcmds; QR support is optional. |
| `texvideo.sty` | The video command, static posters and live playback metadata. Requires the core, graphicx and TikZ; qrcode is optional. |
| `texactivity.sty` | Tuple and code activities, prompts, seeds and reference answers. Requires the core and Beamer facilities. |
| `docs/manual-latex/manual.sty` | Documentation layout only: headings, typography, tables and page furniture. Do not load it in a lecture deck. |

```
\documentclass[aspectratio=169]{beamer}
\usepackage{texquiz}
\usepackage{texvideo}     % only needed for video
\usepackage{texactivity}  % only needed for activities
\begin{document}
% Frames and quiz environments go here.
\end{document}
```

The texstage CLI supplies the installed style directory. For plain pdfLaTeX, put the four generic files on the TeX search path or use the repository-relative loading shown in the reference example. Do not mix package copies from different revisions. DBIS themes and course notation belong to lecture-tools.


## Build modes and notes

| Syntax / option | Meaning and default |
| --- | --- |
| `\def\texstagemode{handout}` | Define before documentclass. Quiz and answer frames become neutral placeholders; videos remain posters and activities retain their prompts. |
| `\def\texstagemode{solutions}` | Questions, correct choices and explanations are visible. Activity references are printed. Videos remain posters. |
| `\def\texstagemode{present}` | Live layout and .tqz metadata. The builder makes the browser bundle and PowerPoint exports; compiling a raw PDF does not start a live session. |
| `\def\texquizmode{...}` | Legacy alias accepted when texstagemode is absent. An explicitly defined texstagemode takes precedence. |
| `No explicit mode` | At begin-document, Beamer notes enabled selects solutions; otherwise handout. Use explicit modes when this distinction matters. |
| `\texquiznotes` | Build-owned switch: empty selects extraction-oriented notes on the right; stage selects separate note pages, omits extra phone-asset pages and stabilizes the stage PDF. Let the CLI set it. |

```
texstage pdf examples/reference/reference.tex
texstage pdf --solutions examples/reference/reference.tex
texstage pdf --present examples/reference/reference.tex
texstage build examples/reference/reference.tex
```

The core needs a LaTeX kernel dated 2023-06-01 or newer. Present mode supports pdfLaTeX and has a LuaLaTeX code path; the supplied examples are validated with pdfLaTeX. XeLaTeX is rejected for present mode. Live video codecs, external display placement and Office playback need separate platform rehearsal.


## Quiz environments and body commands

| Syntax / option | Meaning and default |
| --- | --- |
| `\begin{quiz}[keys]{question} ... \end{quiz}` | Between frames, creates its own frame. Inside a frame, that frame must have the quiz option. The question is required; one quiz per frame, no authored overlays in quiz frames. |
| `\quizsetup{keys}` | Sets deck-wide defaults and display strings. Call after loading texquiz and after any theme whose defaults you want to override. |
| `\choice[id=label]{text}` | Adds an incorrect choice. Nonempty text; id defaults to A, B, ... in authored order. Explicit ids use 1-32 ASCII letters/digits/hyphens and must be unique within the quiz. |
| `\choice*[id=label]{text}` | Marks a correct choice. Several starred choices infer multiple choice; explicit type=multiple also permits one starred choice. |
| `\explain{text}` | At most one explanation per quiz. Shown on the built-in reveal/solutions page; with reveal=none, explain on a separate answer frame. |
| `\accept{text}` | One or more accepted answers for type=text. Hyperref converts the authored text to plain Unicode for scoring. Use texorpdfstring for unsupported math/macros. |
| `\step{text}` | One nonempty ordering item, written in the correct order. The displayed order is shuffled. |
| `\note{text}, \label{name}` | Beamer commands accepted in a quiz body; notes and stable slide references remain available. The quiz title is not its id. |

Choice, explanation, acceptance and step commands are local to the quiz body. Do not put arbitrary paragraphs, verbatim or listings directly in that body. Put supporting material in a surrounding fragile,quiz frame and keep the question/reveal layout compact. Explicit choice ids identify authored choices; the public A/B/... labels follow the displayed order after shuffling.


## Quiz types and scoring

| Syntax / option | Meaning and default |
| --- | --- |
| `single` | 2-6 choices, exactly one correct. Inferred when one choice is starred. |
| `multiple` | 2-6 choices, at least one correct. Exact-set scoring by default; partial=true enables partial credit. |
| `truefalse` | answer=true or answer=false; no choice commands. Labels come from true-label and false-label. |
| `poll` | 2-6 unstarred choices. Explicit type=poll; select=single by default or multiple. No correct answer and no points. |
| `numeric` | Decimal answer and optional tolerance; no answer means an unscored estimate. Bounds may produce a slider. |
| `text` | At least one accept command. Scoring normalizes case, accents and whitespace; author meaningful accepted variants rather than relying on literal TeX source. |
| `open` | Unscored free text. display=wordcloud by default, or list; max-chars defaults to 80. |
| `order` | 2-6 step commands in correct order. Exact ordering by default; partial=true credits correctly placed items. |
| `sketch` | Unscored drawing input. No choices, accepted answers, steps or answer key; presenter chooses drawings for display. |

Type inference checks ordering items, accepted text, choices, then a boolean/numeric answer. Polls, open text, sketches and numeric estimates without an answer should declare their type. Poll/open/sketch/estimate questions force points=none; explicitly requesting scoring for them is an error. Scoring is server behavior, not a LaTeX calculation.


## Quiz options: identity, timing and layout

| Syntax / option | Meaning and default |
| --- | --- |
| `id` | Required, unique across the deck: 1-63 characters, starts with a lower-case letter or digit, then lower-case letters/digits/hyphens. |
| `type` | single, multiple, truefalse, poll, numeric, text, open, order or sketch; otherwise inferred when unambiguous. |
| `time` | Integer 5-240 seconds. Inherits quizsetup; initial default 20. |
| `points` | standard, double or none. Inherits quizsetup; initial default standard, except forced-unscored types. |
| `leaderboard` | true/false; bare key means true. Default follows setup and is false for unscored questions unless explicitly set. Automatic result pages do not increment the authored frame number. |
| `shuffle` | true/false; bare key means true. Initially false. Deterministic choice shuffling is shared between slide and phones; ordering questions are always shuffled. |
| `reveal` | slide (default) creates the built-in reveal; none defers it to an answer frame. |
| `title` | Title of a generated quiz frame; initially Quiz. Inside an authored frame, use that frame title. A neutral title is used for handout placeholders. |
| `cols` | 1-6 forces the choice columns. Unset uses measured fitting and the theme maximum (2 in the generic theme). |
| `partial` | Boolean, false by default; bare key means true. Meaningful for multiple choice and ordering; it changes credit, not which answer is fully correct. |

Time, points, leaderboard, shuffle, reveal and title have setup-level counterparts. Per-question values override them. Other question keys listed in the following section are not accepted by quizsetup.


## Quiz options: answer data

| Syntax / option | Meaning and default |
| --- | --- |
| `select` | Only polls: single (default) or multiple. |
| `answer` | true/false for truefalse; a decimal for numeric. Omit for an unscored numeric estimate. |
| `tolerance` | Numeric tolerance, default 0. Must be nonnegative. |
| `min, max` | Optional numeric bounds. min must not exceed max; a scored answer interval must intersect the allowed range. Both bounds select a phone slider. |
| `step` | Positive numeric slider increment, default 1 when a slider is used. At least one value min + k*step must fall in the correct interval. |
| `unit` | Optional numeric unit text, initially empty, e.g. ms. |
| `display` | Only open text: wordcloud (default) or list. |
| `max-chars` | Open-text input limit, default 80; the build validates 1-200. The TeX parser accepts digits before the bundle validation applies the range. |

```
\begin{quiz}[id=latency, type=numeric, answer=2.5,
    tolerance=0.1, min=0, max=5, step=0.1, unit={ms}]{Latency?}
  \explain{The measured latency was 2.5 ms.}
\end{quiz}
\begin{quiz}[id=term, type=text]{Name the language.}
  \accept{SPARQL}
  \accept{\texorpdfstring{\textsc{sparql}}{SPARQL}}
\end{quiz}
```

Use ordinary decimal notation such as -1.5, not exponents or a comma decimal separator. Avoid irrelevant keys: the supported contract is the type-specific one above, even where a parser accepts an unused value.


## Setup defaults and session frames

| Syntax / option | Meaning and default |
| --- | --- |
| `\quizsetup{time=20, points=standard}` | Initial time and scoring defaults; same valid values as quiz options. |
| `leaderboard=true, shuffle=false, reveal=slide` | Initial global behavior. A DBIS theme changes some of these defaults. |
| `title=Quiz, join-url={}` | Default quiz title; no static join address until you supply one. The live server supplies the active address/PIN. |
| `\quizjoinframe[title=..., note={...}]` | Creates a join frame outside any frame. Default title Join the quiz. Static modes show join-text and join-url; live mode displays the active session. |
| `\quizleaderboardframe[title=..., note={...}]` | Explicit standings frame outside any frame. Default title Leaderboard. This is separate from automatically inserted post-question standings. |
| `\quizpodiumframe[title=..., note={...}]` | Final standings outside any frame. Default title Final standings; reaching it finishes the live quiz session. |
| `title, note (frame keys)` | The only keys accepted by these three frame commands. note is optional, may contain paragraphs, and is carried to presenter notes. |
| `\begin{frame}[quiz]` | Hosts an inline quiz. The whole frame is replaced by a neutral placeholder in handout mode. Use fragile,quiz when the supporting material contains listings. |
| `\begin{frame}[answer=quiz-id]` | Reveals that quiz on this frame. With bare answer the frame is hidden in the handout, but has no quiz-id association. |

For delayed answers, give the quiz reveal=none, then write an answer=its-id frame later. Do not put quizjoinframe, quizleaderboardframe or quizpodiumframe inside a frame: each command creates one.


## Quiz display strings (1/2)

These quizsetup keys replace visible static slide text. Values below are the generic English defaults, before a course theme is loaded. They do not configure the language of the phone application.

| Setup key | Initial text |
| --- | --- |
| `join-title` | Join the quiz |
| `join-text` | During the lecture, join with your phone using the PIN shown on this slide. |
| `leaderboard-title` | Leaderboard |
| `podium-title` | Final standings |
| `handout-heading` | Live quiz |
| `handout-text` | This question is asked live in the lecture. |
| `results-text` | The results are shown live in the lecture. |
| `answer-title` | Answer |
| `answer-heading` | Answer |
| `answer-text` | The answer is shown in the lecture. |

```
\quizsetup{title=Question, true-label=Yes, false-label=No}
```

Use braces for values containing commas or paragraphs. Change the setup after loading a theme to retain your override. For the DBIS German strings and its leaderboard defaults, see the separate lecture-tools style reference.


## Quiz display strings (2/2)

These quizsetup keys replace visible static slide text. Values below are the generic English defaults, before a course theme is loaded. They do not configure the language of the phone application.

| Setup key | Initial text |
| --- | --- |
| `true-label` | True |
| `false-label` | False |
| `number-hint` | Enter a number on your phone. |
| `text-hint` | Type your answer on the phone. |
| `multiple-hint` | Several answers can be correct. |
| `poll-hint` | Tick all that apply. |
| `order-hint` | Put the items in the right order on your phone. |
| `sketch-hint` | Draw your answer on your phone. |
| `answer-label` | Answer: |
| `accepted-label` | Accepted answers: |

```
\quizsetup{title=Question, true-label=Yes, false-label=No}
```

Use braces for values containing commas or paragraphs. Change the setup after loading a theme to retain your override. For the DBIS German strings and its leaderboard defaults, see the separate lecture-tools style reference.


## Quiz theme hooks

| Syntax / option | Meaning and default |
| --- | --- |
| `\texquizprompt{text}` | Draws the question within its supplied width. Generic default: large text. |
| `\texquizchoice {label} {shape} {width} {height} {state} {content}` | Draw an answer with exactly the supplied geometry. height may be empty for natural height. Reference point must be the lower-left corner. |
| `\texquizchoicefont` | Answer font, generic default normalsize. Redefine with renewcommand. |
| `\texquizchoiceoverhead` | Width reserved besides answer text, generic default 2.31cm. Must match the actual box padding and live-count reserve. |
| `\texquizmaxcols` | Maximum automatically chosen columns, generic default 2. |
| `\texquizexplanation{text}` | Reveal/solutions explanation; default is a light panel. |
| `\texquizhint{text}` | Input hint; generic default small text in texquiz-hint color. |
| `\texquizbadge{n}` | Inline shape badge, n=1..6: triangle, diamond, circle, square, star, hexagon. |

The choice label is A, B, ... or an ordering rank. shape is 1-6; state is plain, correct or wrong. Correct and wrong choices must look identical in state plain. Keep geometry consistent because the server overlays counts and live content on the recorded rectangles.

Colors are texquiz-1 through texquiz-6, texquiz-correct, texquiz-panel and texquiz-hint. They style the PDF/deck rendering; a TeX color change alone does not restyle the phone UI. Private macros containing @ or __ are implementation details.

```
\renewcommand{\texquizprompt}[1]{{\Large\bfseries #1\par}}
```


## Video command and options

Load texvideo, then place the command inside a Beamer frame. Every video requires a local JPEG/PNG poster. Paths are relative to the deck directory. The poster determines the rendered aspect ratio; match it to the video.

| Syntax / option | Meaning and default |
| --- | --- |
| `\video[keys]{source}` | source is a local media file or online address. A local file must exist. The command can be used in overlays and repeated frames. |
| `poster` | Required image. The bundle builder accepts .jpg, .jpeg and .png. |
| `width, height` | Optional graphicx dimensions; with neither, the poster uses its natural dimensions. Supply one dimension to preserve aspect ratio. |
| `id` | Optional; derived from source basename/address when omitted, lower-cased and normalized. Use an explicit stable id for predictable reuse. |
| `start, end` | Optional times in seconds. Omitted means the player default beginning/end. Supply nonnegative values with end after start. Playback interpretation is player-specific. |
| `loop, muted, autoplay` | Booleans, initially false; a bare key means true. autoplay requests playback on entering the slide, subject to browser policies. |
| `url` | Optional online copy for the handout link/QR. If omitted for an online video, its source URL is used; a local video otherwise shows its filename. |

```
\begin{frame}{A short demonstration}
  \video[id=demo-clip, poster=poster.jpg, width=.75\textwidth,
         start=5, end=20, muted]{clip.mp4}
\end{frame}
```

Reusing an id retains the same video and playback state. Its source, poster and playback keys must agree. Repeating the same id twice on one slide is an error. Give separate videos distinct ids.


## Video output and portability

| Syntax / option | Meaning and default |
| --- | --- |
| `Handout / solutions` | Poster plus a play mark and filename or link. A QR code is added for an online link when qrcode.sty is available. The PDF does not embed a playing video. |
| `Browser presentation` | Local media is copied into the bundle. YouTube, Vimeo and supported direct media URLs get live players; an unsupported online URL produces a warning and keeps its poster. |
| `PowerPoint, live and static` | Local media becomes a native movie object. An online video becomes a linked poster. Browser-only playback options are not applied by the current native PowerPoint movie writer. |
| `Local formats` | The builder recognizes .mp4, .m4v, .webm and .mov. MP4 with H.264/AAC is the documented cross-workflow target; actual playback depends on installed/browser codecs. |
| `Network and size` | Online playback needs its provider/network. Local media is duplicated into the bundle and both PPTX files; videos over 100 MiB cause a build warning. |

Compilation checks poster geometry and packaging, not successful playback on every browser or Office version. Rehearse actual media on the presentation device. The documentation example uses a synthetic external URL so it builds without downloading media; it is explicitly a poster/link example, not a playable movie test.

The full command contract is in texvideo.sty and src/texstage/build/video.py. Do not interpret a warning-only online URL as proof that an embedded browser player exists for it.


## Activity environment and common options

| Syntax / option | Meaning and default |
| --- | --- |
| `\begin{activity}[keys] ... \end{activity}` | Place inside a Beamer frame; one activity per frame. The environment does not create a frame. A repeated frame may reuse the same unchanged activity id. |
| `\prompt{formatted text}` | Activity instruction. Used in the static box and rendered for phones. One prompt per activity is the supported authoring pattern. |
| `\reference{verbatim text}` | Code activity reference answer; may be repeated for alternative solutions. Use a fragile frame for inline verbatim. File form: reference=answer.rq or an engine-appropriate text file. |
| `\seed{verbatim text}` | Inline code-activity data. Use a fragile frame, or prefer seed=data.ttl / seed=data.sql. If a seed file and inline seed are both supplied, the file takes precedence. |
| `id` | Required, 1-63 lower-case letters/digits/hyphens, starting with a letter or digit. Same id must keep the same definition. |
| `input` | tuple (default) or code. Code input requires engine and seed data. |
| `width, height` | Default linewidth and 0.6 textheight. Size the box to leave room for the frame title and other material. |
| `open` | auto (default) opens when the frame is reached; manual waits for the presenter. |
| `limit` | Contributions per student: 1-50. Default 10 for tuple, 5 for code. |

The exported TexactivityPrompt, TexactivityReference and TexactivitySeed commands are the implementation backing for the local prompt/reference/seed aliases. Use the local names inside activity. Arbitrary body text is not a substitute for prompt.


## Tuple activities: options and example

| Syntax / option | Meaning and default |
| --- | --- |
| `fields` | Two or three labels. Default Subject, Predicate, Object. First/last fields become nodes; a third, middle field labels the edge. |
| `suggest` | Optional comma-separated suggestions. At most 40 entries, each 1-60 characters, after conversion/unescaping. |
| `min` | Required supporting contributions before a tuple appears on the projector: integer 1-1000, default 1. |
| `review` | Boolean, default false; bare key means true. Enables presenter review. |
| `terms` | exact (default) preserves term identity; loose groups case, accents and spacing. Use exact for RDF-like identifiers. |
| `engine` | Not allowed for tuple input. Code-specific seed, reference and tokens produce build warnings if supplied to a tuple activity. |

```
\begin{frame}{Build a small graph}
  \begin{activity}[id=class-graph, fields={Person, Knows, Person},
      suggest={Alice,Bob,Chris}, min=1, review, height=.5\textheight]
    \prompt{Add one connection between two people.}
  \end{activity}
\end{frame}
```

Handout, solutions and PowerPoint show the static activity prompt. Live interaction is implemented in the texstage browser presenter and phones. The current PowerPoint add-in implements quizzes, not live activities.


## Code activities: engines and data

| Syntax / option | Meaning and default |
| --- | --- |
| `engine=sparql` | Queries a Turtle seed (.ttl). References contain SPARQL queries. |
| `engine=sql` | Read-only queries over tables initialized by SQL statements (.sql), using the bundled SQLite browser engine. References contain SQL queries. See SQL activities: permitted statements below. |
| `engine=turtle` | Participants write Turtle. A .ttl seed supplies base/prefix declarations; seed triples are not copied into the participant graph. References contain Turtle graphs. |
| `seed` | Required for code input, as a file or inline seed. UTF-8 text; a BOM is accepted for files. Maximum encoded seed size is 2 MiB. |
| `reference` | Optional reference file. Its text is appended to any inline references. Each reference is 1-2000 characters. References are private bundle answer data, not public phone seed data. |
| `tokens` | Extra keyboard buttons: up to 40 entries of 1-60 characters. Engine punctuation is added automatically. Escape TeX punctuation in key values, e.g. backslash followed by # or %. |
| `Unused tuple keys` | fields, suggest, min, review and terms have no code-input effect and cause warnings when non-default values are supplied. |

The seed is distributed with the activity and is visible to participants; it must contain synthetic/public teaching data. A code activity can omit references for an exploratory task. Providing a reference is what permits comparison with a model result; it does not make arbitrary code input safe to run outside the supported browser engines.

The builder validates data sizes and engine-specific seed extensions. A plain PDF compile cannot establish that SQL/SPARQL/Turtle semantics or results match the teaching objective.


## SQL activities: permitted statements

An SQL activity is a read-only query exercise. The instructor's seed may contain CREATE TABLE and INSERT statements to prepare the teaching data. After loading that seed, Texstage switches the in-memory SQLite database to read-only mode. Each submission is evaluated in a worker in the presenter's browser. The server stores submissions and receives results; it does not execute students' SQL against its own database or a course database.

Students can type any SQL text, but the evaluator accepts only one query statement: SELECT, VALUES or WITH ... SELECT. It refuses commands that change tables or rows, including CREATE, INSERT, UPDATE, DELETE and DROP TABLE. PRAGMA and ATTACH commands are also refused, as are multiple statements in one submission. The tokens option adds keyboard shortcut buttons; it does not limit what a student can type or grant permission to run a command.

| Submission against the people example | Outcome |
| --- | --- |
| `SELECT name FROM people;` | Runs against the seed data. |
| `WITH p AS (SELECT name FROM people) SELECT * FROM p;` | Runs as one read-only query. |
| `DROP TABLE people;` | Refused; the table remains available for later queries. |
| `SELECT name FROM people; DROP TABLE people;` | Refused; only one statement is allowed. |

Result grouping compares returned values. Column names and row order do not affect the group; repeated rows and column positions do. If an exercise asks for ORDER BY, inspect the result order separately rather than treating a matching group as proof that the ordering is correct.

The current activity engine has no writable exercise mode. To teach table creation or updates, use a separately isolated notebook or database lab. The instructor's seed initialization is distinct from the student submissions above.


## Code activity example and build checks

```
\begin{frame}[fragile]{Query the people table}
  \begin{activity}[id=names, input=code, engine=sql,
      height=.4\textheight, open=manual, tokens={SELECT,FROM,ORDER BY}]
    \prompt{Return all names in alphabetical order.}
    \seed{CREATE TABLE people(name TEXT);
INSERT INTO people VALUES ('Bob'), ('Alice');}
    \reference{SELECT name FROM people ORDER BY name;}
  \end{activity}
\end{frame}
```

For ordinary course files, prefer seed=people.sql and reference=names.sql. This avoids embedding verbatim in a macro argument or a non-fragile frame. All paths are resolved from the deck directory; keep referenced files with the source export.

| Syntax / option | Meaning and default |
| --- | --- |
| `texstage pdf --solutions` | Shows activity references and quiz answers. Verify that long code and explanations fit the frame. |
| `texstage build` | Validates the .tqz records, seed files, media and public/private bundle split. It also checks quiz layout in present and solutions modes. |
| `Browser rehearsal` | Open one activity, submit synthetic input, inspect results and reveal behavior. Compilation alone is not a browser/Office interoperability test. |

Runnable examples and an isolated validation command are provided in [examples/reference/README.md](../examples/reference/README.md). They use dedicated output/data directories and do not load existing courses.


## Activity labels and documentation helpers

The activity label hooks are ordinary macros. Redefine them after loading texactivity to localize static slide text; they do not change the phone UI language.

| Hook | Default and contract |
| --- | --- |
| `\texactivitylabel` | No arguments. Default: Live activity -- on your phones. |
| `\texactivityreferencelabel` | No arguments. Default: Reference. Used above solution reference text. |

```
\renewcommand{\texactivitylabel}{Live task -- use your phone}
```

`docs/manual-latex/manual.sty` only controls this manual: portrait A4 article layout, typography, colors, tables and headers/footers. Its `\manualsection{title}` creates a numbered section without forcing a page break; `\manualsubheading{title}` formats a small heading; `\manualcaption` selects caption text. The document supplies `\manualversion` and `\manualdate`.

This documentation style loads fontenc, lmodern, geometry, xcolor, graphicx, array, longtable, booktabs, fvextra, enumitem, caption, subcaption, placeins, needspace, hyperref, bookmark, microtype and upquote. Compile the documentation with pdfLaTeX; its PDF text mapping uses pdfTeX commands. It is not a lecture-deck package.


## Core interfaces for package developers

These expl3 interfaces are shared by texquiz, texvideo and texactivity. They are documented for maintainers of the current candidate, not a promise of a versioned plugin ABI. Use ExplSyntaxOn when writing extension code; ordinary slide authors should use the content packages.

| Syntax / option | Meaning and default |
| --- | --- |
| `\texstage_if_mode:nTF {mode}{yes}{no}` | Tests the resolved mode; T and F variants are also defined. |
| `\texstage_error:n {message}` | Raises a package error. |
| `\texstage_hex:n {text}` | Encodes record text as hex. V and e variants accept a variable or expanded content. |
| `\texstage_emit:n {record}` | Writes an expanded record immediately in present mode. |
| `\texstage_on_page:n {record}` | Writes at shipout, freezing the current logical page number; position values are expanded later. |
| `\texstage_page_record:nnn {kind}{id}{phase}` | Associates a live item and phase with a page. |
| `\texstage_savepos:, \texstage_lastx:, \texstage_lasty:` | Save the current position and read engine coordinates in scaled points. |
| `\texstage_rect:nnnnn {id}{phase}{key}{width}{height}` | Records a rectangle at the current lower-left reference point. |
| `\texstage_vmark:nnn {id}{phase}{key}` | Records a horizontal boundary across linewidth in vertical mode for a live region. |

Do not emit arbitrary records from a course deck. The Python build registry must understand the content type, its public metadata, private answer data, phone assets and rendering. Shipout and shrink corrections are coordinated by the core.


## Core asset and layout helpers

| Syntax / option | Meaning and default |
| --- | --- |
| `\texstage_check_mark:nn {kind}{id}` | Adds a layout-check log mark outside handout mode. |
| `\texstage_stage_notes:` | Enables stage-note bookkeeping and deterministic pdfTeX metadata; normally called through the build-owned notes switch. |
| `\texstage_asset_box:nn {width}{content}` | Typesets the next extra-page asset into a global box. |
| `\texstage_asset_add:nnn {id}{key}{natural width}` | Associates that box with an item and records its unbroken natural width. Call after asset_box. |
| `\texstage_asset:nnnn {id}{key}{width}{content}` | Combined asset creation and natural-width measurement. |
| `\texstage_ship_assets:` | Ships recorded extra pages after the slides. The normal stage compile suppresses these; authors should not call it themselves. |
| `\texstage_vfill:` | Vertical fill that wins over Beamer top-aligned-frame fill. |
| `\texstage_vbox_set:Nnn {box variable}{width}{content}` | Sets a zero-depth box whose reference point is its lower-left corner. |
| `\texstage_once:n {code}` | Runs code only on the first overlay of the current frame. |
| `\texstage_check_outside_frame:n {command name}` | Errors when a frame-creating command is used inside a frame. |

Names containing @, names beginning __, parser temporaries and global state variables are implementation details. The core also patches Beamer shrink/shipout handling; do not copy those internals into themes. The maintained inventory records source hashes so changes require a documentation review.


## LaTeX examples and common authoring failures

| Syntax / option | Meaning and default |
| --- | --- |
| `Unknown key or invalid id` | Check the correct key namespace: quizsetup, quiz, choice, special frame, video or activity. Use stable ids and avoid underscores in quiz/activity ids. |
| `Text outside a quiz command` | Move material into the surrounding quiz frame, or into the question/choice/explanation argument. |
| `Reference/seed breaks compilation` | Use a fragile frame for inline verbatim, or external UTF-8 data/reference files. |
| `No correct slider value` | Choose bounds and a positive step that actually contain a value in answer +/- tolerance. |
| `Answers appear in a handout` | Check the selected build mode and whether authored answer frames carry the answer option. |
| `Static activity in PowerPoint` | Expected for this candidate. Use the browser presenter for live activities. |
| `Overfull or excessive shrink` | Shorten the content, reduce material on the frame, or select appropriate columns/box sizes. Run the checked build rather than hiding the warning. |
| `Theme overlay is misaligned` | Keep answer-box width/height and lower-left reference point consistent with the hook contract. |

The compiled reference example covers every quiz type, delayed answers, explicit session frames, video poster packaging and tuple/code activity records. Coverage is an inventory of the documented project interfaces; it does not claim to document all commands provided by LaTeX, Beamer, TikZ or other dependencies.

The [reference inventory](latex-reference-inventory.json) and [example build instructions](../examples/reference/README.md) accompany this chapter. Existing courses and pinned styles do not need to change to read or build these isolated examples.


## Deck language and live labels

Texstage records the active Babel or Polyglossia language when LaTeX builds a deck. German variants such as ngerman select German labels in the presenter and projector live views; English and unsupported languages use English. The phone uses its browser language independently of the deck. Rebuild an existing bundle to capture its deck language.

```
\documentclass{beamer}
\usepackage[ngerman]{babel}
\usepackage{texquiz}
```

In a DBIS course, keep the language in the course dbis-style.sty setting. lecture-tools supplies the German activity heading and reference label. Private presenter activity controls remain English. Older bundles and TQZ records without a language field remain supported.
