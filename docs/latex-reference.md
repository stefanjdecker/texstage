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
- [Choice, number and text activities](#choice-number-and-text-activities)
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

This reference covers all four shipped LaTeX packages and their author-facing commands, environments, keys and theme hooks. Beamer, TikZ and other upstream commands retain their own upstream contracts. Core developer interfaces are identified separately. Examples target the current 1.0.0 release.

| Syntax / option | Meaning and default |
| --- | --- |
| `texstage.sty` | Shared mode selection, page records, geometry and phone assets. Loaded automatically by every content package; it does not select a course theme. |
| `texquiz.sty` | Quizzes, quiz/answer frame options, join/leaderboard/podium frames and customizable answer rendering. Requires the core, TikZ and pdftexcmds; QR support is optional. |
| `texvideo.sty` | The video command, static posters and live playback metadata. Requires the core, graphicx and TikZ; qrcode is optional. |
| `texactivity.sty` | Tuple, choice, number, text and code activities, prompts, seeds and reference answers. Requires the core, Beamer facilities and TikZ. |
| `docs/manual-latex/manual.sty` | Documentation layout only: headings, typography, tables and page furniture. Do not load it in a lecture deck; [manual-latex/README.md](manual-latex/README.md) describes it. |

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
| `\def\texstagemode{handout}` | For a plain pdflatex run, defined before the deck is read: `pdflatex "\def\texstagemode{handout}\input{deck.tex}"`. Quiz and answer frames become neutral placeholders; videos remain posters and activities retain their prompts. |
| `\def\texstagemode{solutions}` | Questions, correct choices and explanations are visible. Activity references are printed. Videos remain posters. |
| `\def\texstagemode{present}` | Live layout and .tqz metadata. The builder makes the browser bundle and PowerPoint exports; compiling a raw PDF does not start a live session. |
| `\def\texquizmode{...}` | The switch texstage's own commands set: `texstage pdf` and `texstage build` define it in front of the deck. A `\texstagemode` wins over it, so a deck that texstage builds must set neither: its own mode would override the command's, and `texstage build` stops. |
| `No explicit mode` | At begin-document, Beamer notes enabled selects solutions; otherwise handout. Use explicit modes when this distinction matters. |
| `\texquiznotes` | Build-owned switch: empty selects extraction-oriented notes on the right; stage selects separate note pages, omits extra phone-asset pages and stabilizes the stage PDF. Let the CLI set it. |

```
texstage pdf examples/reference/reference.tex
texstage pdf --solutions examples/reference/reference.tex
texstage pdf --present examples/reference/reference.tex
texstage build examples/reference/reference.tex
```

The core needs a LaTeX kernel dated 2023-06-01 or newer. `texstage pdf` and `texstage build` always run pdfLaTeX, so a deck must compile with it; the packages' LuaLaTeX code path is untested, and no texstage command uses it. XeLaTeX is rejected for present mode. Live video codecs, external display placement and Office playback need separate platform rehearsal.


## Quiz environments and body commands

| Syntax / option | Meaning and default |
| --- | --- |
| `\begin{quiz}[keys]{question} ... \end{quiz}` | Between frames, creates its own frame. Inside a frame, that frame must have the quiz option. The question is required; one quiz per frame, no authored overlays in quiz frames. |
| `\quizsetup{keys}` | Sets deck-wide defaults and display strings. Call after loading texquiz and after any theme whose defaults you want to override. |
| `\choice[id=label]{text}` | Adds an incorrect choice. Nonempty text; id defaults to A, B, ... in authored order. Explicit ids use 1-32 ASCII letters/digits/hyphens and must be unique within the quiz. |
| `\choice*[id=label]{text}` | Marks a correct choice. Several starred choices infer multiple choice; explicit type=multiple also permits one starred choice. |
| `\explain{text}` | At most one explanation per quiz, shown on the built-in reveal and in the solutions PDF. With reveal=none, give it on the answer frame: a quiz inside your own `[quiz]` frame then prints its `\explain` nowhere, and one with a frame of its own still prints it in the solutions PDF. |
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
| `time` | Integer 5-240 seconds. Inherits quizsetup; initial default 20. An activity's `time` is another key: 1-14400 seconds ([Activity environment and common options](#activity-environment-and-common-options)). |
| `points` | standard, double or none. Inherits quizsetup; initial default standard, except forced-unscored types. |
| `leaderboard` | true/false; bare key means true. Default follows setup. Only a scored quiz gets one: on a poll, open, sketch or `points=none` question, or a numeric one without an answer, the key does nothing. Automatic result pages do not increment the authored frame number. |
| `shuffle` | true/false; bare key means true. Initially false. Deterministic choice shuffling is shared between slide and phones; ordering questions are always shuffled. |
| `reveal` | slide (default) creates the built-in reveal; none defers it to an answer frame. |
| `title` | Title of a generated quiz frame; initially Quiz. Inside an authored frame, use that frame title. A neutral title is used for handout placeholders. |
| `cols` | 1-6 forces the choice columns. Unset uses measured fitting and the theme maximum (2 in the generic theme). |
| `partial` | Boolean, false by default; bare key means true. Meaningful for multiple choice and ordering; it changes credit, not which answer is fully correct. |

Time, points, leaderboard, shuffle, reveal and title have setup-level counterparts. Per-question values override them. Other question keys listed in the following section are not accepted by quizsetup.


## Quiz options: answer data

| Syntax / option | Meaning and default |
| --- | --- |
| `select` | Only polls: single (default) or multiple. A choice activity's `select` is one or many instead ([Choice, number and text activities](#choice-number-and-text-activities)). |
| `answer` | true/false for truefalse; a decimal for numeric. Omit for an unscored numeric estimate. |
| `tolerance` | Numeric tolerance, default 0. Must be nonnegative. |
| `min, max` | Optional numeric bounds. min must not exceed max; a scored answer interval must intersect the allowed range. Both bounds select a phone slider. |
| `step` | Positive numeric slider increment, default 1 when a slider is used. At least one value min + k*step must fall in the correct interval. |
| `unit` | Optional numeric unit text, initially empty, e.g. ms. |
| `display` | Only open text: wordcloud (default) or list. |
| `max-chars` | Open-text input limit, 1-200 characters, default 80; any other value stops the compile. |

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
| `title=Quiz, join-url={}` | Default quiz title; no static join address until you supply one. The live server supplies the active address/PIN. `join-url` is printed on the join frame of the handout and solutions PDFs; the live join slide shows the server's own address. |
| `\quizjoinframe[title=..., note={...}]` | Creates a join frame outside any frame. Default title Join the quiz. Static modes show join-text and join-url; live mode displays the active session. |
| `\quizleaderboardframe[title=..., note={...}]` | Explicit standings frame outside any frame. Default title Leaderboard (`leaderboard-title`). Right after a quiz's reveal or answer frame it takes the place of the leaderboard the builder would add there. |
| `\quizpodiumframe[title=..., note={...}]` | Final standings outside any frame. Default title Final standings; reaching it finishes the live quiz session. |
| `title, note (frame keys)` | The only keys accepted by these three frame commands. note is optional, may contain paragraphs, and is carried to presenter notes. |
| `\begin{frame}[quiz]` | Hosts an inline quiz. The whole frame is replaced by a neutral placeholder in handout mode. Use fragile,quiz when the supporting material contains listings. |
| `\begin{frame}[answer=quiz-id]` | Reveals that quiz on this frame. In the handout `answer` and `answer=quiz-id` alike become a placeholder page ("The answer is shown in the lecture."); a bare `answer` names no quiz. |

For delayed answers, give the quiz reveal=none, then write an answer=its-id frame later. Do not put quizjoinframe, quizleaderboardframe or quizpodiumframe inside a frame: each command creates one.


## Quiz display strings (1/2)

These quizsetup keys replace visible static slide text. Without them, a text follows the deck's language (see [Deck language and live labels](#deck-language-and-live-labels)): the English or German default below. A value given here wins in every language. The phone application and the presenter windows follow the deck's language by themselves.

| Setup key | English | German |
| --- | --- | --- |
| `join-title` | Join the quiz | Mitmachen |
| `join-text` | During the lecture, join with your phone using the PIN shown on this slide. | In der Vorlesung: mit dem Handy und der PIN auf dieser Folie teilnehmen. |
| `leaderboard-title` | Leaderboard | Bestenliste |
| `podium-title` | Final standings | Endstand |
| `handout-heading` | Live quiz | Live-Quiz |
| `handout-text` | This question is asked live in the lecture. | Diese Frage wird live in der Vorlesung gestellt. |
| `results-text` | The results are shown live in the lecture. | Die Ergebnisse werden live in der Vorlesung gezeigt. |
| `answer-title` | Answer | Antwort |
| `answer-heading` | Answer | Antwort |
| `answer-text` | The answer is shown in the lecture. | Die Antwort gibt es in der Vorlesung. |

```
\quizsetup{title=Question, true-label=Yes, false-label=No}
```

Use braces for values containing commas or paragraphs. Change the setup after loading a theme to retain your override. For the DBIS German strings and its leaderboard defaults, see the separate lecture-tools style reference.


## Quiz display strings (2/2)

The remaining texts. How the setup sets them, and what wins over the deck's language, is on [Quiz display strings (1/2)](#quiz-display-strings-12).

| Setup key | English | German |
| --- | --- | --- |
| `true-label` | True | Wahr |
| `false-label` | False | Falsch |
| `number-hint` | Enter a number on your phone. | Geben Sie auf Ihrem Handy eine Zahl ein. |
| `text-hint` | Type your answer on your phone. | Tippen Sie Ihre Antwort auf dem Handy ein. |
| `multiple-hint` | Several answers can be correct. | Mehrere Antworten können richtig sein. |
| `poll-hint` | Tick all that apply. | Kreuzen Sie alles Zutreffende an. |
| `order-hint` | Put the items in the right order on your phone. | Bringen Sie die Elemente auf dem Handy in die richtige Reihenfolge. |
| `sketch-hint` | Draw your answer on your phone. | Zeichnen Sie Ihre Antwort auf dem Handy. |
| `answer-label` | Answer: | Antwort: |
| `accepted-label` | Accepted answers: | Akzeptierte Antworten: |


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
| `\reference{verbatim text}` | A reference answer, read verbatim: a code activity's query or graph, a choice's option, a number or a short answer. May be repeated for alternative solutions. Use a fragile frame for inline verbatim. Code activities also take a file, reference=answer.rq or an engine-appropriate text file; choice, number and text take their references only in the body. |
| `\seed{verbatim text}` | Inline code-activity data. Use a fragile frame, or prefer seed=data.ttl / seed=data.sql. If a seed file and inline seed are both supplied, the file takes precedence. |
| `\reveal<n>` | Inside activity, at most once, n a slide's number: the frame's slides from the n-th on - Beamer overlays - reveal the activity, and the slides before it open it. Without it, the frame opens the activity and leaving it closes it; the build warns of an activity that no slide opens. |
| `id` | Required, 1-63 lower-case letters/digits/hyphens, starting with a letter or digit. Same id must keep the same definition. |
| `kind` | The activity's kind, as an installed package of kinds names it: choice, number and text (texstage's own; [Choice, number and text activities](#choice-number-and-text-activities)), triples, sparql-query and turtle-graph (texstage-kinds-rdf), sql-query (texstage-kinds-sql). `texstage kinds` lists the installed ones; [installation.md](installation.md) installs the kinds' packages. texstage build asks the kind, which checks its own keys - every key texactivity does not know is the kind's, and the build warns of one the kind does not take. |
| `input` | tuple (default) or code: the activity's kind as decks named it before kinds - input=tuple is kind=triples, input=code with engine=sql, sparql or turtle is kind=sql-query, sparql-query or turtle-graph. Code input requires engine and seed data. |
| `width, height` | Default linewidth and 0.6 textheight. Size the box to leave room for the frame title and other material. |
| `open` | auto (default) opens when the frame is reached; manual waits for the presenter. |
| `limit` | Contributions per student: 1-50. Default 10 for tuple and choice, 5 for code, number and text. |
| `counts=latest|all` | Which of a student's entries count: `latest` replaces the earlier ones, `all` counts each. Default: `all` for triples, `latest` for every other kind. |
| `gap=<seconds>` | How long a student waits between two entries, 0-3600 seconds, decimals allowed. Default: 1 for choice; 2 for triples, number and text; 5 for queries and graphs. |
| `time=<seconds>` | The activity's time when its slide opens it, 1-14400 seconds; at zero it closes. Default: no time - it stays open until it is closed. |
| `budget=<ms>` | A check's CPU time, from 1 ms up to the kind's maximum (1000 ms for every kind texstage ships). Default: that maximum. |
| `feedback=none|status|verdict|full` | What a phone learns before the reveal: `none` that its entry arrived; `status` also whether its check ran, with its message; `verdict` also right or wrong; `full` also how it compares with the reference. Default: `status`. |
| `projector=live|count|hidden` | What the class sees while the activity runs: the entries as they come, only their number, or none of them. Default: `live`. |
| `solution=show|mark` | What the reveal shows: `show` puts the references on the projector too, `mark` only marks the reference's group. Default: `show`. |

The exported TexactivityPrompt, TexactivityReference, TexactivitySeed and TexactivityReveal commands are the implementation backing for the local prompt/reference/seed/reveal aliases. Use the local names inside activity. Arbitrary body text is not a substitute for prompt. The build checks `counts`, `gap`, `time`, `budget`, `feedback`, `projector` and `solution`; `texstage serve` and `present` use them, and a server started with `--activities f1` leaves them aside.


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

A tuple activity is of the kind triples (texstage-kinds-rdf): kind=triples and input=tuple, the default, are the same. Handout, solutions and PowerPoint show the static activity prompt - and a choice's options. Live interaction is implemented in the texstage browser presenter and phones. The current PowerPoint add-in implements quizzes, not live activities.


## Choice, number and text activities

Three kinds come with texstage itself and need no extra package: kind=choice, kind=number and kind=text. Phones choose among options, send a number or a short answer; the projector shows a tally, a histogram or the grouped answers, and the reveal marks what is right. These kinds run only on the activity framework's core, a server's default activity type; a server started with `--activities f1` skips such a deck and says why.

| Syntax / option | Meaning and default |
| --- | --- |
| `kind=choice` | One option, or several with select=many, of those listed in options. The projector counts each option in the deck's order, an option nobody chose included - with select=many, the students who chose it, alone or with others. A student may change their mind: the latest choice counts. |
| `options` | For choice, required: 2-26 comma-separated options, each 1-100 characters and given once. They become the phones' buttons, a formula typeset, each with its shape in its colour; from seven options on each also carries its letter, A to Z, inside its shape - on the phones, the projector's bars and the slide. Options and references are read as LaTeX sets them: an accent is its letter (`Espa\~na` is España), a tie a space (`New~York`). As in every key, `\&` or `\^` stands for the character itself - TeX reads `^^` as a character code -, so `\^o` gives ^o: type ô itself. |
| `select` | For choice: one (default) or many (a quiz poll's `select` is single or multiple). With many, a phone marks several options and sends them together. |
| `kind=number` | A number, positive or negative. Phones accept a decimal comma (2,5) as well as a point, and digits grouped by three (1 000); one separator before three digits alone (3,141) is read as the phone's own language writes numbers - 3.141 on a German phone, 3141 on an English one. The projector draws a histogram: a bar per number while there are at most twelve, else bars of equal width - numbers far from the rest (beyond three times the spread of the middle half) gather in a bar at either end, so that a joke answer does not squeeze the others into one bar. |
| `tolerance` | For number: how far an answer may lie from a reference and still be right. 0 (default) or more, in ASCII digits with at most one point, e.g. 0.5; `tolerance=0,5` is refused, as the comma ends the key. Without a reference nothing is judged, and the build warns of a tolerance given without one. |
| `kind=text` | A short answer of at most 100 characters, compared as quiz text answers are: case, accents and spacing do not matter, and what is not seen (a zero-width space) is no part of it. The projector groups the answers by that form. |
| `\reference{answer}` | In the body; a reference= key is refused. A choice's reference names one of its options, read as they are, and with select=many the references together are the right choice. A number's reference is a number, and each text reference is an accepted answer. Repeat it for alternatives; without one, nothing is judged. |

```
\begin{frame}[fragile]{What has to stay cool?}
  \begin{activity}[id=cool-bag, kind=choice, select=many,
      options={Yoghurt, Bread, Butter, Apples}, height=.5\textheight]
    \prompt{What goes into the cool bag?}
    \reference{Yoghurt}
    \reference{Butter}
  \end{activity}
\end{frame}
\begin{frame}[fragile]{How long is our walk?}
  \begin{activity}[id=walk, kind=number, tolerance=0.5, height=.5\textheight]
    \prompt{450 m at about 60 m per minute: how many minutes?}
    \reference{7.5}
  \end{activity}
\end{frame}
\begin{frame}[fragile]{What do we take home?}
  \begin{activity}[id=take-home, kind=text, height=.5\textheight]
    \prompt{One word: what do we take home with us?}
    \reference{rubbish}
    \reference{litter}
  \end{activity}
\end{frame}
```

The build checks the references as the server checks them: a choice's reference that is none of its options, or a number's reference that is no number, stops the build. Handout and PowerPoint show the prompt and a choice's options - each with its shape in its colour, as the phones show them, so that the prompt need not repeat them; the solutions add the references. The [feature showcase](../examples/showcase/README.md) and the [live-activity demo deck](../examples/demo/README.md) present one activity of each kind.


## Code activities: engines and data

| Syntax / option | Meaning and default |
| --- | --- |
| `kind=sparql-query` (`engine=sparql`) | Queries a Turtle seed (.ttl). References contain SPARQL queries. In texstage-kinds-rdf. A syntax error comes in Oxigraph's own words: the line and column it names are right, but what it says it expected there is sometimes misleading - look at that place in the query (with --activities f1 as well). |
| `kind=sql-query` (`engine=sql`) | Read-only queries over tables initialized by SQL statements (.sql), run by SQLite - Python's on the server, or with --activities f1 sql.js in the presenter's browser. References contain SQL queries. In texstage-kinds-sql. See SQL activities: permitted statements below. |
| `kind=turtle-graph` (`engine=turtle`) | Participants write Turtle. A .ttl seed supplies base/prefix declarations; seed triples are not copied into the participant graph. References contain Turtle graphs. In texstage-kinds-rdf. |
| `seed` | Required for code input, as a file or inline seed. UTF-8 text; a BOM is accepted for files. Maximum encoded seed size is 2 MiB. |
| `reference` | Optional reference file. Its text is appended to any inline references. Each reference is 1-2000 characters. References are private bundle answer data, not public phone seed data. |
| `tokens` | Extra keyboard buttons: up to 40 entries of 1-60 characters. Engine punctuation is added automatically. Escape TeX punctuation in key values, e.g. backslash followed by # or %. |
| `Unused tuple keys` | fields, suggest, min, review and terms have no effect on a code activity. Any value of them warns, except the fields preset, an empty `suggest` and `review=false`. |

The seed is distributed with the activity and is visible to participants; it must contain synthetic/public teaching data. A code activity can omit references for an exploratory task. Providing a reference is what permits comparison with a model result. Students' code runs only in the checks texstage brings - in the server's worker processes or, with `--activities f1`, in the presenter's browser, in memory and within a time budget -, never against a course database.

The builder validates data sizes and engine-specific seed extensions. A plain PDF compile cannot establish that SQL/SPARQL/Turtle semantics or results match the teaching objective.


## SQL activities: permitted statements

An SQL activity is a read-only query exercise. The instructor's seed may contain CREATE TABLE and INSERT statements to prepare the teaching data. After loading that seed, texstage switches the in-memory SQLite database to read-only mode. Where a submission runs depends on how the server is started: by default - the activity framework's core - in one of the server's worker processes, by Python's SQLite, against an in-memory copy of the seed and within a budget of CPU time; with --activities f1 in a worker of the presenter's browser (sql.js), which sends the server its result, or, with --checks server as well, in the server's worker processes. Either way no student's SQL runs against the server's own database or a course database.

Students can type any SQL text, but the check accepts only one query statement: SELECT, VALUES or WITH ... SELECT. It refuses commands that change tables or rows, including CREATE, INSERT, UPDATE, DELETE and DROP TABLE. PRAGMA and ATTACH commands are also refused, as are multiple statements in one submission. The tokens option adds keyboard shortcut buttons; it does not limit what a student can type or grant permission to run a command.

| Submission against the people example | Outcome |
| --- | --- |
| `SELECT name FROM people;` | Runs against the seed data. |
| `WITH p AS (SELECT name FROM people) SELECT * FROM p;` | Runs as one read-only query. |
| `DROP TABLE people;` | Refused; the table remains available for later queries. |
| `SELECT name FROM people; DROP TABLE people;` | Refused; only one statement is allowed. |

Result grouping compares returned values. Column names and row order do not affect the group; repeated rows and column positions do. If an exercise asks for ORDER BY, inspect the result order separately rather than treating a matching group as proof that the ordering is correct.

The SQL check has no writable exercise mode. To teach table creation or updates, use a separately isolated notebook or database lab. The instructor's seed initialization is distinct from the student submissions above.


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
| `texstage build` | Validates the .tqz records, seed files, media and public/private bundle split. It also checks quiz layout in present and solutions modes. Each activity's kind builds it: the kinds must be installed where decks are built. Every reference runs as the server runs it - a reference that does not run, or a seed that does not load, stops the build. |
| `Browser rehearsal` | Open one activity, submit synthetic input, inspect results and reveal behavior. Compilation alone is not a browser/Office interoperability test. |

Runnable examples and an isolated validation command are provided in [examples/reference/README.md](../examples/reference/README.md). They use dedicated output/data directories and do not load existing courses.


## Activity labels and documentation helpers

The activity label hooks are ordinary macros. By default they give the text of the deck's language, English or German; redefine them after loading texactivity for other wording. The phone UI follows the deck's language by itself.

| Hook | Default and contract |
| --- | --- |
| `\texactivitylabel` | No arguments. Default: Live activity -- on your phones (German: Live-Aktivität -- auf Ihren Handys). |
| `\texactivityreferencelabel` | No arguments. Default: Reference (German: Referenz). Used above solution reference text. |

```
\renewcommand{\texactivitylabel}{Live task -- use your phone}
```


## Core interfaces for package developers

These expl3 interfaces are shared by texquiz, texvideo and texactivity. They are documented for maintainers of the current release, not a promise of a versioned plugin ABI. Use ExplSyntaxOn when writing extension code; ordinary slide authors should use the content packages.

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
| `\texstage_texts:nnn {package}{language}{key = text, ...}` | Gives a package's slide texts in a language (en, de), in the preamble. A key a language lacks falls back to English. |
| `\texstage_text:nn {package}{key}` | Expands to the text in the deck's language: Babel's main language at \begin{document}, de for German variants, else en. The text itself is not expanded. |

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
| `Unknown key or invalid id` | Check the correct key namespace: quizsetup, quiz, choice, special frame, video or activity. Use stable ids and avoid underscores in quiz/activity ids. An unknown activity key is no error: it goes to the activity's kind, and only `texstage build` warns (`<key> - not for <kind>`). |
| `a quiz and a video (or activity) on one slide` | The build stops: in PowerPoint the quiz's add-in covers the whole slide. Give each a frame of its own. |
| `kind=<name> - ... install <package>` | The build stops at a kind that is not installed; the default `input=tuple` needs texstage-kinds-rdf. Install the kinds' package where the deck is built and served (`texstage kinds` lists them). |
| `answer=<id> names no quiz of this deck` | The build stops: a frame's `answer=` names a quiz id the deck does not have. |
| `no \quizjoinframe` / `reveal=none, but no frame has answer=` | Warnings: a deck with quizzes but no join frame shows nobody how to join, and a `reveal=none` quiz without an answer frame never shows the class whether it was right. |
| `Text outside a quiz command` | Move material into the surrounding quiz frame, or into the question/choice/explanation argument. |
| `Reference/seed breaks compilation` | Use a fragile frame for inline verbatim, or external UTF-8 data/reference files. |
| `No correct slider value` | Choose bounds and a positive step that actually contain a value in answer +/- tolerance. |
| `Answers appear in a handout` | Check the selected build mode and whether authored answer frames carry the answer option. |
| `Static activity in PowerPoint` | Expected for this release. Use the browser presenter for live activities. |
| `Deck skipped: start the server without --activities f1` | The deck has a choice, number or text activity, which only the activity framework's core runs, a server's default activity type. Start the server without `--activities f1`: `texstage present deck.tex` or `texstage serve`. |
| `Overfull or excessive shrink` | The build checks quiz and answer frames only. It fails at a vertical overfull of 1 pt or more (content in the footline), a horizontal one of 5 pt or more, or a shrink of `--max-shrink` (default 15 %) or more; smaller overfulls are listed as notes. Shorten the content, reduce material on the frame, or select appropriate columns/box sizes. Run the checked build rather than hiding the warning. |
| `Theme overlay is misaligned` | Keep answer-box width/height and lower-left reference point consistent with the hook contract. |

The compiled reference example covers every quiz type, delayed answers, explicit session frames, video poster packaging and tuple/code activity records. Coverage is an inventory of the documented project interfaces; it does not claim to document all commands provided by LaTeX, Beamer, TikZ or other dependencies.

The [reference inventory](latex-reference-inventory.json) and [example build instructions](../examples/reference/README.md) accompany this chapter. Existing courses and pinned styles do not need to change to read or build these isolated examples.


## Deck language and live labels

Texstage records the active Babel or Polyglossia language when LaTeX builds a deck, and everything the deck's audience and lecturer read follows it: the slides' static texts (the quizsetup defaults, the activity labels), the live views on the projector, the phones, the presenter and host windows, the PowerPoint add-in, and the polls typed during the lecture. German variants such as ngerman select German; English and unsupported languages use English. A phone that scans the join slide's code shows its join form in the deck's language, otherwise in its browser language until it has joined. Pages without a deck, such as the deck list and device pairing, use the browser language. Rebuild an existing bundle to capture its deck language.

```
\documentclass{beamer}
\usepackage[ngerman]{babel}
\usepackage{texquiz}
```

In a DBIS course, keep the language in the course dbis-style.sty setting; the course theme's own quizsetup texts still win. Older bundles and TQZ records without a language field remain supported and use English.
