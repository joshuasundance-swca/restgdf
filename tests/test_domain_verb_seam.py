"""BL-20 red tests: request-verb seam.

Per MASTER-PLAN §5 BL-20 (MASTER-PLAN.md:143-144):

> BL-20. Deterministic request-verb seam. Add a private
>   ``_choose_verb(url, body=None)`` helper that returns
>   ``"POST"`` for ArcGIS ``/query`` and ``/queryRelatedRecords``
>   endpoints, ``"GET"`` for metadata-style requests, and ``"POST"``
>   as the conservative default for unknown URLs.

These tests probe the seam only; call sites are NOT rewired in this
slice (a later BL-50 extends this to auto-switch GET → POST when a
``where`` clause pushes a GET URL past the ArcGIS ~1800-byte budget).
"""

from __future__ import annotations


def test_choose_verb_default_for_unknown_url_is_post():
    """Named red per plan.md §3c R-34/R-35: the default for URLs that
    match none of the known families must be POST (conservative — avoids
    URL-length blowups and works with any body)."""
    from restgdf.utils._http import _choose_verb

    assert _choose_verb("https://example.com/some/unknown/path") == "POST"
    assert _choose_verb("https://example.com/rest/services/Foo/MapServer") == "POST"


def test_choose_verb_query_endpoint_is_post():
    from restgdf.utils._http import _choose_verb

    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0/query",
        )
        == "POST"
    )


def test_choose_verb_query_related_records_is_post():
    from restgdf.utils._http import _choose_verb

    url = (
        "https://example.com/ArcGIS/rest/services/X/FeatureServer/0/"
        "queryRelatedRecords"
    )
    assert _choose_verb(url) == "POST"


def test_choose_verb_metadata_endpoint_is_get():
    """Bare service / layer metadata URLs (no trailing ``/query`` or
    ``/queryRelatedRecords``) are short and idempotent — GET."""
    from restgdf.utils._http import _choose_verb

    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0",
        )
        == "GET"
    )
    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer",
        )
        == "GET"
    )


def test_choose_verb_accepts_optional_body_mapping():
    """The signature is ``_choose_verb(url, body=None)`` so BL-50 can
    later inspect the ``where`` clause and switch based on serialized
    length — today, the body is ignored but must be accepted without
    raising."""
    from restgdf.utils._http import _choose_verb

    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0/query",
            body={"where": "1=1", "outFields": "*"},
        )
        == "POST"
    )
    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0",
            body=None,
        )
        == "GET"
    )
