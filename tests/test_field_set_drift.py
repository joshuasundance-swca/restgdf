"""Tests for :class:`restgdf._models._drift.FieldSetDriftObserver` (BL-27)."""

from __future__ import annotations

import logging

import pytest

from restgdf._models._drift import (
    FieldSetDriftObserver,
    _log_drift,
    reset_drift_cache,
)

DRIFT_LOGGER = "restgdf.schema_drift"


@pytest.fixture(autouse=True)
def _reset_drift_cache() -> None:
    reset_drift_cache()


def _feature(**attributes: object) -> dict[str, object]:
    return {"attributes": dict(attributes)}


def test_learn_pages_must_be_positive() -> None:
    with pytest.raises(ValueError):
        FieldSetDriftObserver(context="ctx", learn_pages=0)


def test_baseline_page_emits_no_drift(caplog: pytest.LogCaptureFixture) -> None:
    observer = FieldSetDriftObserver(context="layer-0")
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page([_feature(OBJECTID=1, name="a")])
    assert caplog.records == []


def test_field_appeared_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    observer = FieldSetDriftObserver(context="layer-0")
    observer.observe_page([_feature(OBJECTID=1)])
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page([_feature(OBJECTID=2, NEW_FIELD="x")])
        observer.observe_page([_feature(OBJECTID=3, NEW_FIELD="y")])
    appeared = [r for r in caplog.records if "field_appeared" in r.getMessage()]
    assert len(appeared) == 1
    assert "NEW_FIELD" in appeared[0].getMessage()
    assert "FieldSetDriftObserver[layer-0]" in appeared[0].getMessage()


def test_field_disappeared_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    observer = FieldSetDriftObserver(context="layer-1")
    observer.observe_page([_feature(OBJECTID=1, legacy="x")])
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page([_feature(OBJECTID=2)])
        observer.observe_page([_feature(OBJECTID=3)])
    disappeared = [r for r in caplog.records if "field_disappeared" in r.getMessage()]
    assert len(disappeared) == 1
    assert "legacy" in disappeared[0].getMessage()


def test_empty_page_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    observer = FieldSetDriftObserver(context="layer-empty")
    observer.observe_page([_feature(OBJECTID=1, legacy="x")])
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        # Empty batch (no features) — must NOT emit field_disappeared.
        observer.observe_page([])
        # Batch of only non-mapping entries — likewise skipped.
        observer.observe_page([42, None, "junk"])  # type: ignore[list-item]
    assert caplog.records == []


def test_features_without_attributes_are_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observer = FieldSetDriftObserver(context="layer-2")
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page(
            [{"geometry": {"x": 0, "y": 0}}, {"attributes": None}],  # type: ignore[list-item]
        )
    # No mapping attributes → treated as empty page → no drift.
    assert caplog.records == []


def test_learn_pages_gt_one_extends_baseline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observer = FieldSetDriftObserver(context="layer-3", learn_pages=2)
    observer.observe_page([_feature(a=1)])
    observer.observe_page([_feature(b=2)])
    # Baseline now {a, b}; page 3 introduces c and drops both a and b.
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page([_feature(c=3)])
    kinds = {
        kind
        for kind in ("field_appeared", "field_disappeared")
        if any(kind in r.getMessage() for r in caplog.records)
    }
    assert kinds == {"field_appeared", "field_disappeared"}


def test_drift_context_in_model_name(caplog: pytest.LogCaptureFixture) -> None:
    observer = FieldSetDriftObserver(context="my-service/3")
    observer.observe_page([_feature(a=1)])
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page([_feature(a=1, b=2)])
    assert any(
        "FieldSetDriftObserver[my-service/3]" in r.getMessage() for r in caplog.records
    )


def test_dedupe_across_disappear_reappear(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observer = FieldSetDriftObserver(context="layer-4")
    observer.observe_page([_feature(x=1)])
    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        observer.observe_page([_feature(y=2)])  # x disappears, y appears
        observer.observe_page([_feature(x=3, y=4)])  # x reappears (deduped)
    # `x` disappeared once, `y` appeared once; the reappearance of `x`
    # hits the _log_drift dedupe cache (same model_name+path+kind).
    messages = [r.getMessage() for r in caplog.records]
    assert sum("field_disappeared" in m and "'x'" in m for m in messages) == 1
    assert sum("field_appeared" in m and "'y'" in m for m in messages) == 1


def test_reset_drift_cache_allows_re_emission(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Prove the dedupe cache is process-scoped and that a direct
    # ``reset_drift_cache()`` call genuinely re-enables emission of the
    # same drift key. Exercises ``_log_drift`` directly rather than
    # going through the observer so the test is decoupled from the
    # observer's internal "observed keys" state.
    def emit() -> None:
        _log_drift(
            model_name="ResetTest",
            path="my_field",
            kind="field_appeared",
            sample="my_field",
            level=logging.INFO,
        )

    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        emit()
        emit()  # deduped - no second record
    first_pass = [r for r in caplog.records if "ResetTest" in r.getMessage()]
    assert len(first_pass) == 1

    caplog.clear()
    reset_drift_cache()

    with caplog.at_level(logging.INFO, logger=DRIFT_LOGGER):
        emit()  # re-emits after cache reset
    second_pass = [r for r in caplog.records if "ResetTest" in r.getMessage()]
    assert len(second_pass) == 1
