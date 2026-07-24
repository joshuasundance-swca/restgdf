"""W5-14 (CONFIG-02 / CONFIG-03): opt-in ``from_config`` construction seam.

Per the config hybrid decision, ``FeatureLayer.from_config`` /
``Directory.from_config`` are **opt-in and explicit**: the caller passes a
``Config``; the only setting consumed is ``config.auth.token`` (forwarded as
the request token), and NOTHING here implicitly reads the process-global
``get_config()`` at import or construction time. A directly built ``Config``
is not otherwise threaded into the request path (CONFIG-03 delete-the-claim).
"""

from __future__ import annotations

import inspect

import pytest

from restgdf._config import AuthConfig, Config
from restgdf.directory.directory import Directory
from restgdf.featurelayer.featurelayer import FeatureLayer


@pytest.mark.asyncio
async def test_featurelayer_from_config_applies_auth_token(
    fake_session,
    feature_layer_metadata,
) -> None:
    fake_session.post_responses.extend([feature_layer_metadata, {"count": 5}])
    cfg = Config(auth=AuthConfig(token="cfg-token"))
    fl = await FeatureLayer.from_config(
        "https://example.test/MapServer/0",
        cfg,
        session=fake_session,
    )
    # The explicit config's token reached the request datadict.
    assert fl.datadict["token"] == "cfg-token"
    assert fl.count == 5


@pytest.mark.asyncio
async def test_featurelayer_from_config_no_token_when_config_has_none(
    fake_session,
    feature_layer_metadata,
) -> None:
    fake_session.post_responses.extend([feature_layer_metadata, {"count": 0}])
    fl = await FeatureLayer.from_config(
        "https://example.test/MapServer/0",
        Config(),  # auth.token is None
        session=fake_session,
    )
    assert fl.datadict.get("token") is None


@pytest.mark.asyncio
async def test_directory_from_config_applies_auth_token(
    fake_session,
    feature_layer_metadata,
) -> None:
    fake_session.post_responses.append(feature_layer_metadata)
    cfg = Config(auth=AuthConfig(token="dir-token"))
    directory = await Directory.from_config(
        "https://example.test/rest/services",
        cfg,
        session=fake_session,
    )
    assert directory.token == "dir-token"


def test_from_config_requires_explicit_config() -> None:
    """``config`` is a required positional -- no implicit process-global."""
    for ctor in (FeatureLayer.from_config, Directory.from_config):
        params = inspect.signature(ctor).parameters
        assert "config" in params
        assert (
            params["config"].default is inspect.Parameter.empty
        ), f"{ctor.__qualname__} must require an explicit config"


def test_plain_construction_consumes_no_implicit_auth_token() -> None:
    """A plain (non-from_config) FeatureLayer never sources a global token.

    Guards the failure mode: config must not be consumed implicitly at
    construction time.
    """
    fl = FeatureLayer(
        "https://example.test/MapServer/0",
        session=object(),  # type: ignore[arg-type]
    )
    assert fl.datadict.get("token") is None
