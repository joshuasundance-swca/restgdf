"""S-4: Pydantic models for the ``safe_crawl`` report.

These tests pin the public contract of :class:`CrawlError`,
:class:`CrawlServiceEntry`, and :class:`CrawlReport` — permissive
models returned by :func:`restgdf.utils.crawl.safe_crawl`.

Contract points:

* All three are :class:`PermissiveModel` subclasses: extras are kept,
  missing optional fields default to ``None`` / empty lists rather
  than raise.
* :class:`CrawlError.exception` accepts arbitrary
  :class:`BaseException` instances (``arbitrary_types_allowed``) and is
  excluded from the default :meth:`~pydantic.BaseModel.model_dump`
  output so the report stays JSON-serializable.
* :class:`CrawlReport` round-trips nested lists of the other two models.
* Unknown extras on :class:`CrawlServiceEntry` trigger a
  drift-adapter DEBUG log, never a validation error.
"""

from __future__ import annotations

import logging

import pytest

from restgdf._models import CrawlError, CrawlReport, CrawlServiceEntry
from restgdf._models._drift import (
    PermissiveModel,
    _parse_response,
    reset_drift_cache,
)
from restgdf._models.responses import LayerMetadata


@pytest.fixture(autouse=True)
def _reset_drift_cache() -> None:
    reset_drift_cache()


# --------------------------------------------------------------------------- #
# Tier                                                                        #
# --------------------------------------------------------------------------- #


def test_crawl_error_is_permissive_subclass() -> None:
    assert issubclass(CrawlError, PermissiveModel)


def test_crawl_service_entry_is_permissive_subclass() -> None:
    assert issubclass(CrawlServiceEntry, PermissiveModel)


def test_crawl_report_is_permissive_subclass() -> None:
    assert issubclass(CrawlReport, PermissiveModel)


# --------------------------------------------------------------------------- #
# Forgiving validation                                                        #
# --------------------------------------------------------------------------- #


def test_crawl_error_accepts_empty_payload_without_raising() -> None:
    err = CrawlError.model_validate({})
    assert err.stage is None
    assert err.url is None
    assert err.message is None
    assert err.exception is None


def test_crawl_service_entry_accepts_empty_payload_without_raising() -> None:
    entry = CrawlServiceEntry.model_validate({})
    assert entry.name is None
    assert entry.url is None
    assert entry.metadata is None


def test_crawl_report_accepts_empty_payload_and_defaults_lists() -> None:
    report = CrawlReport.model_validate({})
    assert report.services == []
    assert report.errors == []
    assert report.metadata is None


# --------------------------------------------------------------------------- #
# Construction / round-trip                                                   #
# --------------------------------------------------------------------------- #


def test_crawl_error_round_trip_preserves_stage_url_message() -> None:
    err = CrawlError(
        stage="service_metadata",
        url="https://example.com/arcgis/rest/services/S/FeatureServer",
        message="boom",
    )
    dumped = err.model_dump(exclude_none=True)
    assert dumped == {
        "stage": "service_metadata",
        "url": "https://example.com/arcgis/rest/services/S/FeatureServer",
        "message": "boom",
    }


def test_crawl_error_preserves_exception_attribute_but_excludes_from_dump() -> None:
    boom = RuntimeError("boom")
    err = CrawlError(stage="base_metadata", url="u", message="boom", exception=boom)
    assert err.exception is boom
    dumped = err.model_dump()
    assert "exception" not in dumped


def test_crawl_error_exception_preserves_arbitrary_base_exception_subclass() -> None:
    class _Custom(BaseException):
        pass

    boom = _Custom("weird")
    err = CrawlError(exception=boom)
    assert err.exception is boom


def test_crawl_service_entry_round_trip() -> None:
    entry = CrawlServiceEntry(
        name="Root/Parcels",
        url="https://example.com/arcgis/rest/services/Root/Parcels/FeatureServer",
        type="FeatureServer",
    )
    dumped = entry.model_dump(exclude_none=True)
    assert dumped["name"] == "Root/Parcels"
    assert dumped["url"].endswith("/FeatureServer")
    assert dumped["type"] == "FeatureServer"


def test_crawl_service_entry_accepts_nested_metadata_as_layer_metadata() -> None:
    entry = CrawlServiceEntry.model_validate(
        {
            "name": "S",
            "url": "https://example.com/S/FeatureServer",
            "metadata": {"name": "Root", "maxRecordCount": 1000},
        },
    )
    assert isinstance(entry.metadata, LayerMetadata)
    assert entry.metadata.name == "Root"
    assert entry.metadata.max_record_count == 1000


def test_crawl_report_round_trip_with_nested_lists() -> None:
    report = CrawlReport(
        services=[
            CrawlServiceEntry(name="A", url="https://ex/A"),
            CrawlServiceEntry(name="B", url="https://ex/B"),
        ],
        errors=[
            CrawlError(stage="service_metadata", url="https://ex/B", message="nope"),
        ],
        metadata=LayerMetadata(name="Root"),
    )
    assert [svc.name for svc in report.services] == ["A", "B"]
    assert report.errors[0].stage == "service_metadata"
    assert isinstance(report.metadata, LayerMetadata)
    assert report.metadata.name == "Root"


def test_crawl_report_round_trips_through_model_validate_dict() -> None:
    raw = {
        "services": [
            {"name": "A", "url": "https://ex/A"},
            {
                "name": "B",
                "url": "https://ex/B",
                "metadata": {"name": "LayerB"},
            },
        ],
        "errors": [
            {"stage": "service_metadata", "url": "https://ex/C", "message": "boom"},
        ],
        "metadata": {"name": "Root", "folders": ["Utils"]},
    }
    report = CrawlReport.model_validate(raw)
    assert isinstance(report.services[0], CrawlServiceEntry)
    assert isinstance(report.services[1].metadata, LayerMetadata)
    assert report.services[1].metadata.name == "LayerB"
    assert isinstance(report.errors[0], CrawlError)
    assert isinstance(report.metadata, LayerMetadata)
    assert report.metadata.folders == ["Utils"]


# --------------------------------------------------------------------------- #
# Extras preserved                                                            #
# --------------------------------------------------------------------------- #


def test_crawl_service_entry_preserves_unknown_extras() -> None:
    entry = CrawlServiceEntry.model_validate(
        {"name": "S", "url": "https://ex/S", "serverGen": 17},
    )
    dumped = entry.model_dump(exclude_none=True)
    assert dumped.get("serverGen") == 17


# --------------------------------------------------------------------------- #
# Drift logging for unknown extras via _parse_response                        #
# --------------------------------------------------------------------------- #


def test_parse_response_crawl_service_entry_logs_unknown_extras_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    _parse_response(
        CrawlServiceEntry,
        {"name": "S", "url": "https://ex/S", "mysteryKey": "?"},
        context="safe_crawl",
    )
    drift_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and "mysteryKey" in r.getMessage()
    ]
    assert drift_records, "expected DEBUG drift log for unknown extra"


# --------------------------------------------------------------------------- #
# Re-export                                                                   #
# --------------------------------------------------------------------------- #


def test_models_package_reexports_crawl_models() -> None:
    import restgdf._models as m

    assert m.CrawlError is CrawlError
    assert m.CrawlServiceEntry is CrawlServiceEntry
    assert m.CrawlReport is CrawlReport
