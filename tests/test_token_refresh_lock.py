"""BL-03 red tests: single-flight token refresh.

Per MASTER-PLAN §5 BL-03 (MASTER-PLAN.md:109-110):

> BL-03. Single-flight token refresh. Guard
>   ``ArcGISTokenSession.update_token_if_needed`` with an
>   ``asyncio.Lock`` (lazily initialized, per instance) and double-check
>   the "needs update" predicate inside the lock so concurrent callers
>   collapse onto one ``/generateToken`` POST.

These tests target the public ``update_token_if_needed`` coroutine on
:class:`restgdf.utils.token.ArcGISTokenSession`. Before the green commit
they fail because concurrent callers all observe the "needs update"
predicate and each triggers their own ``update_token`` POST.
"""

from __future__ import annotations

import asyncio
import copy

import pytest

from restgdf._models.credentials import AGOLUserPass
from restgdf.utils.token import ArcGISTokenSession


class _FakeSession:
    """Stand-in aiohttp session — never actually POSTs."""


def _make_session() -> ArcGISTokenSession:
    return ArcGISTokenSession(
        session=_FakeSession(),  # type: ignore[arg-type]
        credentials=AGOLUserPass(username="alice", password="hunter2"),
    )


@pytest.mark.asyncio
async def test_concurrent_update_token_if_needed_refreshes_once(monkeypatch):
    """N coroutines racing on an expired token must trigger exactly one
    ``update_token`` call."""
    s = _make_session()

    calls = 0

    async def fake_update_token(self):
        nonlocal calls
        calls += 1
        # Simulate a slow /generateToken round-trip so the lock matters.
        await asyncio.sleep(0.01)
        self.token = "t"
        self.expires = 9_999_999_999_999  # far future (ms epoch)

    monkeypatch.setattr(ArcGISTokenSession, "update_token", fake_update_token)

    await asyncio.gather(*(s.update_token_if_needed() for _ in range(25)))
    assert calls == 1, f"expected exactly one refresh under lock, got {calls}"


@pytest.mark.asyncio
async def test_refresh_lock_is_per_instance(monkeypatch):
    """Two distinct sessions must not share a refresh lock."""
    s1 = _make_session()
    s2 = _make_session()

    async def fake_update_token(self):
        await asyncio.sleep(0)
        self.token = "t"
        self.expires = 9_999_999_999_999

    monkeypatch.setattr(ArcGISTokenSession, "update_token", fake_update_token)

    await asyncio.gather(s1.update_token_if_needed(), s2.update_token_if_needed())
    # Each session lazily attaches its own lock; they must be distinct
    # objects so refreshes on unrelated sessions don't serialize.
    lock1 = getattr(s1, "_refresh_lock", None)
    lock2 = getattr(s2, "_refresh_lock", None)
    assert lock1 is not None and lock2 is not None
    assert lock1 is not lock2


@pytest.mark.asyncio
async def test_refresh_lock_released_on_exception(monkeypatch):
    """If ``update_token`` raises, the lock must not stay held."""
    s = _make_session()

    calls = 0

    async def flaky_update_token(self):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        self.token = "t"
        self.expires = 9_999_999_999_999

    monkeypatch.setattr(ArcGISTokenSession, "update_token", flaky_update_token)

    with pytest.raises(RuntimeError):
        await s.update_token_if_needed()
    # A retry must be able to acquire the lock and complete.
    await s.update_token_if_needed()
    assert calls == 2
    lock = getattr(s, "_refresh_lock", None)
    assert lock is not None
    assert not lock.locked()


def test_refresh_lock_is_lazy_and_excluded_from_repr_copy_pickle():
    """The lock must be init=False / repr=False / compare=False and not
    break ``repr``, ``copy.copy``, or equality with a fresh instance."""
    s = _make_session()
    # Field must exist and default to None pre-use (lazy init).
    assert hasattr(s, "_refresh_lock")
    assert s._refresh_lock is None
    # Lock should not appear in repr (search for the field-assignment
    # fragment so the test module's own path doesn't trigger a false
    # positive on bare "_refresh_lock" substring).
    assert "_refresh_lock=" not in repr(s)
    # copy.copy must not fail (locks aren't copyable, so they must be
    # excluded / None at construction).
    copy.copy(s)
    # Two freshly-constructed instances must compare equal via dataclass
    # __eq__ (lock is compare=False).
    other = _make_session()
    # Note: aiohttp session identity differs, but dataclass compare is
    # field-by-field. Replace session fields to make them equal.
    other.session = s.session
    other.credentials = s.credentials
    assert s == other
