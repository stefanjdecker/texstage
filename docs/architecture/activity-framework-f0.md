# texstage - the activity framework: F0's report (interim)

Status: 2026-11-09, interim. F0's questions
([activity-framework-plan.md](activity-framework-plan.md), here **the plan**, section 3.2)
answered on the development laptop, with the server and the
simulated phones on the same machine - not yet with the set-up of the plan's 3.4 (the presentation
laptop, a second machine, Wi-Fi and the tunnel). The code is on the branch `f0-spike`
(`tools/spike/`, the server's `server/spike_checks.py`, `tools/simulate.py`); the raw results are
in `tools/spike/results/`.

## 1. The machine

The development laptop: an Intel Core of the Tiger Lake H generation (family 6, model 141), 8 cores and 16 threads,
all of one kind; Windows 10 Enterprise 19045; Python 3.14.4 with SQLite 3.50.4; pyoxigraph 0.5.13
and psutil 7.2.2 (installed into the venv for F0, not yet in the locks).

## 2. The answers

**Q1 - `SERVICE`: pyoxigraph 0.5.13 connects.** `SERVICE` and `service` each made one HTTP
connection to a listener on 127.0.0.1; `SERVICE SILENT` connected too and hid the failure behind an
empty solution. `SERVICE` is a syntax error ("expected OPTIONAL"): 0.5.13, unlike 0.3.22,
does not decode escapes in keywords. So F1 refuses `SERVICE` before the query runs, as the plan
says (4.4), after decoding the escapes all the same; the spike does it
(`tools/spike/checks.py`, `names_service`), and a `SERVICE` inside a string still runs.

**Q2 - stopping a query: from inside where results stream, by ending the worker where they do
not.** A 3-way cross product on the KG lecture's seed (123 triples; 1.9 million rows) stopped at
2.016 s of CPU time, checked every 500 rows. `COUNT` over a 4-way cross product (229 million) gives
no row to stop at: it ran past 20 s, and the pool ends its worker at about 2.6 s (Q5).

**New: `ORDER BY` can crash pyoxigraph 0.5.13.** With two sort keys or more, the first mixing
numbers and other literals, over a few thousand rows, Rust's sort ends the whole process: "the
comparison function does not correctly implement a total order" (exit code `0xC0000409`). One key,
IRIs only, or literals of one kind sort fine, and so does the KG lecture's reference
(`ORDER BY ?name`). A student's text can do it; the pool's rule - once more on a fresh worker, then
`internal` (the plan, 4.4) - holds it to two ended workers, 40 ms in all (Q4). Worth an issue for
Oxigraph; whether today's WebAssembly build (0.5.11) has it too was not tried.

**Q3 - nesting: a stack overflow in pyoxigraph's SPARQL parser, which a larger stack avoids.** On a
thread with the default stack, 800 nested groups (2,415 characters) and 2,000 nested parentheses
end the process (`0xC00000FD`); 512 groups (1,551 characters) parse. Turtle - nested collections,
nested blank nodes - and SQLite are safe to 5,000 levels, SQLite refusing deep subqueries with its
own error. On a thread with a 64 MB stack, 2,000 nested groups (6,015 characters, three times
today's limit of 2,000) parse. So the checks run on such a thread in the worker, with a cap of 500
levels as a second guard (both in the spike).

**Q4 - the pool's costs: small.** Six workers and a spare were ready 0.63 s after the start, each
in 0.40 to 0.46 s (started with `spawn`, pyoxigraph and sqlite3 imported), each in the Windows job
object. Every worker prepared the KG seed and the SQL seed in 45 ms (the SPARQL seed 1.4 ms on
one). A job's round trip took 0.1 ms (median) and 0.2 ms (95 %) idle, 0.2 and 0.4 ms with the
other workers busy; the KG reference was checked in 0.7 and 0.8 ms. 300 distinct texts at once were
done in 0.12 s. A text that crashes its worker ran twice and was `internal` after 40 ms, the next
check took 1.2 ms, and the new spare was ready 0.21 s later. The plan's "about a millisecond"
holds, and ending workers costs little here.

**Q5 - budgets: 2 s of CPU time, ended within 0.7 s more.** SQL stopped itself at 2.016 s, five
times of five. A loop no engine can stop was ended by the watchdog at 2.61 to 2.66 s of CPU time
(2.7 to 2.8 s of the clock), as was the SPARQL `COUNT` of Q2. This machine has no efficient cores,
so whether a budget holds on them stays open for a laptop that has them.

**Q6 - memory: every limit holds.** SQLite's cap - the seeds, 32 MB and 256 MB for a text, 302 MB
here - turned a 400 MB string into "out of memory" at once. The watchdog's 1 GB ended a worker that
took 1.3 GB, twice, and then the text was the student's `error`. The job object's 1.5 GB made an
allocation of 2 GB fail inside the worker (`MemoryError`), which went on.

**Q7 - the budgets of AF 15.1, on one machine:**

| run | result |
|---|---|
| 1,100 phones joining within 60 s, each loading a file of 273 KB (KaTeX, as the server sends it today: not compressed) | all joined; 1,093 had the file: median 7 ms, 95 % 26 ms, at most 118 ms |
| 1,000 phones joining at once, the same file | 235 downloads refused (`WinError 1225`): Windows queues few connections that wait to be accepted, and the server was busy with the joins |
| SPARQL, the KG lecture's activity: 1,000 entries within 10 s, most in the last seconds, 315 of them distinct, 10 running into their budget; 1,100 phones | acknowledged: 95 % within 348 ms (budget 0.5 s); verdicts: 95 % within 495 ms (budget 3 s), the ten as `timeout` within 3.3 s; the activity open on every phone after 279 ms, closed after **597 ms** (budget 0.5 s) |
| SQL, the showcase's activity: the same burst; 1,000 phones | acknowledged: 95 % within 10 ms; verdicts: 95 % within 15 ms; open after 253 ms, closed after 183 ms |
| the server, both bursts and the joins | 608 MB and 22 s of CPU time; a worker 27 MB |

**Why the close was slow:** each phone's view goes through all of an activity's contributions to
find its own (`server/activity.py:569`, `:580`) - at the close, 1,100 views over 1,000 entries. It
is today's algorithm, not Python's speed, and a small change fixes it: the contributions indexed by
player. The plan's F1 takes it on (4.5).

## 3. What F0 decides so far

- **Python stays** (AF 15.3): no step was slow at 1,000 phones but the close, and that is an
  algorithm.
- **`SERVICE`** is refused before the query runs, after decoding (Q1).
- **SPARQL is stopped** between solutions where results stream, else by ending its worker (Q2,
  Q4).
- **Nesting:** a 64 MB stack for the checks, and a cap of 500 levels (Q3).
- **The pool on such a laptop:** the cores less two - six workers - and a spare (Q4, Q5).
- **New for F1:** the `ORDER BY` crash, which the retry rule covers; the phones' views indexed by
  player; a storm of connections at once - phones reconnecting after the Wi-Fi drops - as a risk
  (the plan, 4.11).

## 4. Still to do

- The runs of the plan's 3.4 on the presentation laptop, the phones from a second machine, over
  Wi-Fi and through the tunnel, with the presenter window's slide changes timed (`?timing`) and
  PowerPoint running.
- Q5 on efficient cores, if the presentation laptop has them.
- Then this report becomes final, AF section 18 notes it, and F2's plan follows.

## 5. How to repeat it

In Git Bash, from texstage-public, with `MSYS_NO_PATHCONV=1` so that a path such as `--fetch`'s
stays as written:

```bash
python tools/spike/probe_engines.py --json tools/spike/results/engines.json     # Q1 to Q3
python tools/spike/pool.py --json tools/spike/results/pool.json                  # Q4 to Q6
python tools/spike/make_bundle.py <scratch>/bundles                              # the KG and SQL activities
TEXSTAGE_SPIKE_POOL= texstage serve <scratch>/bundles --port 8471 --data <scratch>/data --key <key> --max-players 1200
python tools/simulate.py <scratch>/bundles/spike.bundle --url ws://<laptop>:8471/ws --key <key> \
  --players 1100 --join-within 60 --fetch /static/vendor/katex/katex.min.js \
  --activity kg-rivers --burst 1000 --within 10 --deadline --distinct 0.3 --runaway 0.01
```
