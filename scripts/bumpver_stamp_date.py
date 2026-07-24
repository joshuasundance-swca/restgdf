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

1. **CHANGELOG fail-fast (CICD-02 / W1-8, fail-fast-only per maintainer
   decision):** read ``CHANGELOG.md`` and exit non-zero if the
   ``## [Unreleased]`` section has no non-blank body. This is a hard
   assertion only — it does NOT rename ``## [Unreleased]`` or otherwise
   consolidate the changelog (that would be the heavier option the
   maintainer decision explicitly declined). Runs first, before touching
   ``CITATION.cff``, so a rejected release leaves no partial file writes.
2. Rewrites the ``date-released:`` line in ``CITATION.cff`` with today's
   UTC date (ISO 8601, ``YYYY-MM-DD``) and ``git add``s the file so
   bumpver's subsequent commit picks up the change.

Exits non-zero if ``CHANGELOG.md`` has no populated ``## [Unreleased]``
section, or if ``CITATION.cff`` does not contain exactly one
``date-released:`` line (which would indicate the file has drifted from
the shape ``tests/test_citation_cff_version.py`` expects).
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import re
import shutil
import subprocess  # nosec B404 - used only to `git add` the file we just rewrote
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CITATION_CFF = _REPO_ROOT / "CITATION.cff"
_CHANGELOG_MD = _REPO_ROOT / "CHANGELOG.md"
_DATE_RELEASED_RE = re.compile(
    r'^(?P<prefix>date-released:\s*)"\d{4}-\d{2}-\d{2}"\s*$',
    re.MULTILINE,
)
_UNRELEASED_HEADER_RE = re.compile(r"^## \[Unreleased\]\s*$", re.MULTILINE)
_NEXT_VERSION_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)


def _today_utc_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).date().isoformat()


def _unreleased_section_body(text: str) -> str | None:
    """Return the raw text between ``## [Unreleased]`` and the next
    ``## [`` header (exclusive of both), or ``None`` if no
    ``## [Unreleased]`` header is present in ``text``.
    """
    header_match = _UNRELEASED_HEADER_RE.search(text)
    if header_match is None:
        return None
    start = header_match.end()
    next_match = _NEXT_VERSION_HEADER_RE.search(text, pos=start)
    end = next_match.start() if next_match is not None else len(text)
    return text[start:end]


def _check_changelog_unreleased_populated() -> int:
    """Fail fast (non-zero) when ``CHANGELOG.md``'s ``## [Unreleased]``
    section has no non-blank body.

    Mirrors the ``date-released`` guard's fail-fast discipline (clear
    stderr message, non-zero exit on any unexpected shape) rather than
    silently letting an empty-Unreleased release ship. This is a hard
    assertion ONLY: it never rewrites ``CHANGELOG.md`` (no auto-rename,
    no consolidation) per the recorded maintainer decision for W1-8.
    """
    if not _CHANGELOG_MD.is_file():
        print(f"[bumpver_stamp_date] {_CHANGELOG_MD} not found", file=sys.stderr)
        return 5

    text = _CHANGELOG_MD.read_text(encoding="utf-8")
    body = _unreleased_section_body(text)

    if body is None:
        print(
            '[bumpver_stamp_date] expected a "## [Unreleased]" header in '
            f"{_CHANGELOG_MD}; found none.",
            file=sys.stderr,
        )
        return 6

    if not body.strip():
        print(
            '[bumpver_stamp_date] the "## [Unreleased]" section in '
            f"{_CHANGELOG_MD} has no body. Add a changelog entry before "
            "bumping the version (see CONTRIBUTING.md).",
            file=sys.stderr,
        )
        return 7

    return 0


def main() -> int:
    changelog_status = _check_changelog_unreleased_populated()
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
