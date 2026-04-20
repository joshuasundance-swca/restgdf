"""Tests for :mod:`restgdf.compat` migration helpers."""

from __future__ import annotations

from pydantic import BaseModel, SecretStr

from restgdf import AGOLUserPass, CrawlError, LayerMetadata
from restgdf.compat import as_dict, as_json_dict


def test_as_dict_basemodel_returns_plain_dict() -> None:
    md = LayerMetadata(name="layer0", maxRecordCount=1000)
    result = as_dict(md)
    assert isinstance(result, dict)
    assert result["name"] == "layer0"
    assert result["max_record_count"] == 1000


def test_as_dict_uses_snake_case_keys() -> None:
    md = LayerMetadata.model_validate(
        {"name": "n", "supportsPagination": True},
    )
    result = as_dict(md)
    assert "supports_pagination" in result
    assert "supportsPagination" not in result


def test_as_dict_passes_through_dict_unchanged() -> None:
    payload = {"name": "layer", "id": 1}
    assert as_dict(payload) is payload


def test_as_dict_passes_through_none() -> None:
    assert as_dict(None) is None


def test_as_dict_passes_through_primitives() -> None:
    for value in (1, 1.5, "hello", True, False):
        assert as_dict(value) == value


def test_as_dict_passes_through_list() -> None:
    items = [1, 2, 3]
    assert as_dict(items) is items


def test_as_dict_handles_crawl_error_with_exception() -> None:
    err = CrawlError(stage="service_metadata", url="http://x/0", message="boom")
    result = as_dict(err)
    assert result["stage"] == "service_metadata"
    assert result["message"] == "boom"


def test_as_json_dict_basemodel_returns_json_safe() -> None:
    md = LayerMetadata(name="layer0")
    result = as_json_dict(md)
    assert isinstance(result, dict)
    assert result["name"] == "layer0"


def test_as_json_dict_redacts_secret_str() -> None:
    creds = AGOLUserPass(username="u", password=SecretStr("supersecret"))
    result = as_json_dict(creds)
    assert isinstance(result, dict)
    # SecretStr serialises to a placeholder in json mode, not the raw value
    assert result["password"] != "supersecret"


def test_as_json_dict_passes_through_dict() -> None:
    payload = {"a": 1}
    assert as_json_dict(payload) is payload


def test_as_json_dict_passes_through_none_and_primitives() -> None:
    assert as_json_dict(None) is None
    assert as_json_dict(42) == 42
    assert as_json_dict("s") == "s"


def test_compat_submodule_import_path() -> None:
    from restgdf.compat import as_dict as imported_as_dict
    from restgdf.compat import as_json_dict as imported_as_json

    assert callable(imported_as_dict)
    assert callable(imported_as_json)


def test_compat_attached_to_package() -> None:
    import restgdf

    assert restgdf.compat.as_dict is as_dict
    assert restgdf.compat.as_json_dict is as_json_dict


def test_as_dict_generic_basemodel_subclass() -> None:
    class Tiny(BaseModel):
        x: int

    result = as_dict(Tiny(x=7))
    assert result == {"x": 7}
