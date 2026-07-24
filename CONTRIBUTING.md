# Contributing to restgdf

Thanks for your interest in restgdf! This document captures the local
workflow, commit conventions, and the gate suite contributors are
expected to run before opening a pull request against `main`.

See also:

- [ARCHITECTURE.md](ARCHITECTURE.md) — module layout, exception
  taxonomy, logger hierarchy, config precedence, streaming shapes,
  extras matrix.
- [CHANGELOG.md](CHANGELOG.md) — every user-visible change. Each PR
  that touches runtime behavior must add a bullet under the
  `## [Unreleased]` section in the appropriate subsection.
- [MIGRATION.md](MIGRATION.md) — for context on what 3.0 changes
  vs. 2.x.

## Quick start

```bash
python -m venv .venv
. .venv/Scripts/activate          # Windows
# . .venv/bin/activate            # macOS/Linux
python -m pip install --upgrade pip
python -m pip install -e ".[dev,resilience,telemetry,geo]"
python -m pre_commit install
```

`.[dev]` covers testing + linting + docs tooling + packaging (it
composes `restgdf[doc]` and adds `build`/`twine`); adding `resilience`,
`telemetry`, and `geo` gives you the full extras matrix locally. See
[ARCHITECTURE.md §Extras](ARCHITECTURE.md#extras-matrix) for the
trade-offs.

## Pull-request checklist

Before you open the PR, verify:

- [ ] Code compiles and imports cleanly (`python -c "import restgdf"`).
- [ ] `pre-commit run --all-files` is green.
- [ ] `pytest -m "not network"` is green locally.
- [ ] Coverage ≥ 97% (`coverage run -m pytest -m "not network" &&
      coverage report --fail-under=97`).
- [ ] Behavior-change PRs add a **red test first** (one commit that
      fails), then the fix (one commit that turns it green). Additive
      features ship tests alongside code in a single commit.
- [ ] `CHANGELOG.md` has a bullet under `## [Unreleased]` in the right
      subsection (`### Added` / `### Changed` → Breaking vs.
      Non-breaking / `### Deprecated` / `### Removed` / `### Fixed`).
- [ ] If you changed public APIs, Sphinx docs still build:
      `sphinx-build -n -W --keep-going -b html docs docs/_build/html`.
- [ ] If you changed anything shipped to PyPI, the wheel/sdist still
      build: `python -m build && python -m twine check --strict dist/*`.
- [ ] Legacy compat tests still pass: `pytest tests/test_compat.py`.
- [ ] Applied a PR label so GitHub's auto-generated release notes
      bucket the change correctly
      (see [`.github/release.yml`](.github/release.yml)): one of
      `breaking-change`, `enhancement`, `bug`, `documentation`,
      `testing`, `ci`, `dependencies`.

## Commit conventions

- Use **Conventional Commits** prefixes: `feat:`, `fix:`, `refactor:`,
  `test:`, `docs:`, `ci:`, `build:`, `chore:`.
- First line ≤ 72 characters, imperative mood.
- Body wrapped at ~72 columns. Explain *why* first, then *what*.
  Illustrative plan item IDs (e.g. `BL-46`) are welcome shorthand when a
  change traces to a specific backlog entry — no `plan.md`/backlog file
  ships in this repo, so treat the ID as context, not a cross-reference.
- Sign commits with `Co-authored-by:` trailers for any shared work.
- Keep each commit self-contained — each commit must pass the full
  gate suite on its own so `git bisect` stays useful.

### Red-first rule for behavior changes

Per the project plan, any PR that changes observable behavior (return
values, exception types, side-effects, default settings) must land the
failing test **in its own commit** *before* the fix. Additive features
(new APIs, new configs, new docs, new CI) may ship tests alongside the
implementation in a single commit.

## Gate suite (run before pushing)

All commands assume the project root and an activated venv (or invoke
`.venv\Scripts\python.exe` directly on Windows).

The gate suite below:

| # | Command                                                                                      | Purpose                                 |
|---|----------------------------------------------------------------------------------------------|-----------------------------------------|
| 1 | `python -m pytest -q -m "not network"`                                                       | Offline test suite (0 xfail regression) |
| 2 | `python -m coverage run -m pytest -q -m "not network" && python -m coverage report --fail-under=97` | Coverage floor ≥ 97%              |
| 3 | `python -m pre_commit run --all-files`                                                       | Linters / formatters / mypy             |
| 4 | `python -m sphinx -n -W --keep-going -b html docs docs/_build/html`                          | Docs build (warnings-as-errors)         |
| 5 | Base-install smoke: `pip install .` (no extras), then `from restgdf import FeatureLayer` and run a metadata/query path | Light-core contract (BL-38) |
| 6 | `python -m pytest -q tests/test_compat.py`                                                   | 2.x legacy patch-seam stays stable      |
| 7 | `python -m build && python -m twine check --strict dist/*`                                   | Packaging metadata sanity               |

On pull requests, CI (`pytest.yml`) re-runs gates 1–3, 5, and 6 (the offline
suite, the coverage floor, pre-commit, the base-install smoke, and the compat
suite). Gate 7's `build` + `twine check` also runs on packaging / `restgdf/**`
PRs via `publish_on_pypi.yml`, while the PyPI publish and Sigstore attestation
run only on the tagged release path. The docs build (gate 4) is verified by
Read the Docs. Running the gates locally still saves round-trips.

## Extras matrix

When adding a runtime dependency, think first about whether it belongs
in the core or behind an extra. restgdf ships with a deliberately thin
light core (`aiohttp`, `pydantic`) plus opt-in extras:

- `resilience` — `stamina`-based retry on transient network / HTTP 5xx.
- `telemetry` — OpenTelemetry tracing hooks.
- `geo` — `geopandas` / `pyogrio` GeoDataFrame conversion.
- `dev` — testing + linting + docs + packaging tooling (composes
  `restgdf[doc]`, adds `build`/`twine`; not shipped to end users).

Prefer `[extras]` over unconditional `install_requires` whenever a
feature is optional. See [ARCHITECTURE.md §Extras](ARCHITECTURE.md#extras-matrix).

## Reporting security issues

Please follow [SECURITY.md](SECURITY.md) — do **not** file a public
issue for vulnerability reports.

## Questions?

Open a discussion or a draft PR and tag @joshuasundance-swca. We read
every issue.
