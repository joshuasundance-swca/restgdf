"""W1-8b: red-first tests for the bumpver release-section fail-fast guard.

``scripts/bumpver_stamp_date.py`` runs as bumpver's ``pre_commit_hook``
between file-pattern substitution and the release commit — i.e. AFTER
``[tool.bumpver] current_version`` has been rewritten to the new version.

Composing the shipped W1-8 guard (require non-empty ``## [Unreleased]``
at bump time) with the W1-4 publish gate (require a non-empty
``## [X.Y.Z]`` section at tag time) deadlocks every release: bumpver
never rewrites the CHANGELOG, so pre-consolidating starves the bump gate
and not consolidating starves the publish gate. Per the fail-fast-only
maintainer decision (no consolidation logic in the hook), the guard now
asserts the thing the release actually needs: the JUST-BUMPED version's
own ``## [{version}]`` section exists with a non-blank body. The intended
flow becomes: consolidate ``[Unreleased]`` -> ``[X.Y.Z]`` in a release-prep
PR, then dispatch bumpver. A bump without a populated release section
fails fast with an actionable message — which still (more directly than
before) blocks the 3.0.0-class empty-section ship.

The script is loaded fresh per-test by file path (``scripts/`` has no
``__init__.py``) and its module-level path constants are monkeypatched to
an isolated ``tmp_path`` "repo root" so no test ever reads or writes the
real ``CHANGELOG.md``/``CITATION.cff``/``pyproject.toml``.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404 - test-only, used to init a throwaway tmp_path repo
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bumpver_stamp_date.py"


def _load_module() -> ModuleType:
    """Load a fresh copy of the script module for each test."""
    spec = importlib.util.spec_from_file_location(
        "bumpver_stamp_date_under_test",
        _SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A freshly loaded script module pointed at an isolated tmp_path "repo root"."""
    module = _load_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "_CITATION_CFF", tmp_path / "CITATION.cff")
    monkeypatch.setattr(module, "_CHANGELOG_MD", tmp_path / "CHANGELOG.md")
    # raising=False: against the pre-W1-8b script this attribute does not
    # exist yet — the red state fails inside test bodies (missing seam),
    # not at fixture setup.
    monkeypatch.setattr(
        module,
        "_PYPROJECT_TOML",
        tmp_path / "pyproject.toml",
        raising=False,
    )
    return module


def _write_pyproject(tmp_path: Path, *, version: str = "3.1.0") -> Path:
    """A minimal post-file_patterns pyproject: current_version already bumped."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
        f'[tool.bumpver]\ncurrent_version = "{version}"\n',
        encoding="utf-8",
    )
    return path


def _write_changelog(
    tmp_path: Path,
    *,
    unreleased_body: str = "",
    release_header: str | None = None,
    release_body: str = "",
) -> Path:
    """Build a CHANGELOG with an Unreleased section, an optional release
    section (header given verbatim, e.g. ``## [3.1.0] - 2026-07-24``), and
    a fixed 1.0.0 tail."""
    parts = ["# Changelog\n\n", "## [Unreleased]\n", unreleased_body]
    if release_header is not None:
        parts += [f"{release_header}\n", release_body]
    parts += ["## [1.0.0] - 2026-01-01\n", "- Initial release.\n"]
    path = tmp_path / "CHANGELOG.md"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _write_citation_cff(tmp_path: Path, *, date: str = "2020-01-01") -> Path:
    path = tmp_path / "CITATION.cff"
    path.write_text(
        f'cff-version: 1.2.0\ndate-released: "{date}"\nversion: 1.0.0\n',
        encoding="utf-8",
    )
    return path


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)  # nosec B603 B607
    subprocess.run(  # nosec B603 B607
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
    )  # nosec B603 B607


class TestReleaseSectionBody:
    """Pure-parsing coverage for ``_release_section_body`` — no file I/O."""

    def test_populated_dated_section_returns_full_body(
        self,
        script: ModuleType,
    ) -> None:
        text = (
            "## [Unreleased]\n\n"
            "## [3.1.0] - 2026-07-24\n### Fixed\n\n- A real fix.\n\n"
            "## [1.0.0]\n- x\n"
        )

        body = script._release_section_body(text, "3.1.0")

        assert body is not None
        assert "A real fix" in body
        assert "## [1.0.0]" not in body

    def test_bare_undated_header_also_matches(self, script: ModuleType) -> None:
        text = "## [3.1.0]\n- Something.\n## [1.0.0]\n- x\n"

        body = script._release_section_body(text, "3.1.0")

        assert body is not None
        assert "Something" in body

    def test_empty_section_returns_blank_body(self, script: ModuleType) -> None:
        text = "## [3.1.0] - 2026-07-24\n## [1.0.0]\n- x\n"

        body = script._release_section_body(text, "3.1.0")

        assert body is not None
        assert body.strip() == ""

    def test_missing_version_header_returns_none(self, script: ModuleType) -> None:
        text = "## [Unreleased]\n- Pending.\n## [1.0.0]\n- x\n"

        assert script._release_section_body(text, "3.1.0") is None

    def test_version_dots_are_not_regex_wildcards(self, script: ModuleType) -> None:
        """``3.1.0`` must not match a ``3x1x0``-style header (dot-metachar trap
        — the same class of bug the W1-4 verify found in the plan's awk)."""
        text = "## [3x1x0] - 2026-07-24\n- decoy\n## [1.0.0]\n- x\n"

        assert script._release_section_body(text, "3.1.0") is None

    def test_section_at_end_of_file_returns_remainder(
        self,
        script: ModuleType,
    ) -> None:
        text = "## [3.1.0] - 2026-07-24\n### Added\n\n- Only entry.\n"

        body = script._release_section_body(text, "3.1.0")

        assert body is not None
        assert "Only entry" in body

    def test_triple_hash_subsections_do_not_truncate_the_body(
        self,
        script: ModuleType,
    ) -> None:
        text = (
            "## [3.1.0] - 2026-07-24\n"
            "### Added\n\n- Item one.\n\n"
            "### Fixed\n\n- Item two.\n\n"
            "## [1.0.0]\n- old\n"
        )

        body = script._release_section_body(text, "3.1.0")

        assert body is not None
        assert "Item one" in body
        assert "Item two" in body
        assert "old" not in body


class TestCheckChangelogReleaseSectionPopulated:
    """File-reading wrapper: ``_check_changelog_release_section_populated``."""

    def test_populated_release_section_passes(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="### Fixed\n\n- Something real got fixed.\n\n",
        )

        assert script._check_changelog_release_section_populated() == 0

    def test_missing_release_section_fails_with_consolidation_hint(
        self,
        script: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Populated Unreleased but no ## [3.1.0] section: the pre-W1-8b
        guard passed this state, and the publish gate then failed AFTER the
        tag was pushed. It must now fail at the bump with an actionable
        message."""
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(tmp_path, unreleased_body="- Pending entry.\n")

        status = script._check_changelog_release_section_populated()

        assert status == 6
        err = capsys.readouterr().err
        assert "3.1.0" in err
        assert "consolidat" in err.lower()

    def test_empty_release_section_fails(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(
            tmp_path,
            unreleased_body="- Pending.\n",
            release_header="## [3.1.0] - 2026-07-24",
            release_body="",
        )

        assert script._check_changelog_release_section_populated() == 7

    def test_whitespace_only_release_section_fails(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="\n   \n\n",
        )

        assert script._check_changelog_release_section_populated() == 7

    def test_missing_changelog_file_fails(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")

        assert script._check_changelog_release_section_populated() == 5

    def test_missing_pyproject_fails(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="- Real.\n",
        )

        assert script._check_changelog_release_section_populated() == 8

    def test_pyproject_without_bumpver_version_fails(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\n',
            encoding="utf-8",
        )
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="- Real.\n",
        )

        assert script._check_changelog_release_section_populated() == 8


class TestMainOrdering:
    """``main()`` runs the CHANGELOG guard first and short-circuits on failure."""

    def test_main_fails_fast_and_never_touches_citation_cff(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="",
        )
        # Deliberately no CITATION.cff at all: if the guard did not run
        # first, main() would instead fail with the (different) "CITATION.cff
        # not found" error -- proving the ordering, not just "some" failure.
        assert not (tmp_path / "CITATION.cff").exists()

        exit_code = script.main()

        assert exit_code == 7
        assert not (tmp_path / "CITATION.cff").exists()

    def test_main_fails_fast_even_when_citation_cff_would_otherwise_succeed(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(tmp_path, unreleased_body="- Pending.\n")
        citation = _write_citation_cff(tmp_path)
        before = citation.read_text(encoding="utf-8")

        exit_code = script.main()

        assert exit_code == 6
        # CITATION.cff must be untouched -- the changelog guard ran before
        # any write.
        assert citation.read_text(encoding="utf-8") == before


class TestCitationCffStampUnaffected:
    """Existing CITATION.cff date-stamp behavior is unchanged by the new guard."""

    def test_main_stamps_date_when_release_section_is_populated(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _init_git_repo(tmp_path)
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="### Fixed\n\n- A real fix.\n\n",
        )
        citation = _write_citation_cff(tmp_path, date="2020-01-01")

        exit_code = script.main()

        assert exit_code == 0
        rewritten = citation.read_text(encoding="utf-8")
        assert '"2020-01-01"' not in rewritten
        assert "date-released:" in rewritten

    def test_main_still_fails_on_malformed_citation_cff_when_guard_passes(
        self,
        script: ModuleType,
        tmp_path: Path,
    ) -> None:
        _write_pyproject(tmp_path, version="3.1.0")
        _write_changelog(
            tmp_path,
            release_header="## [3.1.0] - 2026-07-24",
            release_body="### Fixed\n\n- A real fix.\n\n",
        )
        citation = tmp_path / "CITATION.cff"
        citation.write_text("cff-version: 1.2.0\nversion: 1.0.0\n", encoding="utf-8")

        exit_code = script.main()

        assert exit_code == 2
