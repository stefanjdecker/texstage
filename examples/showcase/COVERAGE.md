# Showcase feature coverage

Target: the current texstage 0.2.1.dev0 candidate. This is a tour of every major
user-facing feature family, not a test of every low-level core macro or every
combination of configuration keys. The command reference remains authoritative
for exhaustive option syntax.

**Source** means an actual executable example in showcase.tex. **Live cue** means
a documented action in the presenter/phone during filming. **Optional setup**
means it needs a separate environment or physical equipment. A static source
cannot click controls, supply real participants, grant microphone permission or
configure a public server.

## Authored content

| Feature | Executable example / scene |
|---|---|
| Shared texstage core | Loaded by texquiz, texvideo and texactivity |
| Generic theme, labels and fonts | Preamble: colors, quizsetup, texquizchoicefont |
| Ordinary slides, notes and next-slide preview | Every ordinary frame; scene 01 |
| Beamer overlays | Scene 03, four incremental steps |
| Join frame, live URL/QR/PIN | Scene 04 |
| Single choice, explicit choice IDs and shuffling | meeting, scene 07 |
| Multiple choice, partial credit, double points | reuse, scene 08 |
| True/false and math | budget, scene 09 |
| Scored numeric slider, decimals, units and tolerance | water, scene 10 |
| Numeric entry without bounds | plates, scene 11 |
| Unscored numeric estimate | duration, scene 12 |
| Accepted text variants and normalization | blanket, scene 13 |
| Delayed reveal and linked answer frame | blanket plus answer=blanket, scene 13 |
| Ordering with partial credit | sequence, scene 14 |
| Single- and multiple-selection polls | place and games, scenes 05 and 15 |
| Word cloud and longer text list | mood and welcome-ideas, scene 15 |
| Sketch question | table-plan, scene 16 |
| Timing defaults and overrides; choice columns | Preamble and individual quiz keys |
| Answer explanations | All built-in scored reveals except the delayed text answer |
| Automatic and explicit leaderboard | meeting and explicit standings after sequence |
| Podium | Scene 27 |
| Local video, poster, width, ID, start/end, loop, muted | packing, scene 17; actual H.264 MP4 |
| Three-field tuple activity, suggestions, manual opening, review, loose terms | bring, scene 19 |
| Two-field tuples, automatic opening, exact terms, minimum support | carry, scene 20 |
| Per-person activity limits and box height | All five activities |
| SQL with inline seed/reference; fragile frame; token bar | packing-sql, scene 22 |
| SPARQL with file seed/reference and manual opening | water-sparql, scene 24 |
| Turtle with seed prefixes and reference graph | bread-turtle, scene 25 |
| Internal/external hyperlinks | Scene 27 |
| Handout, solutions, live bundle, stage PDF, PPTX | Build commands and verification script |

## Live presenter and participant features

| Feature family | Where to record it |
|---|---|
| Presenter/current/next/notes, Page/Text, resizing and timer | Scenes 01-03 |
| Projector window, fullscreen, audience/private separation | Scenes 01-02; fullscreen by clicking the projector |
| Join, waiting, nickname, reconnect and feedback | Scenes 04-16 |
| Read/open/countdown/pause/add time/stop/reveal | Scene 07 |
| Choice/numeric distributions and open results | Scenes 05 and 07-15 |
| Sketch drawing and presenter-selected gallery | Scene 16 |
| Navigation, overview, number jump, Home/End, black/white/freeze | Scene 06 and operational appendix |
| Pen, marker, eraser, undo/redo/clear, laser and zoom | Scene 06; leave one useful mark after demonstrating Clear |
| Blank/grid whiteboards and persistent per-slide ink | Scene 26 and return-to-map scene 27 |
| Q&A enable/close, ask, upvote, show/hide, done, remove/block | Scene 18 and operational appendix |
| Six spontaneous poll formats | Scene 18 montage |
| Activity open/close, approval, hide/show, merge/unmerge, minimum support | Scenes 19-20 and operational appendix |
| Code result clusters, equivalent answers, errors, reference reveal, hide/block | Scenes 22-25 and operational appendix |
| Pair/revoke device, remote navigation and pen | Scene 26, optional physical device |
| Record, microphone level, capture selection, pause/resume/stop/download | Scenes 01 and 28, operational appendix |
| Annotated PDF, results CSV, archive, polls/questions and sketch exports | Scene 28 |
| Library search/folders/sort/upload, resume/new presentation, replay/new game | Scene 29 and operational appendix |

## Options and environments outside the main take

The deck intentionally uses a local silent clip so it works without third-party
video services. Autoplay, audible playback, online video/YouTube/Vimeo and
alternate video-link options are documented in the [LaTeX reference](../../docs/latex-reference.md)
and require a separate media/browser rehearsal if included in the video. They are
not exercised by the supplied silent local clip.

PowerPoint's live add-in, real projector hardware, tablet/stylus behavior,
HTTPS/tunnels, server publication, lecturer/key management and retargeting require
their own setup. Scene 30 explains these paths; see the
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
access or a tablet. Follow RECORDING.md on the equipment used for filming.
