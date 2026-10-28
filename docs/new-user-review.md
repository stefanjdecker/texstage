# Review for new users

Reviewed 2026-10-28 against candidate 0.2.1.dev0.

The original manual explained the interface and LaTeX commands, but assumed
readers already knew what texstage was, had a source checkout and could activate
a Python environment. Those assumptions interrupted the path to a first result.

| Reader's question | Revision |
|---|---|
| What does texstage actually do? | A concrete teaching scenario and a map of author, presenter, server, projector and participant responsibilities. |
| Do I need lecture-tools, DBIS or PowerPoint? | Task-based starting paths distinguish required components from optional integrations. |
| Where do I get it and where do I type commands? | Source acquisition, project-root identification, terminal choice and candidate-version guidance. |
| How do I install and check it? | Windows and POSIX environments, PowerShell activation fallback, locked installation, compiler checks and expected results. |
| What should my first session look like? | Static preview, automatic build/server start, laptop-only participant rehearsal, answer/reveal checkpoints and shutdown. |
| Why does the phone not connect? | Device-relative localhost, advertised addresses, port reuse, network checks and public-url limitations. |
| How do I make it my own? | A first editable quiz, rebuild instructions and a table distinguishing source, generated files and private server state. |

The [manual](manual.md), native LaTeX article and PDF are generated from
[manual-content.json](manual-content.json). The [installation landing page](installation.md)
follows the same entry path; alternative wheel and hosting recipes remain in
[additional installation recipes](installation-advanced.md). All existing
screenshots and the full LaTeX command reference are retained.

## Validation and limits

- Created a new CPython 3.14 environment on Windows, installed the committed
  runtime/build locks from a previously downloaded wheel cache with hash checks,
  then installed this source copy. CLI help and dependency consistency passed.
- Compiled the documented manual demo, exercised the real `present` entry point
  with automatic browser opening suppressed, and checked the bundle, server
  status, presenter route and participant route. Used an unused local port and
  private rehearsal data. Stopped the test-owned server afterwards.
- Compiled the complete first-quiz source in solutions mode and built its live
  bundle; quiz-frame checks passed.
- Rebuilt the article and reviewed the rendered pages, including the added
  onboarding sections and retained screenshots. Corrected contents spacing to
  avoid a nearly empty spill page. Build-manifest, screenshot-hash, style-inventory,
  dependency-lock and documentation-link checks passed.

This was a documentation review and local rehearsal, not a usability study with
an independent first-time user. A clean-machine network download, macOS/Linux
execution, PowerPoint, physical phones, campus networking and projector operation
were not re-tested in this review. The browser screenshots retain their original
synthetic capture provenance. Before public release, add the real repository and
download links and have a new reader complete the tutorial on another machine.
The existing release and licensing decisions still apply.
