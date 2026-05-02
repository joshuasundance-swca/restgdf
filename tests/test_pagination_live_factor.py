"""T9 tests: R-72 advertised_factor live-wiring + R-73 PaginationInconsistencyWarning.

R-72: when layer metadata advertises
``advancedQueryCapabilities.supportsMaxRecordCountFactor`` (aka
``maxRecordCountFactor``), :func:`get_query_data_batches` must pass it
through as ``advertised_factor=`` to the planner. Servers that do NOT
advertise the field keep today's byte-for-byte behavior (no
``advertised_factor`` kwarg supplied).

R-73: a ``PaginationInconsistencyWarning`` sentinel is emitted when
a batch page returns ``exceededTransferLimit=true`` with zero
features — an ArcGIS misbehavior that silently breaks offset-based
pagination (the cursor never advances).
"""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from restgdf.errors import PaginationInconsistencyWarning
from restgdf.utils import getgdf


# ---------------------------------------------------------------------------
# R-72: advertised_factor live-wire at get_query_data_batches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_advertised_factor_wired_when_server_advertises_it():
    """With metadata containing
    ``advancedQueryCapabilities.maxRecordCountFactor: 5``,
    ``get_query_data_batches`` must call ``build_pagination_plan``
    with ``advertised_factor=5``.
    """
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
                    "maxRecordCountFactor": 5,
                },
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.build_pagination_plan",
        side_effect=capture,
    ):
        await getgdf.get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1"},
        )

    spy.assert_called_once()
    _, call_kwargs = spy.call_args
    assert call_kwargs.get("advertised_factor") == 5


@pytest.mark.asyncio
async def test_advertised_factor_omitted_when_server_does_not_advertise():
    """Opt-in guarantee: without
    ``advancedQueryCapabilities.maxRecordCountFactor``, no
    ``advertised_factor`` kwarg is supplied — servers without the
    field keep byte-exact 3.0-baseline behavior.
    """
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
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.build_pagination_plan",
        side_effect=capture,
    ):
        await getgdf.get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1"},
        )

    spy.assert_called_once()
    _, call_kwargs = spy.call_args
    assert "advertised_factor" not in call_kwargs


@pytest.mark.asyncio
async def test_advertised_factor_omitted_when_no_advanced_capabilities_block():
    """No ``advancedQueryCapabilities`` key at all → no advertised_factor."""
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
                "supportsPagination": True,
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.build_pagination_plan",
        side_effect=capture,
    ):
        await getgdf.get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1"},
        )

    spy.assert_called_once()
    _, call_kwargs = spy.call_args
    assert "advertised_factor" not in call_kwargs


# ---------------------------------------------------------------------------
# R-73: PaginationInconsistencyWarning on 0-feature + exceededTransferLimit
# ---------------------------------------------------------------------------


def test_pagination_inconsistency_warning_is_userwarning_subclass():
    assert issubclass(PaginationInconsistencyWarning, UserWarning)


@pytest.mark.asyncio
async def test_zero_features_with_exceeded_limit_emits_inconsistency_warning():
    """Batch page returning ``exceededTransferLimit=true`` AND zero
    features is a server bug that silently breaks pagination — emit
    a :class:`PaginationInconsistencyWarning`.
    """
    page = {
        "features": [],
        "exceededTransferLimit": True,
    }
    collected: list[dict] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async for resolved in getgdf._resolve_page(
            "https://example.com/layer/0",
            object(),
            page,
            {"where": "1=1"},
            on_truncation="ignore",
            depth=0,
            max_depth=32,
            request_kwargs={},
        ):
            collected.append(resolved)

    assert any(
        issubclass(w.category, PaginationInconsistencyWarning) for w in caught
    ), (
        "Expected PaginationInconsistencyWarning for 0-feature + "
        f"exceededTransferLimit=true page; got {[w.category for w in caught]!r}"
    )


@pytest.mark.asyncio
async def test_exceeded_limit_with_features_does_not_emit_inconsistency_warning():
    """A normal exceededTransferLimit response (with features) is
    NOT an inconsistency — no :class:`PaginationInconsistencyWarning`.
    """
    page = {
        "features": [{"attributes": {"OBJECTID": 1}}],
        "exceededTransferLimit": True,
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async for _ in getgdf._resolve_page(
            "https://example.com/layer/0",
            object(),
            page,
            {"where": "1=1"},
            on_truncation="ignore",
            depth=0,
            max_depth=32,
            request_kwargs={},
        ):
            pass

    assert not any(
        issubclass(w.category, PaginationInconsistencyWarning) for w in caught
    ), (
        "PaginationInconsistencyWarning must NOT fire when features>0; "
        f"got {[w.category for w in caught]!r}"
    )


@pytest.mark.asyncio
async def test_no_exceeded_limit_no_inconsistency_warning():
    """Non-truncated pages never trigger the inconsistency warning."""
    page = {"features": [], "exceededTransferLimit": False}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async for _ in getgdf._resolve_page(
            "https://example.com/layer/0",
            object(),
            page,
            {"where": "1=1"},
            on_truncation="raise",
            depth=0,
            max_depth=32,
            request_kwargs={},
        ):
            pass

    assert not any(
        issubclass(w.category, PaginationInconsistencyWarning) for w in caught
    )


def test_pagination_inconsistency_warning_importable_from_errors_module():
    """The sentinel lives in :mod:`restgdf.errors` alongside the error
    taxonomy and is re-exported through the package root for consistency.
    """
    from restgdf import errors

    cls = errors.PaginationInconsistencyWarning
    assert isinstance(cls, type)
    assert issubclass(cls, UserWarning)
    assert cls.__name__ == "PaginationInconsistencyWarning"


def test_pagination_inconsistency_warning_importable_from_package_root():
    from restgdf import PaginationInconsistencyWarning

    assert isinstance(PaginationInconsistencyWarning, type)
    assert issubclass(PaginationInconsistencyWarning, UserWarning)
