"""Pure pagination planner for ArcGIS REST ``/query`` traversal.

Private submodule. Public symbols (:class:`PaginationPlan`,
:func:`build_pagination_plan`) are re-exported via
:mod:`restgdf.utils.getinfo` to preserve the patch-seam convention used
elsewhere in ``restgdf.utils``.

The planner is pure math: given a feature count and a server-advertised
``maxRecordCount`` (plus an optional caller-supplied
``maxRecordCountFactor``), it produces the ``(resultOffset,
resultRecordCount)`` tuples that drive paged ``/query`` calls. It does
not know about HTTP, authentication, or metadata fetches; call sites
(today :func:`restgdf.utils.getgdf.get_query_data_batches`) wrap the
tuples into request bodies.

Clamp semantics for ``maxRecordCountFactor`` match ArcGIS convention:
the advertised factor is an upper bound published by the service;
requesting a larger factor is silently clamped down server-side, so the
planner clamps proactively and emits a single ``WARNING`` via
``restgdf.pagination`` for observability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from restgdf._logging import get_logger

_LOG = get_logger("pagination")
_DEFAULT_FACTOR: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class PaginationPlan:
    """Frozen result of :func:`build_pagination_plan`.

    Attributes:
        total_records: Layer-wide feature count the plan paginates over.
        max_record_count: Server-advertised per-page cap.
        max_record_count_factor: Effective factor after clamping against
            the advertised upper bound. Equals the caller-supplied
            ``factor`` when no clamp was applied.
        effective_page_size: ``max(1, int(max_record_count *
            max_record_count_factor))`` — the actual page size used to
            compute batches.
        batches: Tuple of ``(resultOffset, resultRecordCount)`` pairs.
            Empty when ``total_records == 0``. Last pair's count may be
            less than ``effective_page_size`` (partial tail page).
    """

    total_records: int
    max_record_count: int
    max_record_count_factor: float
    effective_page_size: int
    batches: tuple[tuple[int, int], ...]


def build_pagination_plan(
    total_records: int,
    max_record_count: int,
    *,
    factor: float = _DEFAULT_FACTOR,
    advertised_factor: float | None = None,
) -> PaginationPlan:
    """Compute a :class:`PaginationPlan` for ``total_records`` rows.

    Args:
        total_records: Non-negative total row count (typically the
            result of ``get_feature_count``).
        max_record_count: Positive server-advertised per-page cap.
        factor: Caller-supplied multiplier on ``max_record_count``.
            Defaults to 1.0 (pure ``max_record_count`` pagination).
        advertised_factor: Server-advertised
            ``advancedQueryCapabilities.maxRecordCountFactor`` upper
            bound. When provided and ``factor > advertised_factor``,
            the factor is clamped down and a single warning is logged
            under ``restgdf.pagination``.

    Raises:
        ValueError: If ``total_records < 0``, ``max_record_count <= 0``,
            or ``factor <= 0``.
    """
    if total_records < 0:
        raise ValueError("total_records must be >= 0")
    if max_record_count <= 0:
        raise ValueError("max_record_count must be > 0")
    if factor <= 0:
        raise ValueError("factor must be > 0")

    effective_factor = factor
    if advertised_factor is not None and factor > advertised_factor:
        _LOG.warning(
            "maxRecordCountFactor clamp",
            extra={
                "requested_factor": factor,
                "advertised_factor": advertised_factor,
            },
        )
        effective_factor = advertised_factor

    effective_page_size = max(1, int(max_record_count * effective_factor))

    if total_records == 0:
        batches: tuple[tuple[int, int], ...] = ()
    else:
        batches = tuple(
            (offset, min(effective_page_size, total_records - offset))
            for offset in range(0, total_records, effective_page_size)
        )

    return PaginationPlan(
        total_records=total_records,
        max_record_count=max_record_count,
        max_record_count_factor=effective_factor,
        effective_page_size=effective_page_size,
        batches=batches,
    )


__all__ = ["PaginationPlan", "build_pagination_plan"]
