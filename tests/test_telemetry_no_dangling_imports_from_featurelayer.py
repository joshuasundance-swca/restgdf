"""R-61 atomicity guard: no production code imports feature_layer_stream_span.

This test is green on cf289dc (nothing imports the helper yet) and MUST
stay green after the implementation commit. It rides in the red commit
as a guard-test (R-61).
"""

from __future__ import annotations

import pathlib
import re

import pytest


_PRODUCTION_DIRS = [
    "restgdf/featurelayer",
    "restgdf/directory",
    "restgdf/adapters",
    "restgdf/_client",
]

_FORBIDDEN_PATTERN = re.compile(r"\bfeature_layer_stream_span\b")


def test_featurelayer_does_not_import_telemetry_helpers():
    """No production module imports feature_layer_stream_span (R-61)."""
    root = pathlib.Path(__file__).resolve().parent.parent
    violations: list[str] = []
    for dirpath in _PRODUCTION_DIRS:
        d = root / dirpath
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if _FORBIDDEN_PATTERN.search(text):
                violations.append(str(py.relative_to(root)))
    assert violations == [], (
        f"R-61 violation: feature_layer_stream_span imported in {violations}"
    )


def test_no_pytest_skip_waiting_on_phase_4a():
    """No test is marked @pytest.mark.skip with reason mentioning phase-4A."""
    root = pathlib.Path(__file__).resolve().parent.parent / "tests"
    skip_pattern = re.compile(
        r"@pytest\.mark\.skip.*(?:phase.?4A|iter_pages)", re.IGNORECASE
    )
    own_name = pathlib.Path(__file__).name
    violations: list[str] = []
    for py in root.glob("test_telemetry_*.py"):
        if py.name == own_name:
            continue  # exclude self (guard-test body mentions the pattern)
        text = py.read_text(encoding="utf-8")
        if skip_pattern.search(text):
            violations.append(py.name)
    assert violations == [], (
        f"R-61 violation: skip markers waiting on phase-4A in {violations}"
    )
