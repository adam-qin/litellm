"""
Tests for the XHub LDAP authentication backend (litellm/proxy/auth/ldap_auth.py).

These tests exercise the LDAP login support added to the XHub admin "Security
Settings" screen:

* ``LDAPSettings`` - the stored configuration model (defaults to the
  ``internal_user`` role so LDAP users get Create/Delete/View permissions).
* ``authenticate_with_ldap`` - the LDAP bind flow (mocked ``ldap3``).
* ``get_ldap_config`` - loads/decrypts the stored config; returns ``None`` when
  disabled or unset.
* ``ensure_internal_user_for_ldap`` - finds or provisions the ``internal_user``.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litellm.proxy.auth.ldap_auth import (
    LDAPSettings,
    authenticate_with_ldap,
    ensure_internal_user_for_ldap,
    get_ldap_config,
)


class _LDAPEntry:
    """A minimal stand-in for an ``ldap3`` Entry object.

    Using a plain object (instead of a MagicMock) keeps the
    ``entry.__getattribute__(attribute)`` access the code relies on predictable.
    """

    def __init__(self, dn: str, attributes: dict):
        self.entry_dn = dn
        self.__dict__.update(attributes)

    def __getattribute__(self, name):
        return object.__getattribute__(self, name)


def _make_mock_ldap3(entries, *, user_bind_raises=None):
    """Build a fake ``ldap3`` module.

    ``Connection`` returns the search connection first, then (optionally) raises
    for the user bind to simulate invalid credentials.
    """
    mock_ldap3 = MagicMock()
    mock_ldap3.escape_filter_chars.side_effect = lambda value: value.replace("*", r"\2a").replace("(", r"\28").replace(")", r"\29")
    server = MagicMock()
    mock_ldap3.Server.return_value = server

    search_conn = MagicMock()
    search_conn.entries = entries

    user_conn = MagicMock()
    if user_bind_raises is not None:
        mock_ldap3.Connection.side_effect = [search_conn, user_bind_raises]
    else:
        mock_ldap3.Connection.side_effect = [search_conn, user_conn]
    return mock_ldap3


# ---------------------------------------------------------------------------
# LDAPSettings model
# ---------------------------------------------------------------------------
def test_ldap_settings_defaults():
    cfg = LDAPSettings()
    assert cfg.enabled is False
    assert cfg.user_search_filter == "(uid={username})"
    assert cfg.user_email_attribute == "mail"
    assert cfg.use_ssl is True


def test_ldap_settings_default_user_role_is_internal_user():
    # Product requirement: LDAP users are granted internal_user
    # (Create / Delete / View) by default.
    assert LDAPSettings().default_user_role == "internal_user"


def test_ldap_settings_uses_custom_values():
    cfg = LDAPSettings(
        enabled=True,
        server_url="ldaps://ldap.example.com:636",
        bind_dn="cn=svc,dc=example,dc=com",
        bind_password="secret",
        user_search_base="dc=example,dc=com",
        user_search_filter="(sAMAccountName={username})",
        user_email_attribute="userPrincipalName",
        default_user_role="internal_user",
        use_ssl=False,
    )
    assert cfg.enabled is True
    assert cfg.user_search_filter == "(sAMAccountName={username})"
    assert cfg.user_email_attribute == "userPrincipalName"
    assert cfg.use_ssl is False


# ---------------------------------------------------------------------------
# authenticate_with_ldap
# ---------------------------------------------------------------------------
def test_authenticate_with_ldap_success():
    entry = _LDAPEntry(
        dn="uid=alice,dc=example,dc=com",
        attributes={"mail": ["alice@example.com"]},
    )
    mock_ldap3 = _make_mock_ldap3([entry])

    cfg = LDAPSettings(
        enabled=True,
        server_url="ldaps://ldap.example.com:636",
        user_search_base="dc=example,dc=com",
    )
    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        result = asyncio.run(authenticate_with_ldap("alice", "secret", cfg))

    assert result is not None
    assert result["user_email"] == "alice@example.com"
    assert result["external_subject"] == "uid=alice,dc=example,dc=com"
    assert result["user_id"].startswith("ldap:")
    mock_ldap3.Server.assert_called_once()
    # The second Connection binds as the resolved user DN with the password.
    mock_ldap3.Connection.assert_called_with(
        mock_ldap3.Server.return_value,
        user="uid=alice,dc=example,dc=com",
        password="secret",
        auto_bind=True,
    )


def test_authenticate_with_ldap_user_not_found():
    mock_ldap3 = _make_mock_ldap3([])
    cfg = LDAPSettings(enabled=True, server_url="ldaps://x", user_search_base="dc=x")
    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        result = asyncio.run(authenticate_with_ldap("nobody", "pw", cfg))
    assert result is None


def test_authenticate_with_ldap_invalid_password_returns_none():
    entry = _LDAPEntry(
        dn="uid=bob,dc=example,dc=com",
        attributes={"mail": ["bob@example.com"]},
    )
    mock_ldap3 = _make_mock_ldap3([entry], user_bind_raises=Exception("invalid credentials"))
    cfg = LDAPSettings(enabled=True, server_url="ldaps://x", user_search_base="dc=x")
    with patch.dict(sys.modules, {"ldap3": mock_ldap3}):
        result = asyncio.run(authenticate_with_ldap("bob", "wrong", cfg))
    assert result is None


def test_authenticate_with_ldap_missing_dependency_returns_none():
    class _MissingModule:
        def __getattr__(self, name):  # noqa: B902
            raise ImportError(f"No module named 'ldap3'")

    with patch.dict(sys.modules, {"ldap3": _MissingModule()}):
        result = asyncio.run(
            authenticate_with_ldap("alice", "secret", LDAPSettings(enabled=True))
        )
    assert result is None


def test_authenticate_with_ldap_empty_inputs_returns_none():
    cfg = LDAPSettings(enabled=True, server_url="ldaps://x", user_search_base="dc=x")
    assert asyncio.run(authenticate_with_ldap("", "", cfg)) is None
    assert asyncio.run(authenticate_with_ldap("alice", "pw", LDAPSettings(enabled=True, server_url=""))) is None


# ---------------------------------------------------------------------------
# get_ldap_config
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_ldap_config_enabled():
    record = MagicMock()
    record.ldap_settings = {
        "enabled": True,
        "server_url": "ldaps://ldap.example.com:636",
        "user_search_base": "dc=example,dc=com",
        "bind_password": "secret",
    }
    repo = MagicMock()
    repo.table.find_unique = AsyncMock(return_value=record)

    fake_proxy_config = MagicMock()
    # Identity decrypt keeps the test focused on parsing/masking.
    fake_proxy_config._decrypt_and_set_db_env_variables.side_effect = (
        lambda environment_variables: environment_variables
    )

    with patch(
        "litellm.repositories.table_repositories.LDAPConfigRepository",
        return_value=repo,
    ), patch("litellm.proxy.proxy_server.proxy_config", fake_proxy_config):
        cfg = await get_ldap_config(MagicMock())

    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.server_url == "ldaps://ldap.example.com:636"
    assert cfg.bind_password == "secret"


@pytest.mark.asyncio
async def test_get_ldap_config_disabled_returns_none():
    record = MagicMock()
    record.ldap_settings = {"enabled": False, "server_url": "ldaps://x"}
    repo = MagicMock()
    repo.table.find_unique = AsyncMock(return_value=record)
    with patch(
        "litellm.repositories.table_repositories.LDAPConfigRepository",
        return_value=repo,
    ):
        cfg = await get_ldap_config(MagicMock())
    assert cfg is None


@pytest.mark.asyncio
async def test_get_ldap_config_no_record_returns_none():
    repo = MagicMock()
    repo.table.find_unique = AsyncMock(return_value=None)
    with patch(
        "litellm.repositories.table_repositories.LDAPConfigRepository",
        return_value=repo,
    ):
        assert await get_ldap_config(MagicMock()) is None


# ---------------------------------------------------------------------------
# ensure_internal_user_for_ldap
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ensure_internal_user_returns_existing():
    existing = MagicMock()
    existing.user_email = "alice@example.com"
    user_repo = MagicMock()
    user_repo.table.find_first = AsyncMock(return_value=existing)

    with patch(
        "litellm.proxy.auth.auth_utils.UserRepository", return_value=user_repo
    ), patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.new_user",
        new=AsyncMock(),
    ), patch(
        "litellm.proxy.auth.auth_utils.UserAPIKeyAuth", MagicMock()
    ), patch(
        "litellm.proxy.auth.auth_utils.LitellmUserRoles", MagicMock()
    ), patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.NewUserRequest",
        MagicMock(),
    ):
        result = await ensure_internal_user_for_ldap(
            "alice",
            {"user_id": "alice@example.com", "user_email": "alice@example.com"},
            MagicMock(),
        )
    assert result is existing


@pytest.mark.asyncio
async def test_ensure_internal_user_creates_when_missing():
    user_repo = MagicMock()
    created = MagicMock()
    created.user_email = "alice@example.com"
    # First lookup misses, second (after create) hits.
    user_repo.table.find_first = AsyncMock(side_effect=[None, created])

    new_user = AsyncMock()
    with patch(
        "litellm.proxy.auth.auth_utils.UserRepository", return_value=user_repo
    ), patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.new_user", new_user
    ), patch(
        "litellm.proxy.auth.auth_utils.UserAPIKeyAuth", MagicMock()
    ), patch(
        "litellm.proxy.auth.auth_utils.LitellmUserRoles", MagicMock()
    ), patch(
        "litellm.proxy.management_endpoints.internal_user_endpoints.NewUserRequest",
        MagicMock(),
    ):
        result = await ensure_internal_user_for_ldap(
            "alice",
            {"user_id": "alice@example.com", "user_email": "alice@example.com"},
            MagicMock(),
        )

    new_user.assert_awaited_once()
    assert result is created
