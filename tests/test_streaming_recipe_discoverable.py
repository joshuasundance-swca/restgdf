"""Regression guard: the streaming recipe exists and is wired into the toctree.

Phase-4B ships ``docs/recipes/streaming.md`` documenting the three canonical
streaming shapes (``stream_features`` / ``stream_feature_batches`` /
``stream_gdf_chunks``). Future docs reorganizations must not quietly drop it.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE = REPO_ROOT / "docs" / "recipes" / "streaming.md"
INDEX = REPO_ROOT / "docs" / "index.rst"


def test_streaming_recipe_file_exists() -> None:
    assert RECIPE.is_file(), f"{RECIPE} is missing"


def test_streaming_recipe_has_required_sections() -> None:
    body = RECIPE.read_text(encoding="utf-8")
    for needle in (
        "stream_features",
        "stream_feature_batches",
        "stream_gdf_chunks",
        "on_truncation",
        '"split"',
        'order="request"',
        'order="completion"',
        "max_concurrent_pages",
        "restgdf[geo]",
    ):
        assert needle in body, f"streaming recipe missing reference: {needle!r}"


def test_streaming_recipe_linked_from_toctree() -> None:
    index_body = INDEX.read_text(encoding="utf-8")
    assert (
        "recipes/streaming" in index_body
    ), "docs/index.rst does not reference recipes/streaming in any toctree"
