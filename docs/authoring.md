# Writing quizzes in LaTeX

For presenting and participating, see the [illustrated user manual](manual.md)
with [PDF edition](manual.pdf).

`latex/texquiz.sty` adds live quizzes to any Beamer deck. A quiz is written where it is shown:
either as a frame of its own, or inside one of your frames, next to the material it is about.

## Setup

```latex
\usepackage{texquiz}                 % any Beamer deck
\quizsetup{time=20, join-url={https://quiz.example.org}}
```

The texstage commands supply the generic LaTeX search path. Course themes and
chapter-based wrappers are maintained in the separate lecture-tools project.

## A quiz with its own frame

```latex
\begin{quiz}[id=rdf-triple]{Which components form an RDF triple?}
  \choice{Entity, attribute, table}
  \choice*{Subject, predicate, object}          % * marks a correct answer
  \choice{Class, method, argument}
  \choice{Document, link, keyword}
  \explain{An RDF triple consists of a subject, a predicate, and an object.}
  \note{Ask for an example after the reveal.}   % speaker notes and \label work as usual
\end{quiz}
```

The body may contain only `\choice`, `\explain`, `\accept`, `\step`, `\note` and `\label`;
anything else is an error. The question is at the top, the answers at the bottom of the slide.

## A quiz inside your frame

For questions that come with material — a table, a graph, a listing — keep your frame and add
the option `quiz`; the `quiz` environment then typesets the question and the answer boxes where
it stands. Fragile frames (listings) work.

```latex
\begin{frame}[t,fragile,quiz]{Question: Cities on Two Rivers -- How Many Solutions?}
\label{sl:sparqlsem:question-cities-two}
... graph, listing ...
\begin{quiz}[id=cities-two-rivers, reveal=none]{Evaluate $\evalD{P_1\ \mathit{JOIN}\ P_2}$
by the definition. How many solution mappings?}
  \choice{2}\choice{3}\choice{4}\choice*{5}
\end{quiz}
\note{...}
\end{frame}
```

One quiz per frame. Its title (for the lecturer's console) is the frame title. An `\explain`
appears below the answers on the reveal slide and in the solutions - unless the quiz has
`reveal=none`, where the answer frame explains. The reveal slide holds the material, the
answers and the explanation: keep the material compact and the explanation to a line or two;
`texstage build` reports a frame that runs into the footline.

## Answer frames

A frame that gives the answer away gets the option `answer`:

```latex
\begin{frame}[t,shrink=9,answer=cities-two-rivers]{Answer: Five -- the Self-Join Keeps the Diagonal}
```

In the handout it becomes a placeholder page with the neutral title "Answer" (a title like
"The Answer Is C" would tell). With `=<quiz id>` it also tells the live deck that this slide
reveals that quiz: the question is closed and scored there, the phones learn whether they were
right. This fits predict-then-see questions, whose quiz has `reveal=none`: the quiz frame keeps
its reading and question slides, and after the timer the question slide shows what the class
answered — without marking the right answer, which comes on the answer frame. Without
`reveal=none` the quiz frame gets a third slide that reveals the answer itself.

`\label` on placeholder pages still works: references to the frame keep their numbers.

## Question types

| Type | Write | Scored |
|---|---|---|
| single choice | 2–6 `\choice`, exactly one `\choice*` | yes |
| multiple choice | two or more `\choice*` (or `type=multiple`) | yes, exact set (`partial` for partial credit) |
| true/false | `type=truefalse, answer=true` (or `false`) | yes |
| poll | `type=poll`, `\choice` only; `select=multiple` for several | no |
| number | `type=numeric, answer=42, tolerance=2`; `min`, `max`, `step` give a slider, `unit={ms}` | yes; without `answer` it is an unscored estimate |
| short text | `type=text`, one `\accept{...}` per accepted answer | yes |
| open text | `type=open`, `display=wordcloud` or `list`, `max-chars=80` | no |
| ordering | `type=order`, `\step{...}` in the **correct** order | yes (`partial` for partial credit) |
| sketch | `type=sketch` - the phones draw; the lecturer picks drawings for the projector (texstage) | no |

The type is inferred from the body when it is unambiguous (choices with one or several `*`,
`\accept`, `\step`, `answer=true|false|<number>`).

Short-text answers are scored as the text students see: `\accept{AT\&T}` accepts
`AT&T`, and `\accept{M\"unchen}` accepts `München`. Accents, escaped punctuation,
nonbreaking spaces and ordinary text formatting use Hyperref's Unicode conversion.
For math or a command without a plain-text representation, supply it explicitly,
for example `\accept{\texorpdfstring{$x^2$}{x squared}}`. Unsupported conversions
stop the build rather than silently changing the accepted answer. When a phone's answer is
compared, case, accents and spacing do not count: `munchen` and `MÜNCHEN` score as well, so
such variants need no `\accept` of their own.

Numeric questions require a nonnegative `tolerance`, a positive `step` when set,
and `min <= max` when both bounds are set. At least part of the correct interval
(`answer` ± `tolerance`) must lie inside the bounds. An unscored estimate can omit
`answer`; its range and step are still checked. With both bounds, the phone shows
a slider with values `min + k * step` (default `step=1`); at least one selectable
value must be correct. Give a fractional `step` when the expected answer needs it.

## Options

On a quiz: `id` (required, unique: lower-case letters, digits, hyphens), `time` (5–240 s),
`points=standard|double|none`, `leaderboard=true|false`, `reveal=slide|none`, `shuffle`,
`cols=1..6`, `title`.

- **Points**: a right answer earns 1000 points (`points=double`: 2000), falling linearly to half
  of that at the time limit; from the second right answer in a row a streak adds 100, at most
  500. `points=none` makes the quiz unscored. With `partial`, a multiple-choice or ordering
  answer earns the share it got right, and counts as right for the streak only when it is exact.
- **Answer order** is the authored order unless `shuffle` is given; shuffling is deterministic
  (the same in every build) and is the same on the slide and the phones. Ordering questions are
  always shown shuffled and never in their solved order.
- **Columns**: all answers in one row if each fits its cell on one line (the DBIS look allows
  up to six per row, the default look two — Kahoot's 2 × 2), else two columns if each fits on
  two lines, else one answer per row - except that five or six answers always get at least two
  columns. `cols=` overrides this.
- **Leaderboards** are added by the builder after a scored quiz is revealed (unless
  `leaderboard=false`); they are not frames, so frame numbers stay the same in every build. A
  `\quizleaderboardframe` of your own right after the reveal or answer frame takes the place of
  the added one.

In `\quizsetup` (defaults for the whole deck): `time`, `points`, `leaderboard` (DBIS: `false` -
one leaderboard per session, on its last scored quiz with `leaderboard=true`), `reveal`,
`shuffle`, `title` (frame title of quizzes and their placeholders, default "Quiz"; DBIS:
"Question"), `join-url` (the address printed on the join frame of the handout and solutions
PDFs; the live join slide shows the server's own), and the texts `join-title`, `join-text`,
`leaderboard-title`, `podium-title`,
`handout-heading`, `handout-text`, `answer-title`, `answer-heading`, `answer-text`,
`results-text`, `true-label`, `false-label`, `number-hint`, `text-hint`, `multiple-hint`,
`poll-hint` (a poll with several answers: "Tick all that apply.", as on the phones),
`order-hint`, `sketch-hint`, `answer-label`, `accepted-label`. Without them the texts are the
deck's language's - English, or German for a German deck (babel's main language) -; a text
given here wins in any language.

Frames of their own: `\quizjoinframe` (lobby: QR code, PIN, players joining),
`\quizleaderboardframe` (standings) and `\quizpodiumframe` (final standings), each optionally
`[title=..., note={...}]`. A deck with quizzes needs a join frame before its first quiz - the
build warns without one - and usually ends with the podium. They have no
body to write a `\note` into, so `note` is their speaker note - paragraphs and `[stage
directions]` are fine inside the braces; it appears wherever Beamer shows notes and in the
live deck's PowerPoint notes:

```latex
\quizjoinframe[note={Phones out: scan the code, enter the PIN and a nickname.

[Wait until the number of players stops growing.]}]
```

## What each build contains

| Build | How | Quiz | Answer frame | Use |
|---|---|---|---|---|
| handout | a normal compile, e.g. `build-chapter.py` | placeholder page ("Live quiz") | placeholder page | PDF for students **before** the lecture |
| solutions | `texstage pdf --solutions`, or any compile that shows notes (`build-chapter.py --notes`) | question, material, correct answers marked | as written | PDF for students **after** the lecture; the lecturer's notes PDF |
| present | `texstage pdf --present` (preview); `texstage build` makes the PowerPoint | reading slide (the question alone), question slide (+ reveal slide) | as written | PowerPoint + quiz server (instructor only) |

Every quiz, answer, join and podium frame is exactly one frame in every build and one page in
the handout and solutions builds, so "one page per source file", label and frame-number checks
keep working. A plain standalone compile shows the placeholder; to see a quiz while writing,
use `texstage pdf --present 045.tex` (output in `texquiz-out/` next to the source; the preview
ends with the phones' pictures as extra small pages).

## The live deck

```bash
python tools/scripts/texstage-build.py 06-SPARQL-Semantics      # a lecture chapter
texstage build deck.tex                                          # any deck
```

This writes, in the chapter's `build/texquiz/`:

- `06-SPARQL-Semantics.pptx` - the slides as pictures with their notes, as `beamer2pptx.py`
  makes them, plus a live object on every quiz, answer, join, leaderboard and podium slide,
  and before them a first slide that prepares the quiz slides (below);
- `06-SPARQL-Semantics-static.pptx` - the same slides without the live objects, for
  presenting without the quiz (any PC, no server);
- `06-SPARQL-Semantics.bundle/` - the questions and answer keys for the quiz server;
- `06-SPARQL-Semantics.bundle.zip` - the same as one file, to upload by hand (below).

On the quiz server the deck is called `<course>-<chapter>`, e.g. `kg-06-sparql-semantics` -
the course comes from `"course"` in the lecture's `lecture.json` (else the lecture folder's
name), so chapters of different courses never mix. Every build is a version of its own: a
PPTX plays the build it was made with, also next to newer ones - unless a game of a newer build
of the deck is open and was active in the last six hours. The server then refuses the older
build: end that game (the deck's *Lectures …*, *End lecture …*) or play the newer build.

Every build also makes the stage PDF for texstage, the browser presenter (below): the deck
compiled once more with its own note pages, alongside the first; `--no-stage` skips it, for a
quicker build for PowerPoint alone - such a build cannot be presented in the browser, and
`texstage present` builds it again. Options: `--server <url>` (the quiz server the live deck
uses, default the laptop's `http://localhost:8470`), `--height <px>` (default 1080).
`texstage retarget <pptx> --server <url>` points a built live deck at another server in a
second, without building again.

**Presenting** - one command starts the lecture:

```bash
python tools/scripts/texstage-present.py 06-SPARQL-Semantics                # in the browser (texstage)
python tools/scripts/texstage-present.py 06-SPARQL-Semantics --powerpoint   # in PowerPoint
texstage present deck.tex                                                   # any deck
```

It builds the deck first if its build is missing or older than its frames, pictures and styles
in the chapter's folder (`--build` builds anyway, `--no-build` never - after a change to the
lecture's shared `dbis-style.sty`, build with `--build`); `texstage-present.py` also once a
chapter whose slides it refers to has had its deck built anew - the slide numbers it takes from
that chapter's `slides.aux` - or the chapters were renumbered. Whatever build it presents, it
first says again what that build warned of when it was made - references pdflatex left undefined
(?? on the slides), a pass unsettled, a video PowerPoint does not play -, as the build recorded it
in its `built.json`. Then it uses the quiz server already
running on this machine or starts one - over every chapter's build, with the remembered tunnel,
as `texstage-serve.py` does; its window stays open for the lecture - and opens the deck: in
texstage's presenter window, or with `--powerpoint` the live PowerPoint file. `texstage` is
the same command by the browser presenter's name (`texstage deck.tex`). A server that runs
already is used as it is: `present` says which of its options that server does not take
(`--activities` when it runs the other type, `--tunnel`, `--public-url`, `--host`, further
folders - stop it and present again to have them), the activity type it runs if that is not the
default and none was asked for (`--activities f1`, or a server started before the core's became the
default), whether it has the deck's build or why not
(a kind it lacks, a server started with another `--data`), and when the build would end a game
of the deck's build before that has players. **Built again in the lecture** (in the break, say):
the presenter window then asks before the new build ends the running game - the phones would
join again with a new PIN and the scores start anew; *Keep the running build* goes on with it.

**In the browser instead of PowerPoint** (texstage): `texstage present` opens the presenter
window on the deck (`http://localhost:8470/stage` lists all decks of the server); *Projector*
opens the projector window (a click in it makes it full screen). The presenter window shows the
current and the next step, your notes (as text with A−/A+, or the note page), a timer that starts
with the first step - drag the dividers between them to share the window as in PowerPoint (a double
click puts one back; each browser remembers them); B, W and F make the projector black, white or frozen, G shows all frames - the
arrow keys and Enter choose one there -, a number and Enter jumps there. B, W and F cover the projector
only: every step still reaches the phones, so stepping on starts the next quiz round or opens the next
activity - look ahead in the next step's pane, or in G without choosing. The quizzes run as with PowerPoint. Write on the slides with a pen
(Wacom: *Use Windows Ink* on) - it draws without choosing a tool, its eraser end erases - or
choose a tool: P pen, H highlighter, E eraser, L laser pointer (it is where the mouse, the pen or
the finger is; with a mouse the cursor itself turns into the red dot), Z zoom (drag a box; the
whole slide again: a tap on the red "zoomed" label over the slide, the Zoom button, or Z - the
next slide ends the zoom anyway); N inserts a whiteboard page after the frame (Shift+N with a grid); Ctrl+Z /
Ctrl+Y. *Clear* erases the frame's ink at once - ↶ or Ctrl+Z brings it back. **Links** on a slide
(`\href`, `\url` to a web address) work in both windows: over one the cursor turns into a hand
and shows the address, and a click - with the mouse, or a tap of a finger - opens it in a new
tab; in the presenter window while navigating (↖), so a tool keeps its clicks, and never with a
pen, which draws. The ink stays with its
frame for the lecture. When the deck has ink or whiteboard pages from before, *Present* asks: a
*new presentation* starts without them (they stay with the earlier lecture in the archive; the
phones join a new game), *continue that lecture* goes on with them - for a chapter that takes two
lectures. **A pen display in the hall** that shows the projected picture (a Wacom at the
lectern): put the projector window on it - its pen draws there too, in the presenter window's pen
colour and width, the eraser end erases, the side button held shows the laser pointer, and ↶ /
Ctrl+Z in the presenter window take it back; map the tablet's pen to its own screen (Wacom
settings, Mapping). **An iPad as presenter:** *Devices*, *Pair a
device* in the presenter window shows a QR code; scan it with the iPad, and allow the iPad when
the code it shows is the one in the presenter window. The iPad then runs the presenter window
itself - write with the Pencil, swipe to step - while the laptop drives the projector; it stays
paired until you remove it under *Devices*. It needs the laptop's address (the room's network) or
the tunnel; the number next to the connection's dot is the round trip in milliseconds. Turn off
Scribble on the iPad (Settings → Apple Pencil → Scribble): with it on, a stroke started quickly
after the last one is lost - iPadOS keeps that touch for its handwriting. **After the
lecture**, *Make the PDF* gives the annotated PDF for the students - every frame as it was shown
last, with your ink, and the whiteboard pages, without your notes - and keeps it with the quiz
results in the server's archive (`archive/<deck>/<date>-<PIN>/` in its data folder), which
*Download the archive* gives as one ZIP. When the game ends - *New game*, a new build, the next
lecture - its results, polls, questions and sketches go to that folder by themselves; an ended
game's are under the deck's *Lectures …* (its card's ⋯). The phones in a game that ends say so,
with *Join the new game* where the deck has one: it fills in the new PIN and the same nickname, and
a tap on *Join* joins. A phone
that still has the old PIN - the QR code, a form filled in before - is told the game is over and
gets the new game's PIN, for two hours; it does not count as a wrong PIN (300 of those from one
address in ten minutes lock that address out - through the tunnel, a whole lecture hall).
**Recording the lecture:** *Record* in the presenter
window (on the laptop) - check in the dialog that the bar moves when you speak, choose another
microphone if not, then *Choose the screen …* and pick the projector's screen (or the projector
window) in the browser's dialog, which shows every screen and window as a miniature; the
presenter window says first which screen the projector window is on, where the browser lets it.
Once chosen, the dialog closes and the recording waits in the top bar, not started and without a
file: the chosen screen as a live miniature (larger under the pointer - the projector's picture, not
the presenter window?), the microphone's level, *● Start* and ✕. Put right first what needs it -
sharing an entire screen takes a full-screen presenter window out of full screen (the browser's
"is sharing your screen" bar takes the focus; *Start* or ✕ brings full screen back), the bar can be
hidden -, then *● Start*; ✕ lets the screen and the microphone go. The screen can be chosen before
the lecture, too, and *● Start* clicked when it begins. *Also record the computer's sound* (off unless ticked) adds the
deck's videos' sound - the browser gives it for an entire screen ("Also share system audio",
Chromium on Windows), mixed with your voice. The video is what the hall sees - slides, ink,
pointer, quizzes - with your voice; the red dot, pause and stop are in the presenter window only.
The top bar warns when the microphone has heard nothing for 30 s, or is gone; a recording that
stops by itself (the projector window closed, the display changed, *Stop sharing*) says so until
you dismiss it, with *Record again*. It goes to the
server every 10 s into the archive, so a crash loses seconds at most; after *Stop*, *After the
lecture* lists it for *Download* (a WebM file - with ffmpeg installed, also with a seek index).
Changing the deck or starting a new game does not stop it (the projector window follows the deck
by itself); reloading or closing the presenter window does. The presenter window must be opened
as `http://localhost:…` (as `texstage present` does) or over HTTPS - browsers record the screen only
there. **Questions not in the deck:** *Poll* asks one now - yes/no, A–F (answer texts optional:
with the letters alone, the slide or you give the answers), a scale 1–5, a word cloud, free text
or a sketch; type the question, with formulas between `$...$`. The projector shows the poll and
then its results instead of the slide; → or Esc takes it back to your slide. **Questions from the
audience:** *Q&A*, *open for the phones* - the phones get a tab to ask (anonymously) and upvote;
the panel lists them by votes: *Show* puts one on the projector, *Done*, *Delete*, *Block* (the
asker cannot ask any more). **Sketches:** for a sketch question (`type=sketch` in the deck, or a
sketch poll) the phones draw; *Sketches* shows the drawings as they come, and the ones you pick go
on the projector. The archive keeps the polls (`polls.csv`), the questions (`questions.csv`) and
every sketch as SVG.

It also checks your quiz and answer frames as they really look - the course's own checks
only see their placeholders - and fails if a frame's content runs into the footline (a
vertical overfull of 1 pt or more), runs 5 pt or more too wide, is shrunk by 15 % or more
(`--max-shrink`), or a speaker note is too long for its page. Smaller overfulls are listed as
notes; activity and video frames are not checked:

```
  CHECK: 032.tex (quiz cities-two-rivers, present build): overfull 13.8pt too high - the
         content runs into the footline; shrink the frame or shorten the material
```

`shrink=` on quiz frames works as usual; the live overlays still find the answer boxes.

## Playing a quiz

```bash
python tools/scripts/texstage-serve.py                  # a lecture: every chapter's live deck
texstage serve texquiz-out                               # any deck's output folder
```

(the server alone - `texstage-present.py`, above, starts it too). Open
`http://localhost:8470/host` in a browser on the laptop: it pairs with the server by
itself, lists the decks and starts a game. The page shows the slides with the live quiz on top
and works with the arrow keys or a clicker (F: full screen) - a whole quiz lecture without
PowerPoint; with PowerPoint it is the remote and shows who has joined. The
students open the address on the join slide (or scan its QR code) and enter the PIN and a
nickname; a phone that loses its connection, or is reloaded, comes back as the same player.

Every quiz begins with its **reading slide**: the question alone, the answers' room still
empty; the phones show the question too. Nothing runs - the class reads as long as you like.
The next click (→, or the clicker) shows the answers and starts the round: 3 seconds "Get
ready!", then the countdown. In a speaker script, `[Timer.]` marks that click.

During the countdown, the answer counter shows accepted answers out of **accepted answers
plus connected players still waiting to answer**. A submitted answer stays counted if its
phone disconnects. An unanswered player leaves the total while offline and returns on
reconnection; extra tabs for the same player count only once. The total can therefore change
during a question. Disconnecting alone does not end it: the next accepted answer checks
whether everyone connected has answered, and the timer or lecturer can still close it.

On the slides, the mouse shows a few buttons for the lecturer: pause, 10 seconds more, stop
the question, show the answer, ask again (↻, a practice round without points). A game remembers
every question it has asked, and going back never restarts one - so after a test run, or when
you restart the slideshow after an interruption, the questions already asked show their old
results. ↻ on a question rewinds the game there: it asks that question again (practice), and
every question after it runs anew, its old answers and points gone. The host page
also exports the results as a CSV file (rank, score and every answer per student) and starts a
new game (new PIN). After the podium, showing the join slide again starts a new game too -
the same deck for the next group.

## Presenting with PowerPoint

Once per PC and quiz server (then restart PowerPoint):

```bash
texstage addin install            # "texstage (localhost:8470)", for the server on this laptop
texstage addin list               # which servers' add-ins are registered
```

`texstage-present.py <chapter> --powerpoint` (above) starts the server and opens the chapter's
`build/texquiz/<chapter>.pptx` - or start the server and open the file yourself. Present it as usual,
Presenter View included: the clicker alone plays the game - the join slide opens it, a quiz's
reading slide shows its question, the next click shows the answers and starts the countdown,
the reveal slide shows the answer, the leaderboards and the podium follow. Going back never
restarts a question. Nothing to configure: the live deck carries its
server's address and presenter key (the laptop's own, or `--key` for a hosted server), so its
slides pair by themselves. Keep the PPTX to yourself - it holds the key and the answers;
students get the handout PDF. The add-in loads Microsoft's Office.js from the internet, so the laptop needs a
connection (without one, play the deck from the host page instead). `texstage addin uninstall`
removes the add-in.

**Before the lecture**, on the presenting PC:

```bash
python tools/scripts/texstage-check.py 06-SPARQL-Semantics     # or: texstage check <deck>.pptx
```

checks, in a few seconds, what the room would otherwise find out: the add-in of the deck's
server is registered on this PC, the server answers, accepts the deck's key and has the deck
(or its join slide brings it), and PowerPoint can load Office.js. It ends with `ready`, or
says what to do (`PROBLEM` lines) and names the static deck; for a deck built before
2026-10-10 it notes that the join slide prepares the quiz slides (no first slide yet).

**Then, still before the class watches: start the slideshow at the first slide.** The first
time PowerPoint shows a live slide after the file is opened, it starts the slide's add-in, and
the screen flickers white and black for one to four seconds - on every live slide, also going
forward. So the live deck's first slide (it is not in the static deck) prepares them: it shows
every live slide once by itself, covered by "Preparing the quiz slides n / N" (no question, no
answer on the projector; no quiz starts), and comes back - about one and a half minutes for a
chapter of one session. Then it says **Ready**, with the game's PIN, the players and where they
join; go on to your first slide when the lecture starts. Afterwards the whole slideshow runs
without flicker, also when you end it and start again; only closing the file undoes it. A key
pressed meanwhile stops it, and a slideshow started further on skips it: then the join slide
prepares what is left, in the lecture (as it did for every deck built before 2026-10-10).

**Without the quiz, present `<chapter>-static.pptx`.** The live deck cannot fall back by
itself: if its server is not running, PowerPoint puts a yellow "ADD-IN ERROR" bar on every
live slide, and on a PC without the add-in the live slides even stay blank. Its reveal and
leaderboard slides also store only the question picture (what PowerPoint shows while a
slide's add-in starts), so in the editing view's thumbnails they look like their question
slides; in the slideshow the add-in shows the answer.

Every deck reaches its quiz server through its build, the same way for all: `texstage build`
(and so `texstage-build.py`) records the build folder in the data folder of the laptop's quiz
server (`builds.json` in `~/.texstage` - or `~/.texquiz`, the data folder's name until 2026-10-10,
where only that one exists), and that server looks there too - whatever folder it was
started with, also for a deck built while it runs; texstage's presenter lists these decks as
well. A deck built for another server (`--server`, below) is uploaded to it at the end of the
build. The PowerPoint file carries no deck: PowerPoint keeps at most 2 MB for an add-in, too
little for a chapter.

**Uploading a deck by hand.** If a server does not have a deck - the build could not reach
it, or it was built for another one - open that server's deck list in a browser (the host
page `…/host`, or texstage's presenter `…/stage`) and click **Upload a deck**, or drop the
file onto the list: the chapter's `<chapter>.bundle.zip` from `build/texquiz/` - several at once, a
semester's chapters, go up one after the other. The list says
what arrived ("uploaded, 12 quizzes, 64 slides"), or that the server has it already. It
takes the presenter key the page is signed in with. A deck built before 2026-10-09 has no
`.bundle.zip`: zip its `.bundle` folder (Explorer: Send to → Compressed folder) and upload
that.

**The deck page.** texstage's presenter (`…/stage`) keeps the decks in folders of your own:
*New folder*, then drag a deck onto a folder - or onto a step of the path above the list - or
use the deck's ⋯ (*Move to …*, *Rename …*: a name of its own on the page). A card shows the deck's
first slide and when you presented it last (*presented today, 10:14*, *presented 12 Nov*); where its
lecture runs, its button says *Continue* and its tag the game's PIN - elsewhere *Present* (a lecture
left for hours is over: the deck's next opening is a new one). The search field looks through all
folders; *By name*, *Newest first* or *Recently presented* orders them. ⋯ › *Remove from the list*
takes a deck built on this computer off the list - its build folder stays -; the window asks first
if its lecture runs (the lecture goes on). The notice's *Undo*, *Put back* in the list of removed
decks below the cards, or the deck's next build brings it back. A deck uploaded to the server is
deleted instead (⋯ › *Delete*), not while a game of it is under way. A folder's ⋯ renames, moves or
deletes it (what it holds moves up; no deck is deleted). On a phone, a card's buttons go below its
text. Folders and names are each lecturer's own, kept by the server (`library.json` in its
data folder). A deck the server finds and does not play - a kind of activity it lacks (a deck of
texstage's own kinds is skipped with `--activities f1`), a format it is too old for, a broken
`deck.json` - is on no list; the page says at the top which and why, and so does the server's
window when it finds a new one (`skipped: ...`). If `texstage present` names a deck the page
cannot present, the page says why. A deck's ⋯ › *Lectures …* lists its games, the running one
and the ended ones, each with what it left: the results (CSV), the archive (ZIP), *Make the PDF*
from that lecture's ink, its recordings, and *Delete …* for an ended one - its results, ink,
questions and recordings leave the server. ⋯ › *Builds …* lists every build of the deck on the
server: *Present* an older one to go back to it (the window asks before it ends a game of
another build), *Download* one as the `.bundle.zip` another server takes, *Delete …* an upload -
each says what changed since the build before it (*3 slides changed, 1 quiz added*).
`texstage present` goes back from the command line too: name the build folder itself (a
`<name>.bundle`, a server's kept copy in `served/`, an upload), and that build is presented. *End
lecture …* in *Lectures …* ends the open game at once - its results go to the archive, the phones are
told, and an upload of the deck can be deleted right away -; *Continue* presents an earlier lecture's
build with its ink and whiteboard pages, to go on with it. *Select* ticks several decks (Shift: a
range) to move them at once - *Move to …* makes a new folder on the spot - or to remove them. A deck
built meanwhile appears by itself, as does the host console's list (which shows your names and
folders too); the host console also asks before a new build ends a game with players. *Storage*
shows what your decks hold on the server (uploads, copies kept for games, lectures, their archive and
recordings). Nothing is deleted by itself but a deck's builds beyond its newest ten, as before: a lecture
goes with its *Delete …*, and on the server's
machine `texstage data` shows the whole data folder per deck, while `texstage data clean --before
2026-04-01 --recordings` (or `--lectures`, `--copies`, one `--deck`) lists what would go and deletes
it with `--yes` - never an open game, nor a copy it plays, nor a recording still being made.

## Laptop or hosted server

**On the laptop**, `texstage serve` prints where phones join (the laptop's address in the
network) and the laptop's other addresses: if the phones are on another network, e.g. a
hotspot, give that one with `--public-url http://<address>:8470`. Open the printed
`…/api/status` address on your phone before the lecture - if it does not load, the network
keeps phones away from the laptop (eduroam often does): use a hotspot, a tunnel (below), or a
hosted server. The first start makes Windows ask whether Python may accept connections; allow it.

**On the laptop, through a Cloudflare tunnel**, the phones reach the laptop from any network:
they come through Cloudflare, and the laptop only connects out. Set it up once - a Cloudflare
account with a domain of yours, and Cloudflare's `cloudflared`:

```bash
cloudflared tunnel login
cloudflared tunnel create quiz-tunnel
cloudflared tunnel route dns quiz-tunnel quiz.example.org
```

and in `~/.cloudflared/config.yml` (the credentials file is the one `create` wrote):

```yaml
tunnel: quiz-tunnel
credentials-file: C:\Users\<you>\.cloudflared\<tunnel id>.json
ingress:
  - hostname: quiz.example.org
    service: http://localhost:8470
  - service: http_status:404
```

Then start the server with the tunnel - once; it remembers it, and later starts need no option:

```bash
python tools/scripts/texstage-serve.py --tunnel quiz-tunnel
```

The server runs cloudflared itself and stops it when it stops, the join slides show
`quiz.example.org/play`, and after a few seconds it says "the tunnel works" (or why not). The
decks stay as they are: PowerPoint still talks to `http://localhost:8470`, only the students'
address is new - nothing to rebuild. `texstage check` tries that address over the internet,
too. `--no-tunnel` serves in the room's network again and forgets the tunnel: later starts have
none until `--tunnel <name>` is given again. Try the lecture hall's network once:
cloudflared needs to get out to Cloudflare (port 7844).

**On a hosted server** (set up from `deploy/`, see `docs/architecture/design.md` §8): register its add-in
once per PC, and build the decks for it - or point a built deck at it:

```bash
texstage addin install --url https://quiz.example.org                     # then restart PowerPoint
python tools/scripts/texstage-build.py 06-SPARQL-Semantics --server https://quiz.example.org --key=<key>
texstage retarget 06-SPARQL-Semantics/build/texquiz/06-SPARQL-Semantics.pptx --server https://quiz.example.org --key=<key>
```

The key is your own presenter key on that server: whoever runs the server makes it for you
(`texstage lecturer add <name>`) and gives it to you once. With it you see only your own
decks, games and results - other lecturers on the same server have keys of their own. Give it
as `--key=<key>`, with the `=`: an older key may start with `-`, and after a space it would read
as an option. `texstage publish --url https://quiz.example.org --key=<key> --remember` uploads
the builds it finds - in the folders it is given, else in the current one - and then remembers the
key; after that `--key` can be left out. Without a build it stops and keeps nothing. A deck built
for the server (`--server`) is
uploaded to it at the end of the build, complete - for PowerPoint, the host page and texstage.
Decks built for the laptop and then retargeted, or built while the server could not be
reached, go up with
`python tools/scripts/texstage-publish.py --url https://quiz.example.org --key=<key> --remember`;
publishing again sends only decks that changed. Or by hand: **Upload a deck** in the server's
deck list takes the `.bundle.zip` (above).

## Themes

The look is set by a few macros, which a theme redefines: `\texquizprompt`, `\texquizchoice`,
`\texquizchoicefont`, `\texquizchoiceoverhead`, `\texquizmaxcols`, `\texquizexplanation`,
`\texquizhint` (see the comments in `texquiz.sty`). `texquiz-theme-dbis.sty` puts the question
in the course's `\dbisquestion` box and the answers in `dbox-compact` boxes titled A, B, C …,
each with a small shape badge matching the phone buttons.

## Limitations (v0.1)

- No verbatim (`lstlisting`, `\verb`) inside the `quiz` environment itself; put listings in the
  surrounding frame (with `[fragile,quiz]`) or use `\texttt`.
- No overlays inside a quiz frame: the package makes the reveal slide.
- One quiz per frame.
- pdfLaTeX only: `texstage pdf` and `texstage build` always run pdflatex (tested with TeX Live
  2026). The packages' LuaLaTeX code path is untested and no texstage command uses it; XeLaTeX
  is rejected for the present build.

For all four packages, exact options/defaults, output modes and developer hooks,
see the [complete LaTeX reference](latex-reference.md). It is included in the
[manual PDF](manual.pdf) and [LaTeX edition](manual-latex/README.md).
