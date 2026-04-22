"""BL-40 + Q-A14: ``CITATION.cff`` drift guards.

``CITATION.cff`` is machine-edited by ``bumpver`` — the ``version:`` line
via ``[tool.bumpver.file_patterns]`` and the ``date-released:`` line via
the ``pre_commit_hook`` script at ``scripts/bumpver_stamp_date.py``. Both
fields follow predictable shapes, so a minimal regex parser is
acceptable — we deliberately do NOT depend on ``PyYAML`` to keep the
test matrix zero-new-deps (per plan.md §4 line 317 and MASTER-PLAN
BL-40 line 184).
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

import restgdf

_CFF_VERSION_RE = re.compile(
    r"^\s*version:\s*(?P<version>\S+?)\s*$",
    re.MULTILINE,
)
_CFF_DATE_RELEASED_RE = re.compile(
    r'^\s*date-released:\s*"(?P<date>\d{4}-\d{2}-\d{2})"\s*$',
    re.MULTILINE,
)


def _read_citation_cff() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / "CITATION.cff").read_text(encoding="utf-8")


def _read_citation_cff_version() -> str:
    match = _CFF_VERSION_RE.search(_read_citation_cff())
    assert match is not None, "CITATION.cff must define a top-level `version:` key"
    return match.group("version").strip("\"'")


def test_citation_cff_version_matches_package_version() -> None:
    cff_version = _read_citation_cff_version()
    assert cff_version == restgdf.__version__, (
        f"CITATION.cff version ({cff_version!r}) must match "
        f"restgdf.__version__ ({restgdf.__version__!r}). Check that "
        "`bumpver update` rewrote CITATION.cff (see "
        "[tool.bumpver.file_patterns] in pyproject.toml)."
    )


def test_citation_cff_date_released_is_iso_8601() -> None:
    """``date-released`` must be a valid ``YYYY-MM-DD`` date.

    Stamped at release time by ``scripts/bumpver_stamp_date.py`` via
    bumpver's ``pre_commit_hook``. This guard catches hand-edit typos
    (e.g. ``2026-13-01``) and reassures downstream citation tooling
    (Zenodo, CFF validators) that the field is well-formed.
    """
    match = _CFF_DATE_RELEASED_RE.search(_read_citation_cff())
    assert match is not None, (
        'CITATION.cff must define `date-released: "YYYY-MM-DD"` (quoted, '
        "ISO 8601). See scripts/bumpver_stamp_date.py for the bumpver hook "
        "that keeps this field in sync."
    )
    try:
        _dt.date.fromisoformat(match.group("date"))
    except ValueError as exc:  # pragma: no cover - defensive
        raise AssertionError(
            f"CITATION.cff `date-released` is not a valid ISO 8601 date: {exc}",
        ) from exc
