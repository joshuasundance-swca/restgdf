"""W2-11 (AUTH-04/CONFIG-02) + W3-3 (CONFIG-02 token half): opt-in AuthConfig wiring.

The hybrid decision (master plan §Decision record): ``AuthConfig`` is wired into a
token session ONLY via an opt-in factory, never implicitly through
``ArcGISTokenSession.__post_init__``. Two coordinated surfaces:

* ``TokenSessionConfig.from_auth_config(auth_config, credentials)`` (W2-11) —
  projects an ``AuthConfig`` namespace onto a validated ``TokenSessionConfig``.
* ``ArcGISTokenSession.from_config(session, credentials, config=...)`` (W3-3
  token half) — the opt-in classmethod; ``config`` defaults to
  ``get_config().auth`` but is only read when the classmethod is invoked, never
  at import time and never in ``__post_init__``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic import SecretStr

from restgdf._config import AuthConfig
from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig
from restgdf.utils.token import ArcGISTokenSession


def _creds():
    return AGOLUserPass(username="u", password=SecretStr("p"))


class TestFromAuthConfigFactory:
    def test_projects_refresh_knobs_and_transport(self):
        auth = AuthConfig(
            token_url="https://enterprise.example.com/portal/sharing/rest/generateToken",
            transport="body",
            refresh_leeway_s=300.0,
            clock_skew_s=45.0,
        )
        tsc = TokenSessionConfig.from_auth_config(auth, _creds())
        assert isinstance(tsc, TokenSessionConfig)
        assert tsc.refresh_leeway_seconds == 300
        assert tsc.clock_skew_seconds == 45
        assert tsc.transport == "body"
        assert tsc.token_url.endswith("/generateToken")
        # Effective refresh threshold reflects the AuthConfig values.
        assert tsc.refresh_leeway_seconds + tsc.clock_skew_seconds == 345

    def test_none_token_url_falls_back_to_default(self):
        auth = AuthConfig()  # token_url defaults to None
        tsc = TokenSessionConfig.from_auth_config(auth, _creds())
        assert tsc.token_url.startswith("https://")
        assert tsc.token_url.endswith("/generateToken")

    def test_referer_prefers_auth_config_then_credentials(self):
        auth = AuthConfig(referer="https://portal.example.com")
        tsc = TokenSessionConfig.from_auth_config(auth, _creds())
        assert tsc.referer == "https://portal.example.com"

        cred = AGOLUserPass(
            username="u",
            password=SecretStr("p"),
            referer="https://cred.example.com",
        )
        tsc2 = TokenSessionConfig.from_auth_config(AuthConfig(), cred)
        assert tsc2.referer == "https://cred.example.com"


class TestFromConfigClassmethod:
    def test_explicit_config_threads_refresh_window(self):
        ts = ArcGISTokenSession.from_config(
            session=MagicMock(),
            credentials=_creds(),
            config=AuthConfig(refresh_leeway_s=300.0, clock_skew_s=45.0),
        )
        assert isinstance(ts, ArcGISTokenSession)
        assert isinstance(ts.config, TokenSessionConfig)
        # threshold = leeway + skew derived from the AuthConfig instance.
        assert ts.token_refresh_threshold == 345

    def test_config_none_reads_get_config_auth(self):
        from restgdf._config import reset_config_cache

        reset_config_cache()
        ts = ArcGISTokenSession.from_config(session=MagicMock(), credentials=_creds())
        # Default AuthConfig: refresh_leeway_s=120 + clock_skew_s=30 -> 150.
        assert ts.token_refresh_threshold == 150

    def test_transport_and_header_name_threaded(self):
        ts = ArcGISTokenSession.from_config(
            session=MagicMock(),
            credentials=_creds(),
            config=AuthConfig(transport="body", header_name="X-Custom-Auth"),
        )
        assert ts.config is not None
        assert ts.config.transport == "body"
        assert ts.config.header_name == "X-Custom-Auth"


class TestPlainConstructionDoesNotConsumeConfig:
    def test_plain_session_keeps_dataclass_default_threshold(self):
        """No implicit get_config() read: a plain session keeps the 60s default."""
        ts = ArcGISTokenSession(session=MagicMock(), credentials=_creds())
        # A bare ArcGISTokenSession with only credentials derives its window from
        # the dataclass default (60), NOT from get_config().auth (which would be
        # 150). Proves __post_init__ never reaches into the process-global config.
        assert ts.token_refresh_threshold == 60

    def test_from_config_is_a_classmethod(self):
        assert callable(ArcGISTokenSession.from_config)
