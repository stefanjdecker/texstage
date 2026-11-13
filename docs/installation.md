# Installation

Public source installation and first-run checks

## Contents

- [What texstage does](#what-texstage-does)
- [Choose your starting path](#choose-your-starting-path)
- [Install Python and obtain the source](#install-python-and-obtain-the-source)
- [Install texstage and check the tools](#install-texstage-and-check-the-tools)
- [Start your first session](#start-your-first-session)
- [Move from one laptop to a real phone](#move-from-one-laptop-to-a-real-phone)

## What texstage does

texstage turns a LaTeX Beamer presentation into an interactive teaching session. You write ordinary slides and add quiz commands in a .tex file. texstage compiles that source, prepares the presentation files, and runs a server that connects your presenter browser, the audience display and participants' phones. You can also create a static PDF handout or a PDF with solutions.

For example, a lecturer writes a multiple-choice question, presents its reading step, opens answering, and then reveals the explanation. Students open a join link, enter the session PIN and answer in a browser. The presenter sees the accepted answers and controls what the audience sees.

| Component | Your part in the session |
| --- | --- |
| Author | Edit a Beamer .tex file in a text or LaTeX editor. A quiz uses commands from texquiz.sty. |
| Presenter computer | Runs the Python command and local server. Builds source using TeX. The private presenter shows notes, next steps and controls. |
| Audience display | A separate projector browser window shows the shared slide. Use an extended desktop to keep notes and answers private. |
| Participant | Uses a reachable /play address, session PIN and nickname in a browser. No Python, TeX, app or account installation is needed. |

The browser workflow is the starting path in this manual. PowerPoint integration, recording, hosted servers and tunnels are optional later topics. texstage can present Beamer material without DBIS styling. It does not create the teaching content for you, and a static PDF by itself does not run a live quiz.


## Choose your starting path

| I want to... | Start here |
| --- | --- |
| Join a lecture | Go directly to Join and wait on your phone, or the Participant quick reference. Obtain the address and PIN from your presenter. Skip installation. |
| Author and present my own slides | Install Python, TeX and texstage below. Follow the supplied demonstration before editing your first quiz. |
| Present a supplied bundle | Install Python and texstage. TeX is only needed to rebuild source. Start texstage serve with a private data directory, open /stage, and use Upload a deck for the supplied .bundle.zip. |
| Organize a course as separate slide files | Use the separate lecture-tools project and its workflow manual. It assembles numbered slides and can call texstage for live output. |
| Use DBIS notation or appearance | Use lecture-tools' reusable LaTeX modules. DBIS branding is an optional theme, not a texstage prerequisite. |
| Edit a Jupyter notebook | Use the lecture-tools notebook manual. This path needs neither texstage nor TeX. |

The companion Python package is named lecture-tools and is maintained in the separate lecture-tools-next repository. It owns slide splitting and assembly, course settings, notebook workflows and DBIS styles. Texstage owns generic LaTeX compilation, PowerPoint conversion and live presentation. In an existing course, follow that course's pinned setup instructions; installing Texstage does not reconnect or upgrade its tools. See the [integration guide](integration.md) for the package boundary and tested pair.

| Term used here | Meaning |
| --- | --- |
| Deck / frame / overlay | A deck is a presentation. A Beamer frame is one logical slide; overlays reveal it in successive steps and can produce several PDF pages. |
| Build / bundle | Building converts source into output. A bundle packages slides, quiz data and browser assets for the server; .bundle.zip is its portable upload. |
| Server / port | The running program that coordinates the browsers; the port is its numbered network endpoint, such as 8765. Keep its terminal open during the session. |
| PIN / presenter key | The PIN admits participants to the current session. A presenter key authorizes control of the server. Give participants the PIN, not the key. |
| texstage / texquiz | texstage is the installed command and application. texquiz.sty is the LaTeX quiz package it ships. Some output folders retain the older name texquiz-out. |


## Install Python and obtain the source

Use CPython 3.12, 3.13 or 3.14 for this candidate; these are the versions targeted by its checks. Install Python from [python.org](https://www.python.org/downloads/) or your operating system package manager. Open a new terminal after installation. On Windows use PowerShell; on macOS or Linux use Terminal. Commands below are entered in that terminal, not in a Python prompt or a LaTeX editor.

The public source is [stefanjdecker/texstage on GitHub](https://github.com/stefanjdecker/texstage). With Git installed, open a terminal in the parent folder where you want to keep the source, then run:

```sh
git clone https://github.com/stefanjdecker/texstage.git
cd texstage
```

Without Git, open the repository link, choose Code > Download ZIP, unpack the archive, and open a terminal in its texstage-main folder. Both paths give a source folder containing pyproject.toml, requirements, examples and docs. Use cd followed by the quoted folder path to change folders; pwd shows where you are. The commands below install this source and its matching dependency locks. They do not assume a PyPI release. Keep the source archive or record git rev-parse HEAD so you can identify the exact revision used.

A virtual environment is a private directory of Python tools and dependencies for this installation. It avoids changing another course environment. Use a new .venv directory and keep your documents outside it. Choose the block for your operating system. Activation selects this environment for the current terminal window. See the [Python environment documentation](https://docs.python.org/3/library/venv.html).

### Windows PowerShell

```
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If python selects another version or is unavailable, but the Python launcher is installed, use py -3.14 instead of python for these first two commands. If activation is blocked by PowerShell policy, use the following session-only alternative; it puts the environment executables first in this terminal without changing system policy.

```
$env:Path = (Resolve-Path .venv\Scripts).Path + ';' + $env:Path
```

### macOS or Linux

```
python3 --version
python3 -m venv .venv
. .venv/bin/activate
```

If your distribution reports that venv or ensurepip is missing, install its Python venv package for the selected Python version, then create the environment again. If python3 selects a different version, use an installed python3.14 (or python3.12/python3.13) for the version check and venv creation. After activation the remaining commands use python on every platform.

### Check the selected environment

```
python -c "import sys; print(sys.executable)"
python -m pip --version
```

The paths printed by both commands must point inside this project's .venv. Reopen and activate the same environment in each new terminal before running the tools. Installation downloads dependencies and needs network access; subsequent local examples use the files already installed.


## Install texstage and check the tools

Run these commands at the texstage source root in the environment just created.

```
python -m pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt
python -m pip install --require-hashes --only-binary=:all: -r requirements/build.txt
python -m pip install --no-deps --no-build-isolation .
```

The first two commands install the tested dependency versions and packaging tools. The third installs this source copy. Keep the requirements files from the same candidate. If a hash check or binary download fails, check the Python version, platform and download source instead of removing the checks.

Decks with live activities also need the kinds of activities - packages of their own in kinds/ - where they are built and where they are served: the build asks an activity's kind, and runs its references as the server does.

```
python -m pip install --no-deps --no-build-isolation ./kinds/texstage-kinds-sql ./kinds/texstage-kinds-rdf
texstage kinds
```

```
texstage --help
python -m pip check
python -c "from importlib.metadata import version; print(version('texstage'))"
```

Success means the command list appears, pip reports no broken requirements, and the version is 0.2.1.dev3 for this edition. If texstage is not found, check the environment paths above; on Windows its executable is .venv/Scripts/texstage.exe. There is no python -m texstage entry point.

LaTeX source is text; a TeX distribution turns it into a PDF. Beamer is the LaTeX document class for slides. Install a current full [TeX Live](https://tug.org/texlive/) distribution, [MacTeX](https://tug.org/mactex/) on macOS, or [MiKTeX](https://miktex.org/howto/install-miktex) on Windows. With MiKTeX, install missing packages and updates through MiKTeX Console before an unattended build. A LaTeX editor alone does not supply the compiler.

For texstage, install Beamer and its dependencies, TikZ and the optional qrcode package for QR rendering. The command supplies texstage's own .sty files automatically; do not install them into your global TeX tree for this tutorial.

```
pdflatex --version
```

Run these checks in the same terminal you will use for the tutorial. They must print version information. If a command is not found, finish the TeX installation, reopen the terminal and activate .venv again. Install any missing .sty dependency through your TeX package manager; pip installs Python dependencies, not TeX packages.

If you only serve a supplied bundle, skip the TeX installation. The source archive includes tutorials and dependency locks; a Python wheel is an installation package and is not a substitute for this tutorial source tree. See [additional installation recipes](installation-advanced.md) for verified-wheel installation and optional PowerPoint setup.


## Start your first session

Goal: see a compiled slide, open the presenter, submit a practice answer, and reveal its result. Stay in the texstage source root with .venv active. Use the supplied synthetic example so this rehearsal does not touch any existing course.

### 1  Compile a static preview

```
texstage pdf --present examples/manual/demo.tex
```

The terminal prints the generated PDF path inside examples/manual/texquiz-out. Open that file in a PDF viewer. You should see the manual demonstration, including a join slide and question steps. This checks the TeX installation; opening the PDF does not start an interactive session.

### 2  Start the presenter and server

```
texstage present examples/manual/demo.tex --data .manual-data --port 8765 --no-tunnel
```

This builds the interactive outputs when needed, stores rehearsal session data in .manual-data, and opens the presenter at http://localhost:8765/stage. The first build takes longer than reopening an unchanged deck. Keep the terminal running. If the browser does not open automatically, open that address yourself. If you see the deck library, choose Present on the manual demonstration.

Use an unused port. If texstage is already serving on 8765, present reuses it, even if you supplied another data directory. Choose another unused port to keep rehearsals separate. --no-tunnel disables remembered tunnel settings for the selected data directory; here that directory belongs only to the rehearsal.

### 3  Rehearse as presenter and participant

- Choose Projector and allow its pop-up. With one monitor, keep it beside the presenter; with two, move it to the audience display.
- Advance to the join slide. For a laptop-only rehearsal, open http://localhost:8765/play in another browser tab, enter the current PIN and a practice nickname. Confirm that the player count increases.
- Advance to a question's reading step, then advance again to open answering. The demonstration allows 240 seconds. Submit an answer in the participant tab and check that the presenter counts it.
- Wait for the round to close or use Stop the question, then advance to reveal the answer. Compare the participant feedback with the audience display. The following illustrated sections explain these controls in detail.

### 4  Stop and resume

Finish the practice session and save any exports you need. Press Ctrl+C in the terminal that started the server to stop it. Closing a browser tab alone does not stop the server. Run the same present command from the same source root to reopen the deck and reuse the rehearsal data. Navigation backwards does not reset answered questions; use Ask again or New game as described later.


## Move from one laptop to a real phone

First confirm the laptop-only rehearsal works. Then put the presenter computer and phone on a network that allows them to reach each other. The server prints a line beginning phones join at. Open that /play address on the phone and enter the current PIN. The phone does not need access to the .tex file or the Python installation.

localhost and 127.0.0.1 mean the device you are using. They work for a participant tab on the presenter computer, but point to the phone itself when opened on a phone. The screenshot addresses are demonstration values; never copy them as the actual classroom address.

Check the printed address ending in /api/status from the phone if joining fails. If that page cannot be reached, check the computer's firewall and whether Wi-Fi client isolation blocks device-to-device connections. If several network addresses are printed, select the one reachable from the phone. A VPN or campus Wi-Fi may require a different network or a hosted setup.

```
texstage present examples/manual/demo.tex --data .manual-data --port 8765 --no-tunnel --public-url http://192.168.1.23:8765
```

The address above is only an example: replace 192.168.1.23 with your presenter computer's reachable address. Stop your rehearsal server before restarting with changed settings. --public-url changes the address advertised to participants; it does not configure the network or open a firewall. For access beyond the local network, follow the hosting and security guides linked in [additional installation recipes](installation-advanced.md).

## Additional installation options

See [additional installation recipes](installation-advanced.md) for verified candidate wheels, optional integrations and deployment notes. Start with the source tutorial above when learning the tools.
