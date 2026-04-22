"""Coverage tests for :mod:`restgdf._models.credentials`.

Targets the root ``_translate_legacy_refresh_threshold`` validator
branches that are not exercised by ``tests/test_models_credentials.py``:

* non-dict ``data`` passthrough (line 109)
* non-int ``refresh_threshold_seconds`` legacy alias fallthrough to the
  field validators (lines 121-125)
"""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig


def _creds() -> AGOLUserPass:
    return AGOLUserPass(username="u", password="p")


def test_before_validator_passes_non_dict_through_unchanged():
    """When ``model_validate`` receives a non-dict (e.g. an existing
    model instance), the ``mode='before'`` validator must return it
    unchanged rather than attempt a ``.pop()``.
    """
    original = TokenSessionConfig(
        token_url="https://example.com/token",
        credentials=_creds(),
    )

    # Re-validating an instance hands the validator the instance itself
    # (not a dict). The branch under test simply returns it through.
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        revalidated = TokenSessionConfig.model_validate(original)

    assert revalidated.token_url == original.token_url
    assert revalidated.refresh_leeway_seconds == original.refresh_leeway_seconds
    assert revalidated.clock_skew_seconds == original.clock_skew_seconds


def test_before_validator_returns_non_dict_mapping_like_inputs_directly():
    """Passing a non-dict, non-model object to ``model_validate`` still
    reaches the early-return branch; pydantic then raises its own error
    downstream. We only assert the validator itself does not blow up on
    the ``.pop()`` path.
    """
    sentinel = ["not", "a", "dict"]
    with pytest.raises(ValidationError):
        # pydantic will reject the list at the outer schema, but the
        # ``mode='before'`` validator runs first and must pass it through.
        TokenSessionConfig.model_validate(sentinel)


def test_legacy_refresh_threshold_string_coerces_via_field_validator():
    """A string ``refresh_threshold_seconds`` is *not* split into
    ``clock_skew_seconds`` / ``refresh_leeway_seconds``; it is placed
    into ``refresh_leeway_seconds`` so pydantic's field validator can
    coerce or reject it. A numeric string like ``"75"`` coerces cleanly.
    """
    with pytest.warns(DeprecationWarning, match="refresh_threshold_seconds"):
        cfg = TokenSessionConfig(
            token_url="https://example.com/token",
            credentials=_creds(),
            refresh_threshold_seconds="75",  # type: ignore[arg-type]
        )

    # Because the non-int branch defers to field validators, the full
    # value lands in ``refresh_leeway_seconds`` and ``clock_skew_seconds``
    # keeps its default — no 30-cap split is applied.
    assert cfg.refresh_leeway_seconds == 75
    assert cfg.clock_skew_seconds == 30


def test_legacy_refresh_threshold_bool_is_treated_as_non_int():
    """``bool`` is a subclass of ``int`` in Python, but the validator
    explicitly rejects it so ``refresh_threshold_seconds=True`` does not
    silently become ``1``. It falls through to the field validator,
    which accepts ``True`` as ``1`` for ``refresh_leeway_seconds``.
    """
    with pytest.warns(DeprecationWarning):
        cfg = TokenSessionConfig(
            token_url="https://example.com/token",
            credentials=_creds(),
            refresh_threshold_seconds=True,  # type: ignore[arg-type]
        )

    # ``True`` lands in ``refresh_leeway_seconds`` untouched by the
    # split logic; ``clock_skew_seconds`` keeps its default.
    assert cfg.refresh_leeway_seconds == 1
    assert cfg.clock_skew_seconds == 30


def test_legacy_refresh_threshold_non_numeric_string_fails_field_validation():
    """A non-numeric string survives the root validator (non-int branch)
    and is rejected by the ``refresh_leeway_seconds`` field validator.
    """
    with pytest.warns(DeprecationWarning), pytest.raises(ValidationError):
        TokenSessionConfig(
            token_url="https://example.com/token",
            credentials=_creds(),
            refresh_threshold_seconds="not-a-number",  # type: ignore[arg-type]
        )


def test_legacy_refresh_threshold_does_not_overwrite_explicit_leeway():
    """``setdefault`` is used on the non-int path, so an explicit
    ``refresh_leeway_seconds`` wins over the legacy alias value.
    """
    with pytest.warns(DeprecationWarning):
        cfg = TokenSessionConfig(
            token_url="https://example.com/token",
            credentials=_creds(),
            refresh_threshold_seconds="999",  # type: ignore[arg-type]
            refresh_leeway_seconds=10,
        )

    assert cfg.refresh_leeway_seconds == 10
