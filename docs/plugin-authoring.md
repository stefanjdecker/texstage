# Preparing plugin activities before LaTeX

The experimental host can prepare an enabled plugin's exercise before any LaTeX
pass. One JSON source produces its live data, exercise and worked solution.
The build reuses that preparation for presenter slides, stage slides, solution
checks and static PowerPoint. The PDF command uses the same pipeline for
handouts and solutions.

This implements the H2 host prerequisite. The transaction engine and lesson
interfaces remain separate milestones. The counter snippets below illustrate
the provider contract; the executable regression fixture lives in
[the authoring tests](../tests/test_plugin_authoring.py).

## Author a deck

Install and explicitly enable a compatible provider in a disposable profile,
as described in [Experimental plugins](plugins.md). A style or activity file
never installs or enables a provider.

Beside `lesson.tex`, create `lesson.activities.json`:

```json
{
  "format": 1,
  "language": "en",
  "items": [
    {"id": "counter", "type": "org.example.counter.exercise", "source": "counter.json"}
  ]
}
```

The activity file and every source/asset must be under the master deck's
directory. Source paths are relative to that directory, even when the activity
file is in a subdirectory. Absolute source paths, traversal, symbolic links and
directory junctions are rejected. Sources must be JSON objects without duplicate
keys or non-finite values. There are at most 128 items, with portable unique IDs
(including case-insensitive uniqueness). Language defaults to `en`.

Load `texstage` (and the provider's declared style as needed), then place the
activity in a frame:

```tex
\begin{frame}{Predict the result}
  \texstageprepared{counter}{.92\linewidth}{.55\textheight}
\end{frame}
```

The command selects the exercise fragment for present/handout mode and the
worked fragment for solutions. It records the same item, type and preparation
digest in every mode. A provider style can wrap it in its own command.
Approved styles load from the selected profile; nothing is copied into a course.

From the deck directory:

```sh
texstage build lesson.tex --activities lesson.activities.json --data ./plugin-profile
texstage pdf lesson.tex --handout --activities lesson.activities.json --data ./plugin-profile
texstage pdf lesson.tex --solutions --activities lesson.activities.json --data ./plugin-profile
texstage present lesson.tex --activities lesson.activities.json --data ./plugin-profile --no-tunnel
```

Each command also accepts `--plugins-lock`. `present --activities` rebuilds
explicitly and stops if preparation/build fails; it cannot be combined with
`--no-build`. This prevents presenting a cached deck after an exercise changes.
The static PowerPoint is the `*-static.pptx` output of `build`.

## Select English or German

Set both the main LaTeX language and the activity sidecar language:

| Edition | LaTeX preamble | Sidecar, beside `format` and `items` |
| --- | --- | --- |
| English | `\usepackage[english]{babel}` | `"language": "en"` |
| German | `\usepackage[ngerman]{babel}` | `"language": "de"` |

With several Babel languages, use an explicit main language, for example
`\usepackage[main=ngerman,english]{babel}`. Rebuild with the matching `--activities`
file. Babel/Polyglossia selects the deck language passed to live plugin views;
the sidecar selects generated static exercises and solutions. It does not
translate arbitrary frame titles, questions, notes or source text.

The phone's join, waiting, quiz and built-in activity controls follow the deck's
language, just like plugin controls. The QR link supplies the PIN; entering a
valid PIN manually also selects that session's language before joining.
The browser language is only a fallback until a session is identified.
There is no per-student plugin language switch. Missing or unsupported deck languages
fall back to English. Provider translation coverage and missing-text fallback
are provider-specific. Supply both authored translations for a bilingual lesson.

The collection's [language guide](https://github.com/stefanjdecker/texstage-plugins/blob/codex/database-activity-examples/docs/languages.md)
and [database example](https://github.com/stefanjdecker/texstage-plugins/tree/codex/database-activity-examples/examples/database)
show matching masters with shared exercise data and reference answers.

## Implement a provider

A revision-2 content capability declares exactly one of `authoring_hook` and
the existing `build_hook`. Its state hook, views, view schemas and other
capabilities retain their existing contracts. For example, declare
`"authoring_hook": "counter"` and register the matching hook:

```python
from texstage.plugin_api.v1 import (
    PluginV1, PreparedAuthoring, PreparedItem, latex_escape,
)

def prepare_counter(source, context):
    initial, increment = source["initial"], source["increment"]
    if type(initial) is not int or type(increment) is not int:
        raise ValueError("integer counter required")
    prompt = latex_escape(f"Start at {initial}; add {increment}.")
    return PreparedAuthoring(
        prepared=PreparedItem(
            public={"initial": initial, "increment": increment},
            private={"answer": initial + increment},
        ),
        fragments={
            "exercise": prompt,
            "solutions": prompt + latex_escape(f" Answer: {initial + increment}."),
        },
    )

# Alongside the content type's state hook:
plugin = PluginV1(authoring_hooks={"counter": prepare_counter},
                 state_hooks={"counter": CounterState()})
```

Context contains `item_id`, qualified `type`, `language`, a relative source
identity with SHA-256, and byte limits. The hook runs in the existing enabled
provider worker with a two-second timeout. It returns `PreparedAuthoring` (or
its exact JSON representation) with `format=1`, `prepared` and `fragments`.
A prepared item is never sent through a second post-TeX build hook.

Both `exercise` and `solutions` fragments are required, at most 128 KiB UTF-8
each. The complete JSON response remains within 8 MiB. Existing evaluation seed
and reference limits apply. Diagnostics are at most 64 strings of 2,000
characters. Source and asset files are at most 2 MiB each; assets are limited to
128 declarations using the existing data/image extensions.

Fragments are trusted provider TeX. Use `latex_escape` for plain exercise text;
it is not a filename or arbitrary-TeX sanitizer. Providers must exclude private
answers from exercise fragments and public item fields. The worker provides
process isolation, not a security sandbox for untrusted code.

## Assets, identities and privacy

Use `PreparedItem.assets` to map logical names to
`{"source": "data/example.png", "visibility": "public"}` or `"private"`.
Logical names use the simple item-ID syntax. Fragments can use a materialized
copy via `\texstagepreparedasset{counter}{diagram}`; private assets through this
command are available only in solutions mode.

The host computes preparation identity from the provider pin, source bytes,
type/item/language, returned format and prepared data/fragments, and declared
asset hashes. Artifacts go into a fresh owned `prepared-*` directory.
Reused preparations check source, profile and artifact hashes before and after
compilation. All modes reject missing/extra/mismatched prepared records; live
modes also check geometry bindings and collisions with built-in items. Loaded
plugin styles must match their installed, approved paths and bytes.

Only public item data and explicitly public ordinary assets enter public bundle
routes. Private data/assets remain in private bundle material. Generated TeX,
raw exercise JSON and solution fragments are not copied into the bundle.
Local preparation directories contain private build material, including worked
solutions; distribute the intended PDF/bundle output.

## Export for direct pdfLaTeX

```sh
texstage prepare lesson.tex --activities lesson.activities.json --data ./plugin-profile
```

This prints local entry points for handout, solutions and present. They include
the original deck, prepared fragments and explicit style paths, and run no
Python hook. Compile from the master deck directory so ordinary relative
images and includes retain their meaning, using the actual printed path:

```sh
pdflatex -output-directory=texquiz-out texquiz-out/prepared-XYZ/lesson-handout-prepared.tex
```

These are local materialized builds, not portable source packages. They check
exercise, activity-file, asset, fragment and approved package bytes and refuse
stale inputs. Regenerate after changing those inputs or environments. Python
uses SHA-256; direct pdfLaTeX uses TeX's MD5 file digest for freshness, not to
authenticate untrusted providers. Paths containing braces, percent, hash, caret
or newlines are rejected because they cannot be safely embedded by this bridge.

## Verification and remaining work

Tests cover changed sources, disabled providers, invalid outputs, confined
assets, identity/record mismatches, private/public routing, real PDF/PowerPoint
builds, direct-pdfLaTeX stale rejection and CLI behavior. Existing post-TeX
plugins continue using revision 1 or revision 2 `build_hook`.
The transaction engine, phased lesson, editable browser interfaces, measured
classroom capacity and published compatibility pins remain open.
