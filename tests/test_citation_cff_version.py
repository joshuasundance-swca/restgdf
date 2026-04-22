"""BL-40 + Q-A14: ``CITATION.cff`` version must match ``restgdf.__version__``.

``CITATION.cff`` is machine-edited by ``bumpver`` (see
``[tool.bumpver.file_patterns]`` in ``pyproject.toml``), so the version
line follows a predictable ``version: X.Y.Z`` shape. Per plan.md §4
line 317 and MASTER-PLAN BL-40 (line 184), a minimal regex parser is
acceptable — we deliberately do NOT depend on ``PyYAML`` to keep the
test matrix zero-new-deps.
"""

from __future__ import annotations

import re
from pathlib import Path

import restgdf

_CFF_VERSION_RE = re.compile(
    r"^\s*version:\s*(?P<version>\S+?)\s*$",
    re.MULTILINE,
)


def _read_citation_cff_version() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / "CITATION.cff").read_text(encoding="utf-8")
    match = _CFF_VERSION_RE.search(text)
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
