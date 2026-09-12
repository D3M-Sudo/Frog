# Anura — Dependency and Flatpak workflow (current behaviour on `testing`)

This document is the **normative** reference for how Python dependencies flow
from declaration to Flatpak manifests and how automated dependency tooling is
split between workflows. Source of truth: `pyproject.toml`, `uv.lock`,
`build-aux/sync_dependencies.py`,
`build-aux/check_runtime_dependency_coverage.py`,
`build-aux/check_manifest_consistency.py`,
`build-aux/check_tessdata_consistency.py`, `.github/workflows/dependency-sync.yml`,
`.github/workflows/flatpak-dependencies.yml`, `.github/workflows/main.yml`,
`.github/dependabot.yml`, and `.github/scripts/fedc_certifi.py`.

## Pipeline

```text
pyproject.toml (direct deps)
      |
      v
uv.lock (resolved versions + dependency graph)
      |
      +---> build-aux/sync_dependencies.py --update/--check
      |         synchronises URL + sha256 of python3-* modules in BOTH
      |         flatpak/io.github.d3msudo.anura.json (release: git source)
      |         and flatpak/io.github.d3msudo.anura.local.json (local: dir source)
      |
      +---> build-aux/check_runtime_dependency_coverage.py (F-005)
                every runtime package in the uv.lock closure must have a
                python3-* module in BOTH manifests
```

Both Flatpak manifests are authoritative and must stay in sync. The only
intentional difference is the `anura` application module (`git` source in the
release manifest vs `dir` source in the local manifest). CI enforces this with
`build-aux/check_manifest_consistency.py`.

## Ownership boundaries

| Owner | Responsibility |
| --- | --- |
| `sync_dependencies.py` (+ `dependency-sync.yml`) | Version/URL/hash synchronisation of `python3-*` modules from `uv.lock`. **certifi is excluded here.** |
| FEDC (`flatpak-dependencies.yml` + `fedc_certifi.py`) | **Exclusive owner of `certifi`.** Discovers upstream certifi updates and applies them to **both** manifests. Build-only modules (`pybind11`, `scikit-build-core`) are FEDC/`x-checker-data`-managed, not `uv.lock`-managed. |
| `check_runtime_dependency_coverage.py` | Presence check: every runtime dependency must be represented in both manifests. For FEDC-owned `certifi`, presence is enforced but the version is never compared. |
| `check_manifest_consistency.py` | Drift check between the two manifests. |
| `check_tessdata_consistency.py` | Tessdata commit-SHA consistency between `anura/config.py` and both manifests. |
| Dependabot (`.github/dependabot.yml`) | Opens PRs against `testing` for `pip` and `github-actions` ecosystems. |

## FEDC / certifi workflow

1. The weekly `flatpak-dependencies.yml` run first checks all upstream Flatpak
   versions with flatpak-external-data-checker (FEDC) and reports general
   updates as a `dependencies`-labelled issue (no automatic manifest edits for
   general dependencies).
2. It then restores both manifests and runs an isolated certifi-only FEDC pass:
   `fedc_certifi.py isolate` builds a temporary manifest containing only the
   certifi source (adding the temporary `x-checker-data` FEDC metadata),
   FEDC updates it, and `fedc_certifi.py replace` copies the updated
   URL/checksum back into **both** manifests (stripping the temporary
   `x-checker-data`).
3. If the certifi update produces a diff, a `chore(deps): update certifi via
   FEDC` PR is opened against `testing` (branch `update-certifi`).

Consequences:

- `uv.lock` and Flatpak certifi versions may intentionally diverge; this is not
  drift.
- Never add certifi version management to `sync_dependencies.py`.
- The production manifests must never contain `x-checker-data` on the certifi
  source; that metadata exists only in the temporary FEDC manifest.

## Dependency-sync workflow (Dependabot PRs)

`dependency-sync.yml` triggers on PRs touching `pyproject.toml` (branches
`testing`, `development`) and on manual dispatch:

1. Regenerates `uv.lock` (`uv lock`).
2. Runs `sync_dependencies.py --update`, `--check`, and the F-005 coverage
   check.
3. Commits `uv.lock` + both manifests back to the Dependabot PR branch.

## Local verification

```bash
python3 build-aux/sync_dependencies.py --check
python3 build-aux/check_manifest_consistency.py
python3 build-aux/check_tessdata_consistency.py
python3 build-aux/check_runtime_dependency_coverage.py
```

## GTK (PyGObject) and the development venv

**Status: known environment constraint (documented 2026-09-12).**

PyGObject (`gi`) is **not installable in the project venv** and this is not
expected to change:

- PyGObject publishes **no binary wheels** on PyPI; it must always be compiled.
- Local build environments typically lack the required toolchain
  (`gcc`/`clang`, `pkg-config`, `gobject-introspection`/`girepository` dev
  headers, pycairo build deps), so `uv pip install pygobject` fails at the
  meson/pycairo build stage.
- Anura therefore relies on the **system-provided** `python3-gi` package (GTK
  typelibs come from the host or the Flatpak runtime) — the same model used by
  Flatpak builds, where `gi` is provided by the GNOME runtime.

### Testing GTK-dependent code without a display or venv `gi`

Headless verification of GTK-touching logic (accelerators, GAction
registration, template data) must run with the **system Python interpreter**:

```bash
SP=$(ls -d .venv/lib/python3.*/site-packages)
PYTHONPATH=".:$SP" /usr/bin/python3 script.py
```

- `PYTHONPATH` merges the repo root and the venv site-packages so that
  `anura` imports and pure-Python dependencies (e.g. `loguru`) resolve, while
  `gi` resolves from the system `python3-gi`.
- When importing `Gtk.Template`-based widgets headlessly, **register the
  compiled GResource first**:

  ```python
  with open("builddir/data/io.github.d3msudo.anura.gresource", "rb") as f:
      Gio.Resource.new_from_data(GLib.Bytes.new(f.read()))._register()
  ```

- GObject classes cannot be created via `object.__new__()`; to inspect
  instance methods without a display, call them unbound against a plain
  `types.SimpleNamespace()` stub (e.g.
  `ShortcutsOverlay._setup_shortcuts_data(SimpleNamespace())`).
- Note for PyGObject >= 3.48: `Gtk.accelerator_parse()` returns
  `(success, keyval, mods)` — three values, not two.
- `blueprint-compiler` on the host may lack runtime typelibs (e.g.
  `GtkSource-5`); point it at the Flatpak runtime GIR directory when needed:

  ```bash
  blueprint-compiler compile \
    --typelib-path /var/lib/flatpak/runtime/org.gnome.Platform/x86_64/<ver>/active/files/lib/x86_64-linux-gnu/girepository-1.0 \
    data/ui/<page>.blp
  ```

Reference implementation: the shortcuts-overlay vs `ActionRegistry`
accelerator consistency check (2026-09-12) validated this approach end to end.
