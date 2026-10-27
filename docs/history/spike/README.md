# Spike S1: content add-ins written into a PPTX by a script

The probe kit behind `docs/design.md` §9.1 (2026-10-01): `make.py` writes a manifest and a PPTX
whose slides embed a probe add-in (`probe.html`), `server.py` logs what the add-in instances
report, `drive*.ps1` run the slideshow in PowerPoint over COM. Kept for reference; to rerun it,
put `probe.html` into a `www/` folder next to `server.py` and register `manifest.xml` under
`HKCU\Software\Microsoft\Office\16.0\WEF\Developer`.
