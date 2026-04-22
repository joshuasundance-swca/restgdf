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
commit step. It rewrites the ``date-released:`` line in ``CITATION.cff``
with today's UTC date (ISO 8601, ``YYYY-MM-DD``) and ``git add``s the
file so bumpver's subsequent commit picks up the change.

Exits non-zero if ``CITATION.cff`` does not contain exactly one
``date-released:`` line, which would indicate the file has drifted from
the shape ``tests/test_citation_cff_version.py`` expects.
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
_DATE_RELEASED_RE = re.compile(
    r'^(?P<prefix>date-released:\s*)"\d{4}-\d{2}-\d{2}"\s*$',
    re.MULTILINE,
)


def _today_utc_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).date().isoformat()


def main() -> int:
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
