"""Community XHub audit-log read endpoints.

This module intentionally does not depend on the optional Enterprise router. Audit
records are still stored by the existing LiteLLM audit logger, but reads are
exposed through an XHub-owned namespace with explicit master or UI admin session checks.
"""

import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from litellm.constants import LITELLM_PROXY_MASTER_KEY_ALIAS, UI_SESSION_TOKEN_TEAM_ID
from litellm.proxy._types import (
    CommonProxyErrors,
    LitellmUserRoles,
    UserAPIKeyAuth,
    hash_token,
)
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from litellm.proxy.db.exception_handler import (
    PrismaDBExceptionHandler,
    call_with_db_reconnect_retry,
)

router = APIRouter(prefix="/xhub", tags=["XHub Audit Logging"])

_ALLOWED_SORT_FIELDS = {"updated_at", "changed_by", "action", "table_name", "object_id"}
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "auth_header",
    "authorization",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
)
_MASK = "[REDACTED]"
_KEY_HASH = re.compile(r"^[0-9a-fA-F]{64}$")


def _require_audit_reader(user_api_key_dict: UserAPIKeyAuth, request: Request) -> None:
    """Accept only the real master credential or a signed, bound UI admin session.

    The Dashboard team id, key type and role can also be set on virtual keys;
    none of those properties alone proves that the caller logged in through UI.
    """
    if user_api_key_dict.api_key == LITELLM_PROXY_MASTER_KEY_ALIAS:
        return

    from litellm.proxy.proxy_server import general_settings, master_key

    auth_header_name = (general_settings or {}).get("litellm_key_header_name", "Authorization")
    authorization = request.headers.get(auth_header_name, "")
    bearer = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    cookie = request.cookies.get("token")
    if cookie and bearer and isinstance(master_key, str) and master_key:
        try:
            claims = jwt.decode(cookie, master_key, algorithms=["HS256"], options={"require": ["exp"]})
        except jwt.PyJWTError:
            claims = {}
        if (
            isinstance(claims.get("key"), str)
            and hmac.compare_digest(claims["key"], bearer)
            and user_api_key_dict.api_key == hash_token(bearer)
            and claims.get("user_id")
            and claims["user_id"] == user_api_key_dict.user_id
            and claims.get("user_role") == LitellmUserRoles.PROXY_ADMIN.value
            and user_api_key_dict.user_role == LitellmUserRoles.PROXY_ADMIN
            and user_api_key_dict.team_id == UI_SESSION_TOKEN_TEAM_ID
        ):
            return

    raise HTTPException(
        status_code=403,
        detail="XHub audit logs require the configured master credential or a Dashboard admin session",
    )


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_value(value: Any, key: Optional[str] = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return _MASK
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return value
        if isinstance(decoded, (dict, list)):
            return _sanitize_value(decoded)
    return value


def _safe_key_hash(value: Any) -> str:
    """Support historical plaintext audit actors without returning the plaintext."""
    if not value:
        return ""
    text = str(value)
    return text.lower() if _KEY_HASH.fullmatch(text) else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _audit_log_to_dict(audit_log: Any) -> Dict[str, Any]:
    if hasattr(audit_log, "model_dump"):
        data = audit_log.model_dump()
    elif isinstance(audit_log, dict):
        data = dict(audit_log)
    else:
        data = {
            field: getattr(audit_log, field)
            for field in (
                "id",
                "updated_at",
                "changed_by",
                "changed_by_api_key",
                "action",
                "table_name",
                "object_id",
                "before_value",
                "updated_values",
            )
            if hasattr(audit_log, field)
        }
    data["changed_by_api_key"] = _safe_key_hash(data.get("changed_by_api_key"))
    data["before_value"] = _sanitize_value(data.get("before_value"))
    data["updated_values"] = _sanitize_value(data.get("updated_values"))
    return data


def _json_field_or_condition(json_key: str, value: str) -> Dict[str, Any]:
    return {
        "OR": [
            {"before_value": {"path": [json_key], "string_contains": value}},
            {"updated_values": {"path": [json_key], "string_contains": value}},
        ]
    }


@router.get("/audit-logs")
async def get_xhub_audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    changed_by: Optional[str] = Query(None),
    changed_by_api_key: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    table_name: Optional[str] = Query(None),
    object_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    object_team_id: Optional[str] = Query(None),
    object_key_hash: Optional[str] = Query(None),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc"),
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    _require_audit_reader(user_api_key_dict, request)
    if sort_by not in _ALLOWED_SORT_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid audit-log sort field")
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid audit-log sort order")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must not be after end_date")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=500,
            detail={"message": CommonProxyErrors.db_not_connected_error.value},
        )

    where: Dict[str, Any] = {}
    for field, value in (
        ("changed_by", changed_by),
        ("changed_by_api_key", changed_by_api_key),
        ("action", action),
        ("table_name", table_name),
        ("object_id", object_id),
    ):
        if value:
            where[field] = value
    if start_date or end_date:
        where["updated_at"] = {
            **({"gte": start_date} if start_date else {}),
            **({"lte": end_date} if end_date else {}),
        }
    if object_team_id:
        where["AND"] = where.get("AND", []) + [_json_field_or_condition("team_id", object_team_id)]
    if object_key_hash:
        where["AND"] = where.get("AND", []) + [_json_field_or_condition("token", object_key_hash)]

    try:
        logs = await call_with_db_reconnect_retry(
            prisma_client,
            lambda: prisma_client.db.litellm_auditlog.find_many(
                where=where,
                order={sort_by: sort_order},
                skip=(page - 1) * page_size,
                take=page_size,
            ),
            reason="xhub_audit_logs_find_many_failure",
        )
        total = await call_with_db_reconnect_retry(
            prisma_client,
            lambda: prisma_client.db.litellm_auditlog.count(where=where),
            reason="xhub_audit_logs_count_failure",
        )
    except Exception as error:
        if PrismaDBExceptionHandler.is_database_service_unavailable_error_in_chain(error):
            raise HTTPException(
                status_code=503,
                detail="Audit log database is temporarily unavailable. Please retry shortly.",
            ) from None
        raise HTTPException(status_code=500, detail="Failed to query audit logs") from None
    return {
        "audit_logs": [_audit_log_to_dict(log) for log in logs or []],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/audit-logs/{audit_log_id}")
async def get_xhub_audit_log_by_id(
    audit_log_id: str,
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    _require_audit_reader(user_api_key_dict, request)
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(
            status_code=500,
            detail={"message": CommonProxyErrors.db_not_connected_error.value},
        )
    try:
        audit_log = await call_with_db_reconnect_retry(
            prisma_client,
            lambda: prisma_client.db.litellm_auditlog.find_unique(
                where={"id": audit_log_id}
            ),
            reason="xhub_audit_log_find_unique_failure",
        )
    except Exception as error:
        if PrismaDBExceptionHandler.is_database_service_unavailable_error_in_chain(error):
            raise HTTPException(
                status_code=503,
                detail="Audit log database is temporarily unavailable. Please retry shortly.",
            ) from None
        raise HTTPException(status_code=500, detail="Failed to query audit log") from None
    if audit_log is None:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return _audit_log_to_dict(audit_log)
