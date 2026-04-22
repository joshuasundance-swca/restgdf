"""Tests for R-15 (referer binding) and R-17 (SecretStr repr audit).

R-15: When ``AuthConfig.referer`` or ``TokenSessionConfig.referer`` is set,
``token_request_payload`` must include ``"referer": <value>`` so the
``/generateToken`` endpoint binds the token to that origin.

R-17: A static scan ensures that no logging call in ``token.py``
interpolates raw credential values (password, token, secret).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import SecretStr

from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig
from restgdf.utils.token import ArcGISTokenSession


# ── R-15: referer binding ─────────────────────────────────────────
class TestRefererBinding:
    def _make_session(self, *, referer: str | None = None):
        """Helper that builds an ArcGISTokenSession with optional referer."""
        from unittest.mock import MagicMock

        kwargs = {
            "credentials": AGOLUserPass(username="u", password=SecretStr("p")),
            "token_url": "https://www.arcgis.com/sharing/rest/generateToken",
        }
        if referer:
            kwargs["referer"] = referer
        config = TokenSessionConfig(**kwargs)
        return ArcGISTokenSession(
            session=MagicMock(),
            config=config,
        )

    def test_referer_absent_by_default(self):
        ts = self._make_session()
        payload = ts.token_request_payload
        assert "referer" not in payload

    def test_referer_present_when_configured(self):
        ts = self._make_session(referer="https://myapp.example.com")
        payload = ts.token_request_payload
        assert payload["referer"] == "https://myapp.example.com"

    def test_referer_overrides_client_requestip(self):
        """When referer is set, client should be 'referer', not 'requestip'."""
        ts = self._make_session(referer="https://myapp.example.com")
        payload = ts.token_request_payload
        assert payload["client"] == "referer"


# ── R-17: SecretStr repr audit (static AST scan) ─────────────────
_TOKEN_PY = Path(__file__).resolve().parent.parent / "restgdf" / "utils" / "token.py"

# Attribute names that MUST NOT appear as format-args in logging calls
_FORBIDDEN_ATTRS = frozenset(
    {
        "password",
        "token",
        "secret",
        "get_secret_value",
    },
)


class _LogArgVisitor(ast.NodeVisitor):
    """Walk the AST looking for logging calls that interpolate secrets."""

    def __init__(self):
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call):  # noqa: N802
        # Detect _auth_logger.<level>(...) or logging.<level>(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr in (
            "debug",
            "info",
            "warning",
            "error",
            "critical",
        ):
            # Check all positional args beyond the format string
            for arg in node.args[1:]:
                self._check_expr(arg, node.lineno)
            # Check keyword values too
            for kw in node.keywords:
                self._check_expr(kw.value, node.lineno)
        self.generic_visit(node)

    def _check_expr(self, expr: ast.expr, lineno: int):
        """Flag any Attribute access to a forbidden name."""
        if isinstance(expr, ast.Attribute) and expr.attr in _FORBIDDEN_ATTRS:
            self.violations.append(
                (lineno, f"logging arg references .{expr.attr}"),
            )
        # Also check if it's a call to .get_secret_value()
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr in _FORBIDDEN_ATTRS
        ):
            self.violations.append(
                (lineno, f"logging arg calls .{expr.func.attr}()"),
            )


class TestSecretStrReprAudit:
    def test_no_credential_interpolation_in_logging(self):
        """Static AST check: no logging call in token.py interpolates secrets."""
        source = _TOKEN_PY.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_TOKEN_PY))
        visitor = _LogArgVisitor()
        visitor.visit(tree)
        if visitor.violations:
            msg = "Secret interpolation found in logging calls:\n"
            for lineno, desc in visitor.violations:
                msg += f"  line {lineno}: {desc}\n"
            pytest.fail(msg)
