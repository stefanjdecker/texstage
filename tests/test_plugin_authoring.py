# SPDX-License-Identifier: Apache-2.0
"""One exercise source reaches live data and static editions through approved hooks."""
import copy
from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

import pytest

from texstage.plugin_api.v1 import json_value, latex_escape
from texstage.plugins import PluginError
from texstage.plugins.catalog import Catalog, discover
from texstage.plugins.manifest import canonical, load_manifest, read_json
from texstage.build.authoring import FRAGMENT_MAX, prepare_sources
from texstage.build import plugins as plugin_build
from test_plugins import distribution

TYPE = "org.example.fixture.plane"
FIXTURE = Path(__file__).parent / "fixtures/authoring_hook.py"
STYLE = b"""\\NeedsTeXFormat{LaTeX2e}
\\ProvidesPackage{texstage-fixture-plane}
\\RequirePackage{texstage}
\\newcommand{\\fixturecounter}[1]{\\texstageprepared{#1}{.92\\linewidth}{.55\\textheight}}
"""


def authoring_distribution(root):
    def change(m):
        m["manifest_version"] = 2
        c = m["capabilities"]["content_types"][TYPE]
        c.pop("build_hook")
        c["authoring_hook"] = "counter"
        c["view_schemas"] = {s: "fixture_plugin/view.json" for s in c["views"]}
        m["latex_exports"] = {"commands": ["fixturecounter"], "environments": []}
    return distribution(root, modify=change, extra_resources={
        "fixture_plugin/__init__.py": FIXTURE.read_bytes(),
        "fixture_plugin/texstage-fixture-plane.sty": STYLE,
        "fixture_plugin/view.json": canonical({"type": "object", "additionalProperties": False})})


class Hooks:
    calls = []
    mutate = staticmethod(lambda made: made)

    def __init__(self, catalog):
        self.plugin = runpy.run_path(str(FIXTURE))["create_plugin"]()

    def close(self):
        pass

    def call(self, cid, method, value, context):
        assert method == "prepare_source"
        self.calls.append((cid, copy.deepcopy(value), copy.deepcopy(context)))
        return self.mutate(json_value(self.plugin.authoring_hooks["counter"](value, context)))


def source_files(root):
    root.mkdir(parents=True, exist_ok=True)
    tex = root / "lesson.tex"
    tex.write_text(r"""\documentclass[aspectratio=169]{beamer}
\usepackage{texquiz}
\usepackage{texstage-fixture-plane}
\begin{document}
\begin{frame}{Counter exercise}
\fixturecounter{counter}
\end{frame}
\end{document}
""", encoding="utf-8")
    (root / "counter.json").write_bytes(canonical({"initial": 100, "increment": 10, "label": "Counter #1 & values"}))
    sidecar = root / "lesson.activities.json"
    sidecar.write_bytes(canonical({"format": 1, "language": "en", "items": [
        {"id": "counter", "type": TYPE, "source": "counter.json"}]}))
    return tex, sidecar


@pytest.fixture
def authoring(tmp_path, monkeypatch):
    provider = discover(distributions=[authoring_distribution(tmp_path / "installed")])[0]
    catalog = Catalog([provider])
    monkeypatch.setattr("texstage.build.authoring.Workers", Hooks)
    Hooks.calls = []
    monkeypatch.setattr(Hooks, "mutate", staticmethod(lambda made: made))
    tex, sidecar = source_files(tmp_path / "deck")
    return SimpleNamespace(root=tex.parent, tex=tex, sidecar=sidecar, catalog=catalog,
                           out=tmp_path / "out", provider=provider)


def prepare(w):
    return prepare_sources(w.tex, w.sidecar, w.catalog, w.out)


def test_revision_2_selects_exactly_one_hook(authoring):
    manifest = authoring.provider.manifest
    load_manifest(canonical(manifest))
    c = manifest["capabilities"]["content_types"][TYPE]
    c["build_hook"] = "plane"
    with pytest.raises(PluginError):
        load_manifest(canonical(manifest))
    del c["build_hook"]
    del c["authoring_hook"]
    with pytest.raises(PluginError):
        load_manifest(canonical(manifest))


def test_preparation_identity_and_source_change(authoring):
    a = prepare(authoring)
    b = prepare(authoring)
    assert a.directory != b.directory and a.items == b.items
    assert len(Hooks.calls) == 2
    assert Hooks.calls[0][2]["language"] == "en"
    source = authoring.root / "counter.json"
    source.write_bytes(canonical({"initial": 100, "increment": 20, "label": "Counter #1 & values"}))
    with pytest.raises(PluginError, match="stale prepared source"):
        a.validate(authoring.catalog)
    c = prepare(authoring)
    assert c.items["counter"]["digest"] != a.items["counter"]["digest"]
    assert c.items["counter"]["prepared"]["private"]["answer"] == 120
    assert "Add 20" in c.items["counter"]["fragments"]["exercise"]
    assert "120" in c.items["counter"]["fragments"]["solutions"]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(format=2),
    lambda d: d.update(unknown=True),
    lambda d: d["items"].append(dict(d["items"][0])),
    lambda d: d["items"][0].update(source="../secret.json"),
    lambda d: d["items"][0].update(type="org.example.disabled.counter"),
    lambda d: d.update(language="../bad"),
])
def test_invalid_sidecars_fail_before_hooks(authoring, mutate):
    d = read_json(authoring.sidecar.read_bytes())
    mutate(d)
    authoring.sidecar.write_bytes(canonical(d))
    with pytest.raises(PluginError):
        prepare(authoring)
    assert not Hooks.calls


def test_disabled_profile_never_imports(authoring):
    with pytest.raises(PluginError, match="not enabled"):
        prepare_sources(authoring.tex, authoring.sidecar, Catalog(), authoring.out)
    assert not Hooks.calls


@pytest.mark.parametrize("mutation", ["fragment", "format", "private", "diagnostics", "asset", "executable"])
def test_malformed_hook_outputs(authoring, monkeypatch, mutation):
    def mutate(made):
        if mutation == "fragment": made["fragments"]["exercise"] = "x" * (FRAGMENT_MAX + 1)
        if mutation == "format": made["format"] = True
        if mutation == "private": made["prepared"]["private"] = []
        if mutation == "diagnostics": made["prepared"]["diagnostics"] = [{"bad": True}]
        if mutation == "asset": made["prepared"]["assets"] = {"image": {"source": "../escape.png", "visibility": "public"}}
        if mutation == "executable": made["prepared"]["assets"] = {"script": {"source": "code.mjs", "visibility": "public"}}
        return made
    monkeypatch.setattr(Hooks, "mutate", staticmethod(mutate))
    with pytest.raises(PluginError):
        prepare(authoring)


def test_changed_material_and_profile_fail(authoring):
    a = prepare(authoring)
    with pytest.raises(PluginError, match="identity"):
        a.validate(Catalog())
    (a.directory / "counter-solutions.tex").write_text("changed", encoding="utf-8")
    with pytest.raises(PluginError, match="artifact changed"):
        a.validate(authoring.catalog)
    b = prepare(authoring)
    b.items["counter"]["prepared"]["private"]["answer"] = -1
    with pytest.raises(PluginError, match="item data changed"):
        b.validate(authoring.catalog)


def test_record_binding_and_no_second_build_hook(authoring, monkeypatch):
    a = prepare(authoring)
    row = a.items["counter"]
    definition = ["counter"] + [v.encode().hex() for v in [TYPE, "", "", "", ""]]
    tqz = SimpleNamespace(records={"plugin": [definition],
                         "prepared": [["counter", TYPE, row["digest"]]]},
                         pages={1: SimpleNamespace(items=[SimpleNamespace(id="counter", kind="plugin")])})
    monkeypatch.setattr(plugin_build, "Workers", Hooks)  # would fail on a second prepare call
    public, private, files, requirements = plugin_build.prepare(tqz, authoring.root, authoring.catalog, a)
    assert len(Hooks.calls) == 1
    assert public[TYPE]["counter"]["increment"] == 10
    assert private[TYPE]["counter"]["private"]["answer"] == 110
    assert not files and len(requirements) == 1
    assert "Worked answer" not in canonical(public).decode()
    assert "engine" not in row["prepared"]["evaluations"]["value"]
    with pytest.raises(PluginError, match="require --activities"):
        plugin_build.prepare(tqz, authoring.root, authoring.catalog)
    for rows in ([], [["extra", TYPE, row["digest"]]], [["counter", TYPE, "0" * 64]]):
        with pytest.raises(PluginError):
            a.validate_rows(rows)


def test_plain_text_escaping():
    assert latex_escape(r"A&B_1 #2 50% {x} \ ~ ^ $") == (
        r"A\&B\_1 \#2 50\% \{x\} \textbackslash{} \textasciitilde{} \textasciicircum{} \$")


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs pdfLaTeX")
def test_real_compiles_share_one_preparation_and_keep_solutions_private(authoring, monkeypatch):
    from texstage.build.builder import BuildOptions, build
    from texstage.build.latex import compile_deck
    from texstage.build.pdf import Pdf
    from texstage.build.compiler import compile_latex
    from texstage.server.bundles import load_bundle

    (authoring.root / "public.txt").write_text("Public reminder.", encoding="utf-8")
    (authoring.root / "private.txt").write_text("Private solution detail.", encoding="utf-8")
    def add_assets(made):
        made["prepared"]["assets"] = {
            "reminder": {"source": "public.txt", "visibility": "public"},
            "detail": {"source": "private.txt", "visibility": "private"}}
        made["fragments"]["exercise"] += r"\par\input{\texstagepreparedasset{counter}{reminder}}"
        made["fragments"]["solutions"] += r"\par\input{\texstagepreparedasset{counter}{detail}}"
        return made
    monkeypatch.setattr(Hooks, "mutate", staticmethod(add_assets))
    monkeypatch.setattr("texstage.plugins.policy.catalog_for", lambda data: authoring.catalog)
    options = BuildOptions(stage=True, key="synthetic-authoring-key", activities=authoring.sidecar, height=480)
    result = build(authoring.tex, authoring.out, options)
    assert len(Hooks.calls) == 1
    assert not result.problems
    bundle = load_bundle(result.bundle, catalog=authoring.catalog)
    assert bundle.items[TYPE]["counter"]["increment"] == 10
    assert bundle.keys["items"][TYPE]["counter"]["private"]["answer"] == 110
    assert bundle.file(bundle.items[TYPE]["counter"]["plugin_assets"]["reminder"]).read_text() == "Public reminder."
    assert bundle.file(bundle.keys["items"][TYPE]["counter"]["assets"]["detail"]) is None
    assert not list(result.bundle.rglob("*prepared*")) and not list(result.bundle.rglob("*.tex"))
    assert result.static.is_file() and result.stage is not None
    def text(pdf):
        with Pdf(pdf) as p:
            return " ".join(page.text() for page in p)
    handout = compile_deck(authoring.tex, "handout", authoring.out, plugins=authoring.catalog,
                            preparation=options.preparation)
    assert "Worked answer" not in text(handout.pdf)
    assert "Public reminder" in text(handout.pdf) and "Private solution" not in text(handout.pdf)
    assert "Worked answer" not in text(result.stage.pdf)
    assert "Worked answer: 110" in text(authoring.out / "build/lesson-solutions.pdf")
    assert "Private solution detail" in text(authoring.out / "build/lesson-solutions.pdf")
    exported = options.preparation.export(authoring.tex, authoring.catalog)
    direct = compile_latex(exported["handout"], output_dir=authoring.out / "direct", passes=2)
    assert direct.returncode == 0, direct.stdout[-2000:]
    assert "Worked answer" not in text(direct.pdf)
    (authoring.root / "counter.json").write_bytes(canonical({"initial": 100, "increment": 20}))
    stale = compile_latex(exported["handout"], output_dir=authoring.out / "stale")
    assert stale.returncode != 0 and "Stale prepared input" in stale.log_text
    rebuilt = build(authoring.tex, authoring.out / "changed", options)
    assert len(Hooks.calls) == 2
    changed = load_bundle(rebuilt.bundle, catalog=authoring.catalog)
    assert changed.items[TYPE]["counter"]["increment"] == 20
    assert changed.keys["items"][TYPE]["counter"]["private"]["answer"] == 120
    assert "Add 20" in text(rebuilt.stage.pdf)
    assert "Worked answer: 120" in text(authoring.out / "changed/build/lesson-solutions.pdf")


def test_asset_content_and_parent_symlinks_are_checked(authoring, monkeypatch, tmp_path):
    asset = authoring.root / "data.txt"
    asset.write_text("one", encoding="utf-8")
    def add_asset(made):
        made["prepared"]["assets"]["reminder"] = {"source": "data.txt", "visibility": "public"}
        return made
    monkeypatch.setattr(Hooks, "mutate", staticmethod(add_asset))
    prepared = prepare(authoring)
    asset.write_text("two", encoding="utf-8")
    with pytest.raises(PluginError, match="stale prepared source"):
        prepared.validate(authoring.catalog)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "data.txt").write_text("external", encoding="utf-8")
    try:
        (authoring.root / "link").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    with pytest.raises(PluginError, match="escapes"):
        plugin_build.source_file(authoring.root, "link/data.txt")


def test_cli_preparation_pdf_forwarding_and_failed_present_stops(authoring, monkeypatch, capsys):
    from texstage import cli
    monkeypatch.setattr("texstage.plugins.policy.catalog_for", lambda data: authoring.catalog)
    assert cli.main(["prepare", str(authoring.tex), "--activities", str(authoring.sidecar),
                     "-o", str(authoring.out)]) == 0
    assert "handout:" in capsys.readouterr().out
    calls = []
    def compile_fake(*args, **kw):
        calls.append(kw)
        return SimpleNamespace(pdf=authoring.out / "handout.pdf", overfull=0)
    monkeypatch.setattr("texstage.build.latex.compile_deck", compile_fake)
    assert cli.main(["pdf", str(authoring.tex), "--activities", str(authoring.sidecar)]) == 0
    assert calls[0]["activities"] == authoring.sidecar
    monkeypatch.setattr(cli, "needs_build", lambda *a: None)
    built = []
    monkeypatch.setattr(cli, "cmd_build", lambda args: built.append(args) or 1)
    assert cli.main(["present", str(authoring.tex), "--activities", str(authoring.sidecar)]) == 1
    assert built[0].activities == str(authoring.sidecar)
    assert cli.main(["present", str(authoring.tex), "--activities", str(authoring.sidecar), "--no-build"]) == 2
