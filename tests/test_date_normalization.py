"""BL-54: date field normalization (epoch-ms → ISO-8601 UTC).

Tests for the ``normalize_dates`` parameter on
:func:`~restgdf._models.responses.iter_normalized_features` and the
helpers ``_epoch_ms_to_iso``, ``_resolve_date_fields``,
``_ESRI_DATE_TYPES``.
"""

from __future__ import annotations

import pytest

from restgdf._models.responses import (
    FeaturesResponse,
    FieldSpec,
    _ESRI_DATE_TYPES,
    _epoch_ms_to_iso,
    _resolve_date_fields,
    iter_normalized_features,
)


# ── helper unit tests ─────────────────────────────────────────────


class TestEpochMsToIso:
    """Unit tests for ``_epoch_ms_to_iso``."""

    def test_zero_epoch(self):
        assert _epoch_ms_to_iso(0) == "1970-01-01T00:00:00+00:00"

    def test_known_timestamp(self):
        # 2024-01-15T12:00:00Z = 1705320000000 ms
        result = _epoch_ms_to_iso(1705320000000)
        assert result == "2024-01-15T12:00:00+00:00"

    def test_none_returns_none(self):
        assert _epoch_ms_to_iso(None) is None

    def test_non_numeric_returns_none(self):
        assert _epoch_ms_to_iso("not-a-number") is None

    def test_negative_epoch(self):
        # Before 1970 — may return None on Windows (OSError on negative ts)
        import sys
        result = _epoch_ms_to_iso(-86400000)
        if sys.platform == "win32":
            assert result is None or result == "1969-12-31T00:00:00+00:00"
        else:
            assert result == "1969-12-31T00:00:00+00:00"

    def test_float_epoch(self):
        result = _epoch_ms_to_iso(1705320000000.0)
        assert result == "2024-01-15T12:00:00+00:00"

    def test_string_numeric(self):
        result = _epoch_ms_to_iso("1705320000000")
        assert result == "2024-01-15T12:00:00+00:00"


class TestResolveDateFields:
    """Unit tests for ``_resolve_date_fields``."""

    def test_none_fields(self):
        assert _resolve_date_fields(None) == frozenset()

    def test_empty_fields(self):
        assert _resolve_date_fields([]) == frozenset()

    def test_no_date_fields(self):
        fields = [FieldSpec(name="Name", type="esriFieldTypeString")]
        assert _resolve_date_fields(fields) == frozenset()

    def test_date_fields_detected(self):
        fields = [
            FieldSpec(name="Name", type="esriFieldTypeString"),
            FieldSpec(name="CreatedDate", type="esriFieldTypeDate"),
            FieldSpec(name="EditDate", type="esriFieldTypeDate"),
        ]
        result = _resolve_date_fields(fields)
        assert result == frozenset({"CreatedDate", "EditDate"})

    def test_all_esri_date_types_recognized(self):
        fields = [
            FieldSpec(name="D1", type="esriFieldTypeDate"),
            FieldSpec(name="D2", type="esriFieldTypeTimeOnly"),
            FieldSpec(name="D3", type="esriFieldTypeDateOnly"),
        ]
        result = _resolve_date_fields(fields)
        assert result == frozenset({"D1", "D2", "D3"})

    def test_field_with_none_name_excluded(self):
        fields = [FieldSpec(name=None, type="esriFieldTypeDate")]
        assert _resolve_date_fields(fields) == frozenset()


class TestEsriDateTypes:
    """Sanity check for the date type constant."""

    def test_contains_expected_types(self):
        assert "esriFieldTypeDate" in _ESRI_DATE_TYPES
        assert "esriFieldTypeTimeOnly" in _ESRI_DATE_TYPES
        assert "esriFieldTypeDateOnly" in _ESRI_DATE_TYPES

    def test_does_not_contain_string(self):
        assert "esriFieldTypeString" not in _ESRI_DATE_TYPES


# ── integration via iter_normalized_features ──────────────────────


def _features_response(
    features: list[dict],
    fields: list[FieldSpec] | None = None,
) -> FeaturesResponse:
    return FeaturesResponse(features=features, fields=fields)


class TestNormalizeDatesOff:
    """Default behaviour: epoch-ms values preserved when normalize_dates=False."""

    def test_dates_preserved_by_default(self):
        fields = [FieldSpec(name="EditDate", type="esriFieldTypeDate")]
        response = _features_response(
            [{"attributes": {"EditDate": 1705320000000}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response))
        assert feature.attributes["EditDate"] == 1705320000000

    def test_dates_preserved_explicit_false(self):
        fields = [FieldSpec(name="EditDate", type="esriFieldTypeDate")]
        response = _features_response(
            [{"attributes": {"EditDate": 1705320000000}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response, normalize_dates=False))
        assert feature.attributes["EditDate"] == 1705320000000


class TestNormalizeDatesOn:
    """Date normalization when ``normalize_dates=True``."""

    def test_date_converted_to_iso(self):
        fields = [FieldSpec(name="EditDate", type="esriFieldTypeDate")]
        response = _features_response(
            [{"attributes": {"EditDate": 1705320000000}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response, normalize_dates=True))
        assert feature.attributes["EditDate"] == "2024-01-15T12:00:00+00:00"

    def test_non_date_field_untouched(self):
        fields = [
            FieldSpec(name="Name", type="esriFieldTypeString"),
            FieldSpec(name="EditDate", type="esriFieldTypeDate"),
        ]
        response = _features_response(
            [{"attributes": {"Name": "test", "EditDate": 1705320000000}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response, normalize_dates=True))
        assert feature.attributes["Name"] == "test"
        assert feature.attributes["EditDate"] == "2024-01-15T12:00:00+00:00"

    def test_null_date_value_stays_none(self):
        fields = [FieldSpec(name="EditDate", type="esriFieldTypeDate")]
        response = _features_response(
            [{"attributes": {"EditDate": None}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response, normalize_dates=True))
        assert feature.attributes["EditDate"] is None

    def test_multiple_date_fields_converted(self):
        fields = [
            FieldSpec(name="Created", type="esriFieldTypeDate"),
            FieldSpec(name="Modified", type="esriFieldTypeDate"),
        ]
        response = _features_response(
            [{"attributes": {"Created": 0, "Modified": 1705320000000}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response, normalize_dates=True))
        assert feature.attributes["Created"] == "1970-01-01T00:00:00+00:00"
        assert feature.attributes["Modified"] == "2024-01-15T12:00:00+00:00"

    def test_no_fields_on_response_still_works(self):
        """normalize_dates=True but no fields metadata → no conversion."""
        response = _features_response(
            [{"attributes": {"EditDate": 1705320000000}}],
            fields=None,
        )
        feature = next(iter_normalized_features(response, normalize_dates=True))
        assert feature.attributes["EditDate"] == 1705320000000

    def test_missing_date_attribute_no_error(self):
        """Field declared as date but not in attributes → no crash."""
        fields = [FieldSpec(name="EditDate", type="esriFieldTypeDate")]
        response = _features_response(
            [{"attributes": {"Name": "test"}}],
            fields=fields,
        )
        feature = next(iter_normalized_features(response, normalize_dates=True))
        assert "EditDate" not in feature.attributes
        assert feature.attributes["Name"] == "test"
