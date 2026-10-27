# Demo deck

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
