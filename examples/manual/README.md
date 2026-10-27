# Illustrated manual demo

[demo.tex](demo.tex) is the synthetic deck used in the
[user manual](../../docs/manual.md) and its [PDF edition](../../docs/manual.pdf).
It contains a join slide, presenter notes, choice and poll questions, numeric
input, ordering and a podium.

From the repository root, after [installation](../../docs/installation.md):

```sh
texstage pdf --present examples/manual/demo.tex
texstage present examples/manual/demo.tex --data .manual-data --port 8765 --no-tunnel
```

Use an unused port for rehearsal. If a server already runs on port 8765, choose
another port to avoid reusing its session.

The rounds last 240 seconds to leave time for rehearsal and screenshot capture.
Use shorter durations when appropriate for teaching. The static example join URL
is a loopback address for the screenshot session. Real phones must use a reachable
server address; they cannot reach your laptop through 127.0.0.1.

All participants, questions and scores in the manual are synthetic. Use a fresh
data directory when rehearsing. Do not point the demo at an existing course's
server or participant data. The [maintenance guide](../../docs/manual-maintenance.md)
describes the isolated capture setup.
