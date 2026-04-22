"""BL-22 tests: :mod:`restgdf.utils._pagination`.

Covers the pure-math planner (offset/count tuples, edge cases, factor
clamp with warning) and the getinfo.py re-export patch-seam contract.
Full-stack byte-exact pagination through ``get_query_data_batches`` is
already pinned by ``tests/test_getgdf.py`` and
``tests/test_characterization.py``; this module pins the planner itself
and its re-export surface.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from restgdf.utils._pagination import PaginationPlan, build_pagination_plan


def test_build_pagination_plan_basic_math():
    plan = build_pagination_plan(25, 10)
    assert plan.batches == ((0, 10), (10, 10), (20, 5))
    assert plan.effective_page_size == 10
    assert plan.max_record_count_factor == 1.0
    assert plan.total_records == 25
    assert plan.max_record_count == 10


def test_build_pagination_plan_exact_multiple():
    plan = build_pagination_plan(20, 10)
    assert plan.batches == ((0, 10), (10, 10))


def test_build_pagination_plan_zero_records():
    plan = build_pagination_plan(0, 10)
    assert plan.batches == ()
    assert plan.effective_page_size == 10


def test_build_pagination_plan_total_lte_page_size():
    plan = build_pagination_plan(3, 10)
    assert plan.batches == ((0, 3),)


def test_build_pagination_plan_factor_applied():
    plan = build_pagination_plan(50, 10, factor=2.0)
    assert plan.effective_page_size == 20
    assert plan.max_record_count_factor == 2.0
    assert plan.batches == ((0, 20), (20, 20), (40, 10))


def test_build_pagination_plan_factor_clamps_with_warning(caplog):
    caplog.set_level(logging.WARNING, logger="restgdf.pagination")
    plan = build_pagination_plan(50, 10, factor=3.0, advertised_factor=2.0)
    assert plan.max_record_count_factor == 2.0
    assert plan.effective_page_size == 20
    assert plan.batches == ((0, 20), (20, 20), (40, 10))
    assert any(
        record.name == "restgdf.pagination" and "clamp" in record.getMessage().lower()
        for record in caplog.records
    )


def test_build_pagination_plan_factor_at_advertised_no_warning(caplog):
    caplog.set_level(logging.WARNING, logger="restgdf.pagination")
    plan = build_pagination_plan(10, 5, factor=2.0, advertised_factor=2.0)
    assert plan.max_record_count_factor == 2.0
    assert not any(record.name == "restgdf.pagination" for record in caplog.records)


def test_build_pagination_plan_factor_below_advertised_no_warning(caplog):
    caplog.set_level(logging.WARNING, logger="restgdf.pagination")
    plan = build_pagination_plan(10, 5, factor=1.5, advertised_factor=2.0)
    assert plan.max_record_count_factor == 1.5
    assert plan.effective_page_size == 7
    assert not any(record.name == "restgdf.pagination" for record in caplog.records)


@pytest.mark.parametrize(
    ("total", "max_rc", "factor"),
    [
        (-1, 10, 1.0),
        (10, 0, 1.0),
        (10, -5, 1.0),
        (10, 10, 0),
        (10, 10, -0.5),
    ],
)
def test_build_pagination_plan_invalid_inputs(total, max_rc, factor):
    with pytest.raises(ValueError):
        build_pagination_plan(total, max_rc, factor=factor)


def test_build_pagination_plan_batches_match_existing_getgdf_pattern():
    """Pin planner byte-exactness against the two fixtures
    :mod:`tests.test_getgdf` and :mod:`tests.test_characterization` use
    to pin the full-stack pagination path. Keeping this pin in the
    planner module localises the invariant to the code it protects."""
    assert build_pagination_plan(5, 2).batches == ((0, 2), (2, 2), (4, 1))
    assert build_pagination_plan(25, 10).batches == ((0, 10), (10, 10), (20, 5))


def test_pagination_plan_is_frozen():
    plan = build_pagination_plan(5, 2)
    with pytest.raises((AttributeError, TypeError)):
        plan.total_records = 999  # type: ignore[misc]


def test_getinfo_reexports_pagination_symbols():
    """Patch-seam contract: :mod:`restgdf.utils.getinfo` must expose
    both ``PaginationPlan`` and ``build_pagination_plan`` at the module
    namespace so consumers (and :mod:`unittest.mock.patch` targets)
    resolve them through the getinfo module path."""
    from restgdf.utils import getinfo

    assert getinfo.PaginationPlan is PaginationPlan
    assert getinfo.build_pagination_plan is build_pagination_plan
    assert "PaginationPlan" in getinfo.__all__
    assert "build_pagination_plan" in getinfo.__all__


@pytest.mark.asyncio
async def test_default_pagination_uses_factor_1_0():
    """Regression: `get_query_data_batches` calls the planner with
    `factor=1.0` (default) and no `advertised_factor` in phase-2c.

    This pins the deferred-plumbing decision: live
    `advancedQueryCapabilities.maxRecordCountFactor` is not yet wired
    into the call site, so production batch sizes stay byte-exact
    during the 3.0 migration.
    """
    from restgdf.utils import getgdf

    real_planner = getgdf.build_pagination_plan
    spy = MagicMock()

    def capture(*args, **kwargs):
        spy(*args, **kwargs)
        return real_planner(*args, **kwargs)

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=25),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 10,
                "advancedQueryCapabilities": {
                    "supportsPagination": True,
                    "maxRecordCountFactor": 4.0,
                },
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.build_pagination_plan",
        side_effect=capture,
    ):
        result = await getgdf.get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1"},
        )

    spy.assert_called_once()
    call_args, call_kwargs = spy.call_args
    assert call_args == (25, 10)
    assert "factor" not in call_kwargs
    assert "advertised_factor" not in call_kwargs
    assert result == [
        {"where": "1=1", "resultOffset": 0, "resultRecordCount": 10},
        {"where": "1=1", "resultOffset": 10, "resultRecordCount": 10},
        {"where": "1=1", "resultOffset": 20, "resultRecordCount": 5},
    ]


@pytest.mark.asyncio
async def test_caller_override_result_record_count_bypasses_planner():
    """Caller-supplied `data={"resultRecordCount": N}` takes the
    pre-planner branch in `get_query_data_batches`; the planner is
    never called. Batch sizes honor the caller's N (clamped at
    `max_record_count`), not the planner default.
    """
    from restgdf.utils import getgdf

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=2500),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 1000,
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.build_pagination_plan",
    ) as planner_mock:
        result = await getgdf.get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"resultRecordCount": 500},
        )

    planner_mock.assert_not_called()
    assert result == [
        {"resultRecordCount": 500, "resultOffset": 0},
        {"resultRecordCount": 500, "resultOffset": 500},
        {"resultRecordCount": 500, "resultOffset": 1000},
        {"resultRecordCount": 500, "resultOffset": 1500},
        {"resultRecordCount": 500, "resultOffset": 2000},
    ]


@pytest.mark.asyncio
async def test_caller_override_result_record_count_partial_final_batch():
    """Override branch with N that doesn't divide `feature_count` evenly:
    the final batch is clamped to the remainder.
    """
    from restgdf.utils import getgdf

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=1100),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 1000,
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.build_pagination_plan",
    ) as planner_mock:
        result = await getgdf.get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"resultRecordCount": 400},
        )

    planner_mock.assert_not_called()
    assert result == [
        {"resultRecordCount": 400, "resultOffset": 0},
        {"resultRecordCount": 400, "resultOffset": 400},
        {"resultRecordCount": 300, "resultOffset": 800},
    ]
