#!/usr/bin/env python3
"""bumpver ``pre_commit_hook``: stamp today's UTC date into ``CITATION.cff``.

Context
-------
``bumpver`` substitutes tokens that appear in ``version_pattern``. Our
``version_pattern = "MAJOR.MINOR.PATCH"`` (SemVer) has no date tokens, so
``[tool.bumpver.file_patterns]`` cannot substitute ``{YYYY}-{0M}-{0D}``
into ``CITATION.cff``. That leaves ``date-released`` as the one drift-prone
field bumpver can't touch via file_patterns alone.

Behaviour
---------
This hook runs between bumpver's file-pattern substitution step and its
commit step. It performs two independent checks/actions, in order:

1. **CHANGELOG fail-fast (CICD-02 / W1-8b, fail-fast-only per maintainer
   decision):** read the just-bumped version from ``pyproject.toml``
   (``[tool.bumpver] current_version`` — already rewritten by bumpver's
   file-pattern step when this hook runs) and exit non-zero unless
   ``CHANGELOG.md`` has a ``## [{version}]`` section with a non-blank
   body. This matches what the publish-time W1-4 gate will require at
   the tag, so a bump that would fail publish fails HERE instead —
   before any tag exists. Intended flow: consolidate ``[Unreleased]``
   into ``## [X.Y.Z]`` in a release-prep PR, then dispatch bumpver.
   This is a hard assertion only — it does NOT rename ``[Unreleased]``
   or otherwise consolidate the changelog (the heavier option the
   maintainer decision explicitly declined). Runs first, before touching
   ``CITATION.cff``, so a rejected release leaves no partial file writes.
2. Rewrites the ``date-released:`` line in ``CITATION.cff`` with today's
   UTC date (ISO 8601, ``YYYY-MM-DD``) and ``git add``s the file so
   bumpver's subsequent commit picks up the change.

Exits non-zero if the just-bumped version has no populated
``## [{version}]`` section in ``CHANGELOG.md``, if the version cannot be
read from ``pyproject.toml``, or if ``CITATION.cff`` does not contain
exactly one ``date-released:`` line (which would indicate the file has
drifted from the shape ``tests/test_citation_cff_version.py`` expects).
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import re
import shutil
import subprocess  # nosec B404 - used only to `git add` the file we just rewrote
import sys
import tomllib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CITATION_CFF = _REPO_ROOT / "CITATION.cff"
_CHANGELOG_MD = _REPO_ROOT / "CHANGELOG.md"
_PYPROJECT_TOML = _REPO_ROOT / "pyproject.toml"
_DATE_RELEASED_RE = re.compile(
    r'^(?P<prefix>date-released:\s*)"\d{4}-\d{2}-\d{2}"\s*$',
    re.MULTILINE,
)
_NEXT_VERSION_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)


def _today_utc_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).date().isoformat()


def _read_bumped_version() -> str | None:
    """Return ``[tool.bumpver] current_version`` from ``pyproject.toml``.

    The hook runs after bumpver's file-pattern substitution, so this is
    the NEW (just-bumped) version. ``None`` on any missing/unparseable
    shape — the caller turns that into a fail-fast exit.
    """
    try:
        with _PYPROJECT_TOML.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    version = data.get("tool", {}).get("bumpver", {}).get("current_version")
    return version if isinstance(version, str) and version else None


def _release_section_body(text: str, version: str) -> str | None:
    """Return the raw text between ``## [{version}]`` (with or without a
    trailing ``- <date>`` suffix) and the next ``## [`` header, or
    ``None`` if no such header is present. ``version`` is matched
    literally — dots are not regex wildcards.
    """
    header_re = re.compile(
        # [ \t]* (not \s*): \s matches newlines, which would let the
        # optional date suffix swallow the section's first body line
        # when the header is undated.
        rf"^## \[{re.escape(version)}\](?:[ \t]*-[^\n]*)?[ \t]*$",
        re.MULTILINE,
    )
    header_match = header_re.search(text)
    if header_match is None:
        return None
    start = header_match.end()
    next_match = _NEXT_VERSION_HEADER_RE.search(text, pos=start)
    end = next_match.start() if next_match is not None else len(text)
    return text[start:end]


def _check_changelog_release_section_populated() -> int:
    """Fail fast (non-zero) unless the just-bumped version's own
    ``## [{version}]`` section exists in ``CHANGELOG.md`` with a
    non-blank body.

    This asserts at BUMP time exactly what the publish-time W1-4 gate
    asserts at the tag, so a release that would fail publish fails here
    — before bumpver creates the release commit/tag. Mirrors the
    ``date-released`` guard's fail-fast discipline (clear stderr
    message, non-zero exit on any unexpected shape). This is a hard
    assertion ONLY: it never rewrites ``CHANGELOG.md`` (no auto-rename,
    no consolidation) per the recorded maintainer decision for W1-8.
    """
    if not _CHANGELOG_MD.is_file():
        print(f"[bumpver_stamp_date] {_CHANGELOG_MD} not found", file=sys.stderr)
        return 5

    version = _read_bumped_version()
    if version is None:
        print(
            "[bumpver_stamp_date] could not read [tool.bumpver] "
            f"current_version from {_PYPROJECT_TOML}.",
            file=sys.stderr,
        )
        return 8

    text = _CHANGELOG_MD.read_text(encoding="utf-8")
    body = _release_section_body(text, version)

    if body is None:
        print(
            f'[bumpver_stamp_date] expected a "## [{version}]" section in '
            f"{_CHANGELOG_MD}; found none. Consolidate the "
            f'"## [Unreleased]" entries into "## [{version}] - <date>" in '
            "a release-prep PR before dispatching the bump "
            "(see CONTRIBUTING.md).",
            file=sys.stderr,
        )
        return 6

    if not body.strip():
        print(
            f'[bumpver_stamp_date] the "## [{version}]" section in '
            f"{_CHANGELOG_MD} has no body. Populate it before bumping "
            "the version (see CONTRIBUTING.md).",
            file=sys.stderr,
        )
        return 7

    return 0


def main() -> int:
    changelog_status = _check_changelog_release_section_populated()
    if changelog_status != 0:
        return changelog_status

    if not _CITATION_CFF.is_file():
        print(f"[bumpver_stamp_date] {_CITATION_CFF} not found", file=sys.stderr)
        return 1

    text = _CITATION_CFF.read_text(encoding="utf-8")
    today = _today_utc_iso()
    new_text, n = _DATE_RELEASED_RE.subn(rf'\g<prefix>"{today}"', text)

    if n != 1:
        print(
            '[bumpver_stamp_date] expected exactly one `date-released: "..."` '
            f"line in {_CITATION_CFF}; found {n}.",
            file=sys.stderr,
        )
        return 2

    if new_text == text:
        return 0

    _CITATION_CFF.write_text(new_text, encoding="utf-8")

    git_exe = shutil.which("git")
    if git_exe is None:
        print(
            "[bumpver_stamp_date] git executable not found on PATH; "
            "CITATION.cff was rewritten but not staged.",
            file=sys.stderr,
        )
        return 4

    try:
        subprocess.run(  # nosec B603 - fixed argv, no shell, resolved git path
            [git_exe, "add", "--", str(_CITATION_CFF)],
            check=True,
            cwd=_REPO_ROOT,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[bumpver_stamp_date] git add failed: {exc}", file=sys.stderr)
        return 3

    print(f'[bumpver_stamp_date] stamped date-released: "{today}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
