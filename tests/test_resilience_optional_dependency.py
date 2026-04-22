"""Tests for resilience optional dependency gating (BL-31, commit 1)."""

from __future__ import annotations

import sys

import pytest

from restgdf.errors import OptionalDependencyError


class TestResilienceOptionalDependency:
    def test_import_restgdf_without_resilience_extra(self) -> None:
        """Bare ``import restgdf`` and ``from restgdf import ResilienceConfig`` work."""
        import restgdf  # noqa: F401
        from restgdf import ResilienceConfig  # noqa: F401

    def test_resilience_import_raises_optional_dependency_error_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """import restgdf.resilience raises OptionalDependencyError when stamina missing."""
        # Remove cached module and sentinel-block stamina
        mods_to_remove = [k for k in sys.modules if k.startswith("restgdf.resilience")]
        for k in mods_to_remove:
            monkeypatch.delitem(sys.modules, k, raising=False)
        monkeypatch.setitem(sys.modules, "stamina", None)

        with pytest.raises(OptionalDependencyError) as exc_info:
            import importlib
            importlib.import_module("restgdf.resilience")

        assert isinstance(exc_info.value, ModuleNotFoundError)
        assert "pip install restgdf[resilience]" in str(exc_info.value)
