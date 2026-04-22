"""Class-identity contract for the RestgdfResponseError alias shim (BL-06)."""

from __future__ import annotations


def test_models_errors_shim_preserves_identity() -> None:
    from restgdf._models._errors import RestgdfResponseError as FromShim
    from restgdf.errors import RestgdfResponseError as Canonical

    assert FromShim is Canonical


def test_models_package_reexport_preserves_identity() -> None:
    from restgdf._models import RestgdfResponseError as FromPackage
    from restgdf.errors import RestgdfResponseError as Canonical

    assert FromPackage is Canonical


def test_top_level_reexport_preserves_identity() -> None:
    import restgdf
    from restgdf.errors import RestgdfResponseError as Canonical

    assert restgdf.RestgdfResponseError is Canonical


def test_shim_module_has_no_class_statement() -> None:
    import pathlib

    import restgdf._models._errors as shim

    source = pathlib.Path(shim.__file__).read_text(encoding="utf-8")
    # Pure alias shim: no class definition may remain.
    assert "class RestgdfResponseError" not in source
    assert "from restgdf.errors import RestgdfResponseError" in source
