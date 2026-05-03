"""Low-level utility modules for HTTP transport, pagination, and data helpers.

Most users should interact with :class:`~restgdf.FeatureLayer` and
:class:`~restgdf.Directory` instead of calling these directly.
Submodules are lazily loaded to avoid importing heavy optional
dependencies at package init time.
"""

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
