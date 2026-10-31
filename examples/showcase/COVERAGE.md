# Showcase feature coverage

Target: the current texstage 0.2.1.dev0 candidate. This is a tour of every major
user-facing feature family, not a test of every low-level core macro or every
combination of configuration keys. The command reference remains authoritative
for exhaustive option syntax.

**Source** means an actual executable example in showcase.tex. **Browser control** means
a capability available in the live presenter or participant browser. **Optional setup**
means it needs a separate environment or physical equipment. A static source
cannot click controls, supply real participants, grant microphone permission or
configure a public server.

## Authored content

| Feature | Executable example / example |
|---|---|
| Shared texstage core | Loaded by texquiz, texvideo and texactivity |
| Generic theme, labels and fonts | Preamble: colors, quizsetup, texquizchoicefont |
| Ordinary slides, notes and next-slide preview | Every ordinary frame; example 01 |
| Beamer overlays | Example 03, four incremental steps |
| Join frame, live URL/QR/PIN | Example 04 |
| Single choice, explicit choice IDs and shuffling | meeting, example 07 |
| Multiple choice, partial credit, double points | reuse, example 08 |
| True/false and math | budget, example 09 |
| Scored numeric slider, decimals, units and tolerance | water, example 10 |
| Numeric entry without bounds | plates, example 11 |
| Unscored numeric estimate | duration, example 12 |
| Accepted text variants and normalization | blanket, example 13 |
| Delayed reveal and linked answer frame | blanket plus answer=blanket, example 13 |
| Ordering with partial credit | sequence, example 14 |
| Single- and multiple-selection polls | place and games, examples 05 and 15 |
| Word cloud and longer text list | mood and welcome-ideas, example 15 |
| Sketch question | table-plan, example 16 |
| Timing defaults and overrides; choice columns | Preamble and individual quiz keys |
| Answer explanations | All built-in scored reveals except the delayed text answer |
| Automatic and explicit leaderboard | meeting and explicit standings after sequence |
| Podium | Example 27 |
| Local video, poster, width, ID, start/end, loop, muted | packing, example 17; actual H.264 MP4 |
| Three-field tuple activity, suggestions, manual opening, review, loose terms | bring, example 19 |
| Two-field tuples, automatic opening, exact terms, minimum support | carry, example 20 |
| Per-person activity limits and box height | All five activities |
| SQL with inline seed/reference; fragile frame; token bar | packing-sql, example 22 |
| SPARQL with file seed/reference and manual opening | water-sparql, example 24 |
| Turtle with seed prefixes and reference graph | bread-turtle, example 25 |
| Internal/external hyperlinks | Example 27 |
| Handout, solutions, live bundle, stage PDF, PPTX | Build commands and verification script |

## Live presenter and participant features

| Feature family | Where to record it |
|---|---|
| Presenter/current/next/notes, Page/Text, resizing and timer | Examples 01-03 |
| Projector window, fullscreen, audience/private separation | Examples 01-02; fullscreen by clicking the projector |
| Join, waiting, nickname, reconnect and feedback | Examples 04-16 |
| Read/open/countdown/pause/add time/stop/reveal | Example 07 |
| Choice/numeric distributions and open results | Examples 05 and 07-15 |
| Sketch drawing and presenter-selected gallery | Example 16 |
| Navigation, overview, number jump, Home/End, black/white/freeze | Example 06 and operational appendix |
| Pen, marker, eraser, undo/redo/clear, laser and zoom | Example 06; leave one useful mark after demonstrating Clear |
| Blank/grid whiteboards and persistent per-slide ink | Example 26 and return-to-map example 27 |
| Q&A enable/close, ask, upvote, show/hide, done, remove/block | Example 18 and operational appendix |
| Six spontaneous poll formats | Example 18 montage |
| Activity open/close, approval, hide/show, merge/unmerge, minimum support | Examples 19-20 and operational appendix |
| Code result clusters, equivalent answers, errors, reference reveal, hide/block | Examples 22-25 and operational appendix |
| Pair/revoke device, remote navigation and pen | Example 26, optional physical device |
| Record, microphone level, capture selection, pause/resume/stop/download | Examples 01 and 28, operational appendix |
| Annotated PDF, results CSV, archive, polls/questions and sketch exports | Example 28 |
| Library search/folders/sort/upload, resume/new presentation, replay/new game | Example 29 and operational appendix |

## Optional environments

The deck intentionally uses a local silent clip so it works without third-party
video services. Autoplay, audible playback, online video/YouTube/Vimeo and
alternate video-link options are documented in the [LaTeX reference](../../docs/latex-reference.md)
and require a separate media/browser check before use. They are
not exercised by the supplied silent local clip.

PowerPoint's live add-in, real projector hardware, tablet/stylus behavior,
HTTPS/tunnels, server publication, lecturer/key management and retargeting require
their own setup. Example 30 explains these paths; see the
[user manual](../../docs/manual.md) and [installation guide](../../docs/installation.md).
Activities are browser-only. The static PowerPoint export remains a static deck.

The example does not exercise every display-string override, color/theme
implementation hook, legacy alias or developer-only asset/geometry macro. These
are customization/integration interfaces rather than additional participant
experiences; see the reference for all four style files.

## Validation boundaries

The verification script compiles present/solutions/handout, checks the generated
bundle's feature inventory and notes, verifies the local media and private answer
separation, and runs the actual SQL/SPARQL/Turtle engines on the sample data.
It does not claim to test a physical phone, Office, recording permission, network
access or a tablet. Check these features on the intended presentation equipment.
