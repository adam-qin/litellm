"""Fail-closed authorization and redaction for the XHub audit reader."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from litellm.constants import LITELLM_PROXY_MASTER_KEY_ALIAS
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth, hash_token
from litellm.proxy.management_endpoints.xhub_audit_log_endpoints import (
    _audit_log_to_dict,
    _require_audit_reader,
    _sanitize_value,
    get_xhub_audit_log_by_id,
    get_xhub_audit_logs,
)


def _audit_request(bearer="sk-ui-session", claims=None, signing_key="test-master"):
    headers = [(b"authorization", f"Bearer {bearer}".encode())] if bearer else []
    if claims is not None:
        cookie = jwt.encode(claims, signing_key, algorithm="HS256")
        headers.append((b"cookie", f"token={cookie}".encode()))
    return Request({"type": "http", "method": "GET", "path": "/xhub/audit-logs", "headers": headers})


def _ui_claims(**overrides):
    claims = {
        "key": "sk-ui-session",
        "user_id": "admin-user",
        "user_role": LitellmUserRoles.PROXY_ADMIN.value,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    claims.update(overrides)
    return claims


def test_virtual_proxy_admin_cannot_read_audit_logs():
    virtual = UserAPIKeyAuth(api_key="sk-virtual-test", user_role=LitellmUserRoles.PROXY_ADMIN)
    with pytest.raises(HTTPException) as error:
        _require_audit_reader(virtual, _audit_request())
    assert error.value.status_code == 403


def test_real_master_can_read_audit_logs():
    master = UserAPIKeyAuth(api_key=LITELLM_PROXY_MASTER_KEY_ALIAS, user_role=LitellmUserRoles.PROXY_ADMIN)
    _require_audit_reader(master, _audit_request(bearer="master-placeholder"))


def test_server_authenticated_dashboard_admin_session_can_read_audit_logs():
    dashboard_admin = UserAPIKeyAuth(
        api_key=hash_token("sk-ui-session"), user_id="admin-user",
        team_id="litellm-dashboard", user_role=LitellmUserRoles.PROXY_ADMIN,
    )
    with patch("litellm.proxy.proxy_server.master_key", "test-master"):
        _require_audit_reader(dashboard_admin, _audit_request(claims=_ui_claims()))


@pytest.mark.parametrize(
    "bearer,claims,signing_key",
    [
        ("sk-ui-session", None, "test-master"),
        ("sk-ui-session", _ui_claims(), "other-master"),
        ("sk-other", _ui_claims(), "test-master"),
        ("sk-ui-session", _ui_claims(user_id="other-user"), "test-master"),
        ("sk-ui-session", _ui_claims(user_role="internal_user"), "test-master"),
        ("sk-ui-session", _ui_claims(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), "test-master"),
    ],
)
def test_dashboard_claims_fail_closed(bearer, claims, signing_key):
    admin = UserAPIKeyAuth(
        api_key=hash_token("sk-ui-session"), user_id="admin-user", team_id="litellm-dashboard",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )
    with patch("litellm.proxy.proxy_server.master_key", "test-master"):
        with pytest.raises(HTTPException) as error:
            _require_audit_reader(admin, _audit_request(bearer, claims, signing_key))
    assert error.value.status_code == 403


def test_virtual_proxy_admin_with_dashboard_marker_but_no_ui_cookie_is_rejected():
    virtual = UserAPIKeyAuth(
        api_key="sk-virtual-test", user_id="admin-user", team_id="litellm-dashboard",
        key_type="management", user_role=LitellmUserRoles.PROXY_ADMIN,
    )
    with pytest.raises(HTTPException) as error:
        _require_audit_reader(virtual, _audit_request(bearer="sk-virtual-test"))
    assert error.value.status_code == 403


def test_team_key_with_proxy_admin_role_is_rejected():
    virtual = UserAPIKeyAuth(
        api_key="sk-virtual-test",
        team_id="team-A1",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )
    with pytest.raises(HTTPException) as error:
        _require_audit_reader(virtual, _audit_request())
    assert error.value.status_code == 403


def test_nested_secrets_and_legacy_actor_key_are_redacted():
    raw = {
        "changed_by_api_key": "sk-legacy-actor",
        "before_value": json.dumps({"team_id": "team-A", "config": [{"api_key": "sk-sensitive", "secret": "private"}]}),
        "updated_values": {"password": "private", "metadata": {"authorization": "Bearer private"}},
    }
    safe = _audit_log_to_dict(raw)
    assert safe["changed_by_api_key"] == hashlib.sha256(b"sk-legacy-actor").hexdigest()
    assert safe["before_value"]["team_id"] == "team-A"
    assert safe["before_value"]["config"][0]["api_key"] == "[REDACTED]"
    assert safe["updated_values"]["metadata"]["authorization"] == "[REDACTED]"
    assert "sk-sensitive" not in json.dumps(safe)
    assert _sanitize_value({"token": "test-token"})["token"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_detail_returns_404_when_not_found():
    master = UserAPIKeyAuth(api_key=LITELLM_PROXY_MASTER_KEY_ALIAS, user_role=LitellmUserRoles.PROXY_ADMIN)
    db = MagicMock()
    db.db.litellm_auditlog.find_unique = AsyncMock(return_value=None)
    with patch("litellm.proxy.proxy_server.prisma_client", db):
        with pytest.raises(HTTPException) as error:
            await get_xhub_audit_log_by_id("missing", _audit_request(), master)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_detail_denies_virtual_admin_before_database_access():
    virtual = UserAPIKeyAuth(api_key="sk-virtual-test", user_role=LitellmUserRoles.PROXY_ADMIN)
    with pytest.raises(HTTPException) as error:
        await get_xhub_audit_log_by_id("missing", _audit_request(), virtual)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_list_maps_database_outage_to_503():
    master = UserAPIKeyAuth(api_key=LITELLM_PROXY_MASTER_KEY_ALIAS, user_role=LitellmUserRoles.PROXY_ADMIN)
    db = MagicMock()
    db.db.litellm_auditlog.find_many = AsyncMock(side_effect=ConnectionError("database unavailable"))
    db.attempt_db_reconnect = AsyncMock(return_value=False)
    with patch("litellm.proxy.proxy_server.prisma_client", db):
        with pytest.raises(HTTPException) as error:
            await get_xhub_audit_logs(request=_audit_request(), user_api_key_dict=master)
    assert error.value.status_code == 503
