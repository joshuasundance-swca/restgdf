"""restgdf v2.0.0 version contract."""

from __future__ import annotations

import sys
from pathlib import Path

import restgdf

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - fallback for 3.9/3.10
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]


def test_version_is_v2() -> None:
    assert restgdf.__version__ == "2.0.0"


def test_version_matches_pyproject() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == restgdf.__version__
    assert pyproject["tool"]["bumpver"]["current_version"] == restgdf.__version__
