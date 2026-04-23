"""T8 (R-74) tests: length-based request-verb seam.

Per the v3 follow-up plan, ``_choose_verb`` was extended in T8 (R-74)
from the original BL-20 endpoint-classification contract to a length
based policy: short requests use GET, long requests (URL + encoded body
over the ~8 KiB budget) use POST. The prior BL-20 expectations — that
``/query`` endpoints always POST and metadata endpoints always GET —
were superseded by this slice. Tests below probe the new contract; the
call-site wiring is covered in ``test_choose_verb_live.py``.
"""

from __future__ import annotations


def test_choose_verb_short_unknown_url_is_get():
    """Short requests to unfamiliar URLs default to GET under the new
    length-based policy; POST is reserved for oversized bodies."""
    from restgdf.utils._http import _choose_verb

    assert _choose_verb("https://example.com/some/unknown/path") == "GET"
    assert _choose_verb("https://example.com/arbitrary/endpoint") == "GET"


def test_choose_verb_short_query_endpoint_is_get():
    from restgdf.utils._http import _choose_verb

    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0/query",
        )
        == "GET"
    )


def test_choose_verb_short_query_related_records_is_get():
    from restgdf.utils._http import _choose_verb

    url = (
        "https://example.com/ArcGIS/rest/services/X/FeatureServer/0/"
        "queryRelatedRecords"
    )
    assert _choose_verb(url) == "GET"


def test_choose_verb_metadata_endpoint_is_get():
    """Bare service / layer metadata URLs are short and idempotent — GET."""
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
    """The signature is ``_choose_verb(url, body=None)``; a small body
    keeps the request under the byte budget and stays GET."""
    from restgdf.utils._http import _choose_verb

    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0/query",
            body={"where": "1=1", "outFields": "*"},
        )
        == "GET"
    )
    assert (
        _choose_verb(
            "https://example.com/ArcGIS/rest/services/X/FeatureServer/0",
            body=None,
        )
        == "GET"
    )
