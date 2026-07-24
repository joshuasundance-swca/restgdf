"""W1-8 (CICD-02): red-first tests for the bumpver CHANGELOG fail-fast guard.

``scripts/bumpver_stamp_date.py`` runs as bumpver's ``pre_commit_hook``
between file-pattern substitution and the release commit. Per the
recorded maintainer decision (fail-fast-ONLY — no ``## [Unreleased]``
consolidation/rename), it now also fails the hook when ``CHANGELOG.md``'s
``## [Unreleased]`` section has no non-blank body, so an empty-Unreleased
release can no longer ship silently.

The script is loaded fresh per-test by file path (``scripts/`` has no
``__init__.py`` and is not an importable package) and its module-level
path constants are monkeypatched to an isolated ``tmp_path`` "repo root"
so no test ever reads or writes the real ``CHANGELOG.md``/``CITATION.cff``.
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
    return module


def _write_changelog(tmp_path: Path, unreleased_body: str) -> Path:
    text = (
        "# Changelog\n\n"
        "## [Unreleased]\n"
        f"{unreleased_body}"
        "## [1.0.0] - 2026-01-01\n"
        "- Initial release.\n"
    )
    path = tmp_path / "CHANGELOG.md"
    path.write_text(text, encoding="utf-8")
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
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)  # nosec B603 B607


class TestUnreleasedSectionBody:
    """Pure-parsing coverage for ``_unreleased_section_body`` — no file I/O."""

    def test_populated_section_returns_full_body(self, script: ModuleType) -> None:
        text = "## [Unreleased]\n### Fixed\n\n- A real fix.\n\n## [1.0.0]\n- x\n"

        body = script._unreleased_section_body(text)

        assert body is not None
        assert "A real fix" in body
        assert "## [1.0.0]" not in body

    def test_empty_section_returns_blank_body(self, script: ModuleType) -> None:
        text = "## [Unreleased]\n## [1.0.0]\n- x\n"

        body = script._unreleased_section_body(text)

        assert body is not None
        assert body.strip() == ""

    def test_whitespace_only_section_returns_blank_body(self, script: ModuleType) -> None:
        text = "## [Unreleased]\n\n   \n\n## [1.0.0]\n- x\n"

        body = script._unreleased_section_body(text)

        assert body is not None
        assert body.strip() == ""

    def test_missing_header_returns_none(self, script: ModuleType) -> None:
        text = "## [1.0.0]\n- x\n"

        assert script._unreleased_section_body(text) is None

    def test_unreleased_at_end_of_file_returns_full_remainder(
        self, script: ModuleType,
    ) -> None:
        text = "## [Unreleased]\n### Added\n\n- Only entry, no version header after.\n"

        body = script._unreleased_section_body(text)

        assert body is not None
        assert "Only entry" in body

    def test_does_not_mis_parse_a_triple_hash_subsection_as_a_version_header(
        self, script: ModuleType,
    ) -> None:
        """A populated section containing ``### Added``/``### Fixed`` subsections
        must not be truncated early by the next-header search (guards against the
        risk named in plan/01 W1-8: 'an awk pattern that mis-parses a legitimately
        populated section blocks a real release')."""
        text = (
            "## [Unreleased]\n"
            "### Added\n\n- Item one.\n\n"
            "### Fixed\n\n- Item two.\n\n"
            "## [1.0.0]\n- old\n"
        )

        body = script._unreleased_section_body(text)

        assert body is not None
        assert "Item one" in body
        assert "Item two" in body
        assert "old" not in body


class TestCheckChangelogUnreleasedPopulated:
    """File-reading wrapper: ``_check_changelog_unreleased_populated``."""

    def test_empty_unreleased_section_fails(
        self,
        script: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_changelog(tmp_path, unreleased_body="")

        status = script._check_changelog_unreleased_populated()

        assert status != 0
        err = capsys.readouterr().err
        assert "Unreleased" in err

    def test_whitespace_only_unreleased_section_fails(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        _write_changelog(tmp_path, unreleased_body="\n   \n\n")

        status = script._check_changelog_unreleased_populated()

        assert status != 0

    def test_populated_unreleased_section_passes(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        _write_changelog(
            tmp_path,
            unreleased_body="### Fixed\n\n- Something real got fixed.\n\n",
        )

        status = script._check_changelog_unreleased_populated()

        assert status == 0

    def test_missing_unreleased_header_fails(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        path = tmp_path / "CHANGELOG.md"
        path.write_text(
            "# Changelog\n\n## [1.0.0] - 2026-01-01\n- Initial release.\n",
            encoding="utf-8",
        )

        status = script._check_changelog_unreleased_populated()

        assert status != 0

    def test_missing_changelog_file_fails(self, script: ModuleType) -> None:
        status = script._check_changelog_unreleased_populated()

        assert status != 0


class TestMainOrdering:
    """``main()`` runs the CHANGELOG guard first and short-circuits on failure."""

    def test_main_fails_fast_and_never_touches_citation_cff(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        _write_changelog(tmp_path, unreleased_body="")
        # Deliberately no CITATION.cff at all: if the guard did not run
        # first, main() would instead fail with the (different) "CITATION.cff
        # not found" error -- proving the ordering, not just "some" failure.
        assert not (tmp_path / "CITATION.cff").exists()

        exit_code = script.main()

        assert exit_code != 0
        assert not (tmp_path / "CITATION.cff").exists()

    def test_main_fails_fast_even_when_citation_cff_would_otherwise_succeed(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        _write_changelog(tmp_path, unreleased_body="")
        citation = _write_citation_cff(tmp_path)
        before = citation.read_text(encoding="utf-8")

        exit_code = script.main()

        assert exit_code != 0
        # CITATION.cff must be untouched -- the changelog guard ran before
        # any write.
        assert citation.read_text(encoding="utf-8") == before


class TestCitationCffStampUnaffected:
    """Existing CITATION.cff date-stamp behavior is unchanged by the new guard."""

    def test_main_stamps_date_when_changelog_is_populated(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        _init_git_repo(tmp_path)
        _write_changelog(
            tmp_path,
            unreleased_body="### Fixed\n\n- A real fix.\n\n",
        )
        citation = _write_citation_cff(tmp_path, date="2020-01-01")

        exit_code = script.main()

        assert exit_code == 0
        rewritten = citation.read_text(encoding="utf-8")
        assert '"2020-01-01"' not in rewritten
        assert "date-released:" in rewritten

    def test_main_still_fails_on_malformed_citation_cff_when_changelog_is_populated(
        self, script: ModuleType, tmp_path: Path,
    ) -> None:
        _write_changelog(
            tmp_path,
            unreleased_body="### Fixed\n\n- A real fix.\n\n",
        )
        citation = tmp_path / "CITATION.cff"
        citation.write_text("cff-version: 1.2.0\nversion: 1.0.0\n", encoding="utf-8")

        exit_code = script.main()

        assert exit_code == 2
