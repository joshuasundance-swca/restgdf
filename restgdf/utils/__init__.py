from __future__ import annotations

import importlib
from typing import Any

__all__ = ["crawl", "getgdf", "getinfo", "utils"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module 'restgdf.utils' has no attribute {name!r}")

    module = importlib.import_module(f"restgdf.utils.{name}")
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
