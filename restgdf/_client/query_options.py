"""Typed request-payload builder for ArcGIS REST queries.

:class:`QueryOptions` is a frozen dataclass that replaces the
``dict``-based datadict merging previously scattered across
``restgdf.featurelayer`` and ``restgdf.utils.getgdf`` call sites. It is
introduced in Phase 5 of the TDD refactor as an **opt-in** alternative:
existing call sites that pass ``where=``, ``data=``, and ``**kwargs``
are NOT migrated in this phase, so all prior behavior is preserved.

Design contract
---------------
1. Typed fields always win over :attr:`extra` on key conflict; ``extra``
   can only add non-reserved keys.
2. Optional typed fields (``token``, ``result_offset``, ``result_record_count``)
   are omitted from the produced data dict when their value is ``None``.
3. A no-arg :class:`QueryOptions` produces the exact same dict as
   :func:`restgdf.utils._http.default_data`.
4. :attr:`extra` is stored as an immutable :class:`~types.MappingProxyType`
   view over a copy of the caller-supplied mapping, so mutating the
   original dict does not leak into the options.
5. :meth:`to_data` returns a fresh ``dict`` on every call; callers may
   mutate the result safely.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from restgdf.utils._http import DEFAULTDICT


_RESERVED_KEYS = frozenset(
    {
        "where",
        "outFields",
        "returnGeometry",
        "returnCountOnly",
        "returnIdsOnly",
        "resultOffset",
        "resultRecordCount",
        "token",
        "f",
    },
)


def _freeze(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping) if mapping else {})


@dataclass(frozen=True)
class QueryOptions:
    """Typed, immutable request-payload builder for ArcGIS REST queries.

    See the module docstring for the design contract.
    """

    where: str = "1=1"
    out_fields: str = "*"
    return_geometry: bool = True
    return_count_only: bool = False
    return_ids_only: bool = False
    token: str | None = None
    result_offset: int | None = None
    result_record_count: int | None = None
    extra: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        # Normalize extra to a MappingProxyType-wrapped copy so the caller
        # cannot mutate the options by mutating their original dict, and
        # the user cannot mutate the proxy either.
        object.__setattr__(self, "extra", _freeze(self.extra))

    def to_data(self) -> dict[str, Any]:
        """Return a fresh POST body dict for an ArcGIS REST query."""
        data: dict[str, Any] = dict(DEFAULTDICT)
        # Layer extras under defaults, but above nothing reserved yet.
        for k, v in self.extra.items():
            if k in _RESERVED_KEYS:
                continue
            data[k] = v
        # Typed fields win.
        data["where"] = self.where
        data["outFields"] = self.out_fields
        data["returnGeometry"] = self.return_geometry
        data["returnCountOnly"] = self.return_count_only
        if self.return_ids_only:
            data["returnIdsOnly"] = self.return_ids_only
        if self.token is not None:
            data["token"] = self.token
        if self.result_offset is not None:
            data["resultOffset"] = self.result_offset
        if self.result_record_count is not None:
            data["resultRecordCount"] = self.result_record_count
        return data

    @classmethod
    def from_legacy_kwargs(cls, kwargs: Mapping[str, Any]) -> QueryOptions:
        """Parse the legacy ``FeatureLayer(**kwargs)`` convention.

        The legacy convention accepts a top-level ``where=`` plus a
        ``data=`` sub-dict that may carry ``token``, ``outFields``, and
        arbitrary additional keys. This classmethod maps those onto the
        typed fields and routes unknown keys to :attr:`extra`.

        Does not mutate the input mapping.
        """
        top_where = kwargs.get("where")
        data = kwargs.get("data") or {}

        where = data.get("where", top_where if top_where is not None else "1=1")
        token = data.get("token")
        out_fields = data.get("outFields", "*")
        return_geometry = data.get("returnGeometry", True)
        return_count_only = data.get("returnCountOnly", False)
        return_ids_only = data.get("returnIdsOnly", False)
        result_offset = data.get("resultOffset")
        result_record_count = data.get("resultRecordCount")

        extras = {k: v for k, v in data.items() if k not in _RESERVED_KEYS}

        return cls(
            where=where,
            out_fields=out_fields,
            return_geometry=return_geometry,
            return_count_only=return_count_only,
            return_ids_only=return_ids_only,
            token=token,
            result_offset=result_offset,
            result_record_count=result_record_count,
            extra=extras,
        )


__all__ = ["QueryOptions"]
