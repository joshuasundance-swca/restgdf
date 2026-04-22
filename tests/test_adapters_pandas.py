from __future__ import annotations

import importlib
from typing import Any

import pytest

from restgdf.errors import OptionalDependencyError


def test_rows_to_dataframe_happy_path() -> None:
    pd = pytest.importorskip("pandas")

    from restgdf.adapters.pandas import rows_to_dataframe

    df = rows_to_dataframe(
        [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}],
    )

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["a", "b"]
    assert df["a"].tolist() == [1, 2]


@pytest.mark.asyncio
async def test_arows_to_dataframe_happy_path() -> None:
    pd = pytest.importorskip("pandas")

    from restgdf.adapters.pandas import arows_to_dataframe

    async def _gen():
        yield {"a": 1}
        yield {"a": 2}

    df = await arows_to_dataframe(_gen())

    assert isinstance(df, pd.DataFrame)
    assert df["a"].tolist() == [1, 2]


def test_rows_to_dataframe_raises_without_pandas(monkeypatch) -> None:
    from restgdf.adapters import pandas as pandas_adapter

    def _missing(module_name: str) -> Any:
        exc = ModuleNotFoundError(f"No module named '{module_name}'")
        exc.name = module_name
        raise exc

    monkeypatch.setattr(
        "restgdf.utils._optional.import_module",
        _missing,
    )
    # Reload adapter module to ensure the patched helper is used — its
    # ``require_pandas`` import is resolved at call time via the attribute
    # lookup inside ``_import_optional_module``.
    importlib.reload(pandas_adapter)

    with pytest.raises(OptionalDependencyError) as excinfo:
        pandas_adapter.rows_to_dataframe([{"a": 1}])

    assert "restgdf[geo]" in str(excinfo.value)


@pytest.mark.asyncio
async def test_arows_to_dataframe_raises_without_pandas(monkeypatch) -> None:
    from restgdf.adapters import pandas as pandas_adapter

    def _missing(module_name: str) -> Any:
        exc = ModuleNotFoundError(f"No module named '{module_name}'")
        exc.name = module_name
        raise exc

    monkeypatch.setattr(
        "restgdf.utils._optional.import_module",
        _missing,
    )
    importlib.reload(pandas_adapter)

    async def _gen():
        yield {"a": 1}

    with pytest.raises(OptionalDependencyError):
        await pandas_adapter.arows_to_dataframe(_gen())
