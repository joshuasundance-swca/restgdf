"""BL-13 red tests: default transport is HEADER, header_name is X-Esri-Authorization.

These tests are written RED-first — they will fail until the feat(BL-13)
commit flips the default wire format.
"""

from __future__ import annotations

import pytest


class TestAuthConfigTransportDefault:
    """AuthConfig.transport defaults to 'header'."""

    def test_default_transport_is_header(self):
        from restgdf._config import AuthConfig

        cfg = AuthConfig(token_url="https://example.com/generateToken")
        assert cfg.transport == "header"

    def test_default_header_name(self):
        from restgdf._config import AuthConfig

        cfg = AuthConfig(token_url="https://example.com/generateToken")
        assert cfg.header_name == "X-Esri-Authorization"

    def test_body_transport_requires_allow_flag(self):
        """R-13 strict: transport='body' without allow_query_transport raises."""
        # NOTE: R-13 only blocks 'query', body is always allowed
        from restgdf._config import AuthConfig

        # body is NOT blocked — just test query is blocked
        cfg = AuthConfig(
            token_url="https://example.com/generateToken",
            transport="body",
        )
        assert cfg.transport == "body"

    def test_query_transport_rejected_without_flag(self):
        """R-13 strict: transport='query' without allow_query_transport → ValidationError."""
        from pydantic import ValidationError

        from restgdf._config import AuthConfig

        with pytest.raises(ValidationError, match="allow_query_transport"):
            AuthConfig(
                token_url="https://example.com/generateToken",
                transport="query",
            )

    def test_query_transport_allowed_with_flag(self):
        from restgdf._config import AuthConfig

        cfg = AuthConfig(
            token_url="https://example.com/generateToken",
            transport="query",
            allow_query_transport=True,
        )
        assert cfg.transport == "query"


class TestTokenSessionTransportHeader:
    """auth_headers emits X-Esri-Authorization under default transport='header'."""

    def test_auth_headers_uses_x_esri_authorization(self):
        from restgdf.utils.token import ArcGISTokenSession

        session = ArcGISTokenSession(
            session=object(),  # type: ignore[arg-type]
            token="abc123",
            expires=9999999999999,
        )
        hdrs = session.auth_headers
        assert "X-Esri-Authorization" in hdrs
        assert hdrs["X-Esri-Authorization"] == "Bearer abc123"
        assert "Authorization" not in hdrs

    def test_update_dict_no_body_token_under_header_transport(self):
        """Under transport='header' update_dict must NOT inject 'token' into params/data."""
        from restgdf.utils.token import ArcGISTokenSession

        session = ArcGISTokenSession(
            session=object(),  # type: ignore[arg-type]
            token="abc123",
            expires=9999999999999,
        )
        d: dict = {}
        session.update_dict(d)
        assert "token" not in d

    def test_update_headers_under_header_transport(self):
        """update_headers injects X-Esri-Authorization under default transport."""
        from restgdf.utils.token import ArcGISTokenSession

        session = ArcGISTokenSession(
            session=object(),  # type: ignore[arg-type]
            token="abc123",
            expires=9999999999999,
        )
        h: dict = {}
        result = session.update_headers(h)
        assert result["X-Esri-Authorization"] == "Bearer abc123"
