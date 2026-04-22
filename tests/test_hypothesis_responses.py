"""BL-39 scaffold: hypothesis property tests for response normalization.

This module bootstraps the ``hypothesis`` dependency via ``[dev]`` extras
and demonstrates property-based testing of the response normalization
pipeline.  Expand with additional strategies as coverage targets require.
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from restgdf._models.responses import (
    FeaturesResponse,
    FieldSpec,
    _epoch_ms_to_iso,
    iter_normalized_features,
)


# ── strategy: arbitrary epoch-ms values ────────────────────────────

_epoch_ms = st.one_of(
    st.integers(min_value=0, max_value=4_102_444_800_000),  # up to ~2100
    st.none(),
)


@given(epoch=st.integers(min_value=0, max_value=4_102_444_800_000))
@settings(max_examples=50)
def test_epoch_ms_to_iso_roundtrip_never_crashes(epoch: int):
    """_epoch_ms_to_iso never raises for non-negative integers in range."""
    result = _epoch_ms_to_iso(epoch)
    assert result is None or isinstance(result, str)


@given(value=st.one_of(st.none(), st.text(), st.binary()))
@settings(max_examples=50)
def test_epoch_ms_to_iso_garbage_returns_none_or_str(value):
    """_epoch_ms_to_iso returns None or str for arbitrary garbage input."""
    result = _epoch_ms_to_iso(value)
    assert result is None or isinstance(result, str)


# ── strategy: arbitrary feature attributes ─────────────────────────

_attribute_values = st.one_of(
    st.none(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=50),
)

_attribute_dicts = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
    values=_attribute_values,
    max_size=10,
)


@given(attrs=_attribute_dicts)
@settings(max_examples=30)
def test_iter_normalized_features_never_crashes_on_arbitrary_attributes(
    attrs: dict,
):
    """iter_normalized_features tolerates arbitrary attribute dicts."""
    response = FeaturesResponse(features=[{"attributes": attrs}])
    features = list(iter_normalized_features(response))
    assert len(features) == 1
    assert features[0].attributes == attrs


@given(attrs=_attribute_dicts)
@settings(max_examples=30)
def test_normalize_dates_false_preserves_attributes(attrs: dict):
    """normalize_dates=False never mutates attribute values."""
    fields = [FieldSpec(name="d", type="esriFieldTypeDate")]
    response = FeaturesResponse(features=[{"attributes": attrs}], fields=fields)
    features = list(iter_normalized_features(response, normalize_dates=False))
    assert features[0].attributes == attrs
