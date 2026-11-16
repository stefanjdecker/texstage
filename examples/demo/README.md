# Demo decks

`demo.tex` is synthetic material exercising live quizzes. From the repository root,
after [installation](../../docs/installation.md):

```sh
texstage pdf examples/demo/demo.tex
texstage pdf --present examples/demo/demo.tex
texstage build examples/demo/demo.tex
texstage present examples/demo/demo.tex
```

The first command creates the handout. Output goes to `texquiz-out` beside the
source by default. Use `--output-dir` for a separate destination and `--data`
on live commands for a disposable server data directory. Do not distribute the
live PowerPoint file with its presenter key as student material.

## Live activities

`activities.tex` shows texstage's own kinds of live activities: a choice of
several options, a number and a short answer, each with a reference. They run on
the activity framework's core, so start the server with `--activities core`; a
server of the default type skips the deck and says why:

```sh
texstage pdf --solutions examples/demo/activities.tex
texstage present examples/demo/activities.tex --activities core --port 8471
```

Use a port where no server runs yet: `present` reuses a running server as it is.
The solutions show the references; the handout does not. Phones see the options,
a number field or a text field; the projector shows a tally, a histogram or the
grouped answers. Reveal an activity from the presenter's Activities panel. The
[manual](../../docs/manual.md#choice-number-and-text-activities) describes the keys.
