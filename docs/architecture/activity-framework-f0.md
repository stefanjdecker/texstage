# texstage - the activity framework: F0's report (interim)

Status: 2026-11-09, interim, revised after a critical review the same day (section 4). F0's
questions ([activity-framework-plan.md](activity-framework-plan.md), here **the plan**, section
3.2) answered on the development laptop, with the server and the simulated phones on the same
machine - not yet with the set-up of the plan's 3.4 (the presentation laptop, a second machine,
Wi-Fi and the tunnel). The code is on the branch `f0-spike` (`tools/spike/`, the server's
`server/spike_checks.py`, `tools/simulate.py`); the raw results are in `tools/spike/results/`.

## 1. The machine

The development laptop: an Intel Core of the Tiger Lake H generation (family 6, model 141), 8 cores
and 16 threads, all of one kind; Windows 10 Enterprise 19045; Python 3.14.4 with SQLite 3.50.4;
pyoxigraph 0.5.13 and psutil 7.2.2 (installed into the venv for F0, not yet in the locks).

## 2. The answers

**Q1 - `SERVICE`: pyoxigraph 0.5.13 connects.** `SERVICE` and `service` each made one HTTP
connection to a listener on 127.0.0.1; `SERVICE SILENT` connected too and hid the failure behind an
empty solution. `SERVICE` is a syntax error ("expected OPTIONAL"): 0.5.13, unlike 0.3.22,
does not decode escapes in keywords. So F1 refuses `SERVICE` before the query runs (the plan, 4.4),
after decoding the escapes all the same, and by tokens that read variables and prefixed names
whole: the spike's first check also refused `?service`, `:service`, `ex:Service` and a prefix
`service:` (section 4). The spike's check passes 14 such cases now, the escaped keyword and
`SERVICE` in a string or a comment among them (`tools/spike/checks.py`, `names_service`).

**Q2 - stopping a query: from inside where results stream, by ending the worker where they do
not.** A 3-way cross product on the KG lecture's seed (123 triples; 1.9 million rows) stopped at
2.016 s of CPU time, checked every 500 rows. `COUNT` over a 4-way cross product (229 million) gives
no row to stop at: it ran past 20 s, and the pool ends its worker after about 2.7 s (Q5).

**New: `ORDER BY` can crash pyoxigraph 0.5.13.** In our probes, two sort keys or more, the first
mixing numbers and other literals, over a few thousand rows, made Rust's sort end the whole
process: "the comparison function does not correctly implement a total order" (exit code
`0xC0000409`). One key - even over 15,000 rows of mixed terms -, IRIs only, or literals of one
kind sorted fine, and so does the KG lecture's reference (`ORDER BY ?name`). A student's text can do
it; the pool's rule - once more on a fresh worker, then `internal` (the plan, 4.4) - holds it to two
ended workers, 0.1 s in all (Q4). Worth an issue for Oxigraph. Whether today's WebAssembly build
(0.5.11) has it too was not tried.

**Q3 - nesting: a stack overflow in pyoxigraph's SPARQL parser, which a larger stack avoids.** On a
thread with the default stack, 800 nested groups (2,415 characters) and 2,000 nested parentheses
end the process (`0xC00000FD`); 512 groups (1,551 characters) parse. Turtle - nested collections,
nested blank nodes - and SQLite are safe to 5,000 levels, SQLite refusing deep subqueries with its
own error. On a thread with a 64 MB stack, 2,000 nested groups (6,015 characters, three times
today's limit of 2,000) parse. So the checks run on such a thread in the worker, with a cap of 500
levels as a second guard (both in the spike) - tried on Windows only.

**Q4 - the pool's costs: small** (measured again with the pool the review fixed, section 4). Six
workers and a spare were ready 0.59 s after the start, each in 0.39 to 0.43 s - started with
`spawn`, pyoxigraph imported before it said it was ready -, each in the Windows job object. The KG
seed was prepared in 5.2 ms on a worker, 6.4 ms on all seven; the SQL seed in 1.1 ms. A job's round
trip took 0.1 ms (median) and 0.2 ms (95 %), idle or with the other workers busy; the KG reference
was checked in 0.7 and 1.1 ms; a submit held the pool's lock for at most 0.1 ms. 300 distinct texts
at once were done in 0.21 s. With one student's 18 texts of 0.5 s each queued, another student's
text waited 0.50 s - one round of the six workers, not three: the students take turns. A text that
crashes its worker ran twice and was `internal` after 0.1 s, the next check took 1.1 ms, and the
new spare was back, its activities prepared, 0.28 s later.

**Q5 - budgets: 2 s of CPU time, ended within about 1 s more.** SQL stopped itself at 2.016 s, five
times of five. A loop no engine can stop was ended by the watchdog after 2.7 to 3.0 s of the clock,
as was the SPARQL `COUNT` of Q2 (2.7 s). This machine has no efficient cores, so whether a budget
holds on them stays open for a laptop that has them.

**Q6 - memory: every limit holds, SQLite's once its temporary storage is in memory.** SQLite's
cap - the seeds, 32 MB, and 256 MB for a text: 302 MB here - turned a 400 MB string, and a sort of
600 MB, into "out of memory", the sort after 2.9 s and without a temporary file. With SQLite's
default temporary storage, a 300 MB sort under a cap of 64 MB ran in 3.4 s and wrote two temporary
files: the spike, and F1, set `PRAGMA temp_store = MEMORY` (section 4). The watchdog's 1 GB - of
committed memory now, as the job object counts it - ended a worker that took 1.3 GB, twice, and then
the text was the student's `error`. The job object's 1.5 GB made an allocation of 2 GB fail inside
the worker (`MemoryError`), which went on.

**Q7 - the budgets of AF 15.1, on one machine.** Each run with a fresh server and data folder
(`tools/spike/run_q7.py`): 1,100 phones joining within 30 s, each loading a file of 273 KB (KaTeX,
not compressed, as the server sends it today), then 1,000 entries within 10 s, most of them in the
last seconds, 30 % distinct; a share of the texts running into their budget:

| run | acknowledged, 95 % | verdicts, 95 % (slowest) | open, close on every phone | the server's slowest push |
|---|---|---|---|---|
| SPARQL, the KG lecture's activity, 1 % - three runs | 13 to 32 ms | 28 to 881 ms (2.8 to 3.7 s) | 230 to 343 ms, 195 to 244 ms | 64 to 115 ms |
| the same, 3 % | 20 ms | **8.0 s** (10.7 s) | 242 ms, 221 ms | 64 ms |
| the same, 5 % | 123 ms | **15.8 s** (19.7 s) | 280 ms, 207 ms | 99 ms |
| SPARQL on a heavier seed (10,123 triples), 1 % | 73 ms | 104 ms (2.8 s) | 309 ms, 237 ms | 101 ms |
| Turtle, the KG lecture's activity | 10 ms | 14 ms (48 ms) | 232 ms, 181 ms | 67 ms |
| SQL, the showcase's activity, 1 % | 144 ms | 274 ms (2.6 s) | 306 ms, 233 ms | 89 ms |

The budgets: acknowledged within 0.5 s, verdicts within 3 s, a phase change on every phone within
0.5 s. In every run 1,082 to 1,099 phones had the file, 95 % of them within 12 to 25 ms; 1 to 18
had not finished when the tool stopped waiting - its requests had no timeout, so whether the
server or the tool held them is not known (they have one now). With the joins spread out, no
download was refused. The server and its workers were measured in a second run on the heavier seed,
with the runner corrected to tell them apart: the server took 383 MB and 17.2 s of CPU time over
the run, a worker at most 30 MB (`tools/spike/results/q7-heavier.json`).

**What the runs say:**

- **The budgets hold on this machine but for the verdicts, once more than about 1 % of the texts
  run into their budget:** each holds a worker for its whole budget, and 30 of them hold the six
  workers for about 13 s; taking the students in turns cannot help when each is another student's.
  Short checks first are decided (AF 2;
  [activity-framework-plan-f2.md](activity-framework-plan-f2.md), 4.6), and F1 takes them if its
  runs on the laptop meet the same (the plan, 4.4).
- **A phase change is within its budget:** the close took 181 to 244 ms. The 597 ms of the first
  report came from a server that had run four games before (section 4). Of the time to the last
  phone, the server's own push to 1,100 phones took at most 115 ms; the rest is the network and the
  one process that plays all the phones.
- **One run says little:** at 1 %, the verdicts' 95th percentile was 28, 529 and 881 ms in three
  runs alike but for their random texts and times; the heavier seed's two runs gave 73 and 304 ms
  for the acknowledgements, 104 and 973 ms for the verdicts.

## 3. What F0 decides so far

- **Nothing points away from Python yet** (AF 15.3): no step was slow at 1,000 phones because of
  the language. But the checks were cheap, and the phones played on the server's machine; the
  decision is the plan's 3.5's, after the runs of 3.4.
- **`SERVICE`** is refused before the query runs, after decoding, by tokens that read variables and
  prefixed names whole (Q1).
- **SPARQL is stopped** between solutions where results stream, else by ending its worker (Q2, Q4).
- **Nesting:** a 64 MB stack for the checks, and a cap of 500 levels (Q3).
- **SQLite:** its temporary storage in memory (Q6).
- **The pool on such a laptop:** the cores less two - six workers - and a spare; the students in
  turns; nothing blocking while it holds its lock; committed memory watched (Q4 to Q6).
- **New:** texts that run into their budget can use up the pool - short checks first, decided on
  2026-11-09 (Q7; AF 2).

## 4. What the review found, and what changed

A critical review of F0 on 2026-11-09 found, and the spike and this report now take into account:

- **The `SERVICE` check refused correct queries** - `?service`, `:service`, `ex:Service`, a prefix
  `service:` -, since it took any word *service* for the keyword: it reads tokens now (Q1).
- **SQLite wrote temporary files past its cap** - its default temporary storage spills large sorts
  to files: `PRAGMA temp_store = MEMORY` (Q6).
- **The pool held its lock** while sending messages - a prepare carries a whole seed -, while
  waiting up to a second for a dead worker, and while reading every worker's numbers; the event
  loop, which submits under the same lock, could have stalled, and a large seed deadlocked it.
  Messages go out through each worker's outbox now, and the rest happens outside the lock (Q4).
- **The pool served texts first come, first served:** the students take turns now (Q4).
- **A text the server could not check counted as the student's error:** it stays waiting now, as F1
  will count it unchecked.
- **Labels and claims of the first report:** its "SPARQL seed 1.4 ms" was the SQL seed's time; the
  workers imported pyoxigraph only at their first SPARQL prepare, so "ready" said less than it
  seemed; its 608 MB included four games; seven downloads had not finished; that Windows refused
  235 downloads because of its short queue of waiting connections is likely, not proven.
- **The measurements:** single runs, one machine, cheap checks and an assumed share of runaway
  texts. Now three runs at 1 %, one each at 3 and 5 %, a heavier seed, the Turtle activity and a
  fresh server per run; still one machine.

## 5. Still to do

- The runs of the plan's 3.4: the presentation laptop, the phones from a second machine, over
  Wi-Fi and through the tunnel, with PowerPoint running, the presenter window's slide changes timed
  (`?timing`) and the projector's updates counted.
- Q5 on efficient cores, if the presentation laptop has them; the 64 MB stack on Linux and macOS.
- Whether today's WebAssembly build has the `ORDER BY` crash.
- Short checks first, built and measured with the runs at 3 and 5 %.
- Then this report becomes final, and AF section 18 notes it.

## 6. How to repeat it

From texstage-public:

```bash
python tools/spike/probe_engines.py --json tools/spike/results/q1-q3.json      # Q1 to Q3
python tools/spike/pool.py --json tools/spike/results/q4-q6.json                # Q4 to Q6
python tools/spike/run_q7.py <scratch>                                          # Q7, on this machine
```

For the set-up of the plan's 3.4, the server on the presentation laptop and the phones from a
second machine (in Git Bash, `MSYS_NO_PATHCONV=1` keeps `--fetch`'s path as written):

```bash
python tools/spike/make_bundle.py <scratch>/bundles
TEXSTAGE_SPIKE_POOL= texstage serve <scratch>/bundles --port 8471 --data <scratch>/data --key <key> --max-players 1200
python tools/simulate.py <scratch>/bundles/spike.bundle --url ws://<laptop>:8471/ws --key <key> \
  --players 1100 --join-within 30 --fetch /static/vendor/katex/katex.min.js \
  --activity kg-rivers --burst 1000 --within 10 --deadline --distinct 0.3 --runaway 0.01
```
