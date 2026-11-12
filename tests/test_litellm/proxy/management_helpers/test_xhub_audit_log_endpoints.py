"""Fail-closed authorization and redaction for the XHub audit reader."""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from litellm.constants import LITELLM_PROXY_MASTER_KEY_ALIAS
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.management_endpoints.xhub_audit_log_endpoints import (
    _audit_log_to_dict,
    _require_audit_reader,
    _sanitize_value,
    get_xhub_audit_log_by_id,
    get_xhub_audit_logs,
)


def test_virtual_proxy_admin_cannot_read_audit_logs():
    virtual = UserAPIKeyAuth(api_key="sk-virtual-test", user_role=LitellmUserRoles.PROXY_ADMIN)
    with pytest.raises(HTTPException) as error:
        _require_audit_reader(virtual)
    assert error.value.status_code == 403


def test_real_master_can_read_audit_logs():
    master = UserAPIKeyAuth(api_key=LITELLM_PROXY_MASTER_KEY_ALIAS, user_role=LitellmUserRoles.PROXY_ADMIN)
    _require_audit_reader(master)


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
            await get_xhub_audit_log_by_id("missing", master)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_detail_denies_virtual_admin_before_database_access():
    virtual = UserAPIKeyAuth(api_key="sk-virtual-test", user_role=LitellmUserRoles.PROXY_ADMIN)
    with pytest.raises(HTTPException) as error:
        await get_xhub_audit_log_by_id("missing", virtual)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_list_maps_database_outage_to_503():
    master = UserAPIKeyAuth(api_key=LITELLM_PROXY_MASTER_KEY_ALIAS, user_role=LitellmUserRoles.PROXY_ADMIN)
    db = MagicMock()
    db.db.litellm_auditlog.find_many = AsyncMock(side_effect=ConnectionError("database unavailable"))
    db.attempt_db_reconnect = AsyncMock(return_value=False)
    with patch("litellm.proxy.proxy_server.prisma_client", db):
        with pytest.raises(HTTPException) as error:
            await get_xhub_audit_logs(user_api_key_dict=master)
    assert error.value.status_code == 503
