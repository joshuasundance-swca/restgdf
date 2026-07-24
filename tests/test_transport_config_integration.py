"""M2 wave-2 integration: end-to-end proof that a single env-driven
``TransportConfig`` is honored at BOTH the library data path and the token
seams.

Sets ``RESTGDF_TRANSPORT_VERIFY_SSL=false`` and a custom
``RESTGDF_TRANSPORT_USER_AGENT`` via env (with a cache reset), then drives:

* the **library-built data session** (``get_gdf`` with ``session=None``) —
  proving the env ``verify_ssl`` reaches the real ``TCPConnector`` (W4-5) and
  the env ``user_agent`` reaches the wire headers of a real data request
  (W2-10 ``default_headers``); and
* a **token mint** plus a **token-attached data request** — proving the
  ``/generateToken`` POST honors the session's ``verify_ssl`` and that the env
  ``user_agent`` also reaches token-path data requests (W2-10).

Per the W2X handoff, the env-var ``verify_ssl`` proof is taken through the
library-built connector (W4-5), because the token POST forwards a per-request
``ssl=self.verify_ssl`` that would override a connector's ssl; the token
session's ``verify_ssl`` is set consistently (``False``) to assert the token
seam coherently alongside the connector.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from restgdf import reset_config_cache
from restgdf.utils._http import _arcgis_request, default_headers
from restgdf.utils.getgdf import get_gdf, get_sub_gdf
from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession

_CUSTOM_UA = "restgdf-integration-probe/9.9"
_FAR_FUTURE_MS = 32503680000000  # ~year 3000, in epoch milliseconds


@pytest.fixture
def _transport_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Set verify_ssl=false + a custom user_agent via env and reset the config
    cache so the singleton reflects them; scrub + reset on teardown."""
    monkeypatch.setenv("RESTGDF_TRANSPORT_VERIFY_SSL", "false")
    monkeypatch.setenv("RESTGDF_TRANSPORT_USER_AGENT", _CUSTOM_UA)
    reset_config_cache()
    yield
    reset_config_cache()


class _RecordingDataSession:
    """Plain-session double that records the kwargs of each data request."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs: Any):
        self.post_calls.append((url, kwargs))

        class Response:
            def __init__(self, text_payload: str) -> None:
                self._text_payload = text_payload

            async def text(self) -> str:
                return self._text_payload

        return Response(self.response_text)

    async def get(self, url: str, **kwargs: Any):
        if "params" in kwargs:
            kwargs.setdefault("data", kwargs.pop("params"))
        return await self.post(url, **kwargs)


class _MintContext:
    """Async CM double for the /generateToken POST."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _MintContext:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _DataResponse:
    status = 200


class _RecordingInnerSession:
    """Inner session the ArcGISTokenSession wraps: ``post`` serves the mint
    (async CM); ``get`` serves token-attached data requests (awaitable)."""

    def __init__(self) -> None:
        self.mint_kwargs: dict[str, Any] = {}
        self.data_kwargs: dict[str, Any] = {}

    def post(self, url: str, **kwargs: Any) -> _MintContext:
        self.mint_kwargs = kwargs
        return _MintContext({"token": "minted-tok", "expires": _FAR_FUTURE_MS})

    async def get(self, url: str, **kwargs: Any) -> _DataResponse:
        self.data_kwargs = kwargs
        return _DataResponse()


class _ConnectorSslCapture:
    """gdf_by_concat stand-in snapshotting the connector ssl at call time."""

    def __init__(self) -> None:
        self.ssl: Any = "NOT_CALLED"

    async def __call__(self, url: str, session: Any, **kwargs: Any) -> str:
        connector = getattr(session, "connector", None)
        self.ssl = getattr(connector, "_ssl", "NO_CONNECTOR")
        return "sentinel"


@pytest.mark.asyncio
async def test_env_config_reaches_library_data_path(_transport_env: None) -> None:
    """The library-built data session honors BOTH env knobs: the connector
    carries ssl=False (W4-5) and a real data request carries the custom
    User-Agent (W2-10)."""
    # (a) connector ssl introspection on the get_gdf-owned session.
    capture = _ConnectorSslCapture()
    with patch("restgdf.utils.getgdf.gdf_by_concat", new=capture):
        await get_gdf("https://example.com/layer/0", session=None)
    assert capture.ssl is False

    # (b) the env user_agent reaches the wire headers of a real data request.
    session = _RecordingDataSession('{"type":"FeatureCollection","features":[]}')
    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        return_value=object(),
    ):
        await get_sub_gdf(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
        )
    assert session.post_calls, "expected the data request to be issued"
    _url, kwargs = session.post_calls[0]
    assert kwargs["headers"]["User-Agent"] == _CUSTOM_UA


@pytest.mark.asyncio
async def test_env_config_reaches_token_mint_and_data_request(
    _transport_env: None,
) -> None:
    """A token mint honors verify_ssl, and a token-attached data request honors
    both the forwarded verify_ssl and the env user_agent."""
    inner = _RecordingInnerSession()
    token_session = ArcGISTokenSession(
        session=inner,
        credentials=AGOLUserPass(username="u", password="p"),
        verify_ssl=False,  # set consistently with the data-path connector
    )

    # Token mint: the /generateToken POST forwards the session verify_ssl.
    await token_session.update_token()
    assert inner.mint_kwargs["ssl"] is False

    # Token-attached data request through the real _arcgis_request seam: the
    # env user_agent (via default_headers) reaches the wire, and verify_ssl is
    # forwarded onto the data call too. The freshly minted token has a
    # far-future expiry, so this issues no second mint.
    await _arcgis_request(
        token_session,
        "https://example.com/layer/0/query",
        {"where": "1=1"},
        headers=default_headers(None),
    )
    assert inner.data_kwargs["ssl"] is False
    assert inner.data_kwargs["headers"]["User-Agent"] == _CUSTOM_UA
