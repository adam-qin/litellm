"""Behavior pins for ``proxy_server.py`` model routes.

Pins (PR2):
    - GET /v1/models
    - GET /models
    - GET /v1/models/{model_id}
    - GET /models/{model_id}
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import litellm
from litellm.proxy import proxy_server

from .conftest import normalize  # type: ignore[import-not-found]


def _stub_model_info_response(
    model_id: str = "gpt-4", provider: str = "openai"
) -> dict:
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": provider,
    }


@pytest.fixture
def patched_models(monkeypatch):
    """Stub router + utility helpers used by the /models routes."""
    from litellm.proxy import utils as proxy_utils

    router = MagicMock()
    router.get_fully_blocked_model_names = MagicMock(return_value=set())
    router.get_model_names = MagicMock(return_value=["gpt-4", "claude-sonnet"])
    router.get_model_access_groups = MagicMock(return_value={})

    deployment = MagicMock()
    deployment.litellm_params.model = "gpt-4"
    router.get_deployment_by_model_group_name = MagicMock(return_value=deployment)

    monkeypatch.setattr(proxy_server, "llm_router", router)
    monkeypatch.setattr(proxy_server, "prisma_client", MagicMock())

    async def _fake_get_available_models_for_user(**kwargs):
        return ["gpt-4", "claude-sonnet"]

    monkeypatch.setattr(
        proxy_utils,
        "get_available_models_for_user",
        _fake_get_available_models_for_user,
    )

    def _fake_create_model_info_response(model_id, provider="openai", **kwargs):
        return _stub_model_info_response(model_id=model_id, provider=provider)

    monkeypatch.setattr(
        proxy_utils, "create_model_info_response", _fake_create_model_info_response
    )

    monkeypatch.setattr(proxy_utils, "validate_model_access", lambda **kwargs: None)

    monkeypatch.setattr(
        litellm,
        "get_llm_provider",
        lambda model: (model, "openai", None, None),
    )

    return router


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_get_models_happy_path(client, auth_as, patched_models, path):
    """Pins: ``GET /v1/models``, ``GET /models``."""
    with auth_as():
        response = client.get(path)
    assert response.status_code == 200
    assert normalize(response.json()) == {
        "data": [
            {
                "id": "<VOLATILE>",
                "object": "model",
                "created": "<VOLATILE>",
                "owned_by": "openai",
            },
            {
                "id": "<VOLATILE>",
                "object": "model",
                "created": "<VOLATILE>",
                "owned_by": "openai",
            },
        ],
        "object": "list",
    }


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_get_models_invalid_scope_returns_400(client, auth_as, patched_models, path):
    """Pins: ``GET /v1/models``, ``GET /models`` (error path: invalid scope)."""
    with auth_as():
        response = client.get(path, params={"scope": "not-a-real-scope"})
    assert response.status_code == 400
    assert "Invalid scope parameter" in str(response.json())


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_model_list_omits_models_denied_by_inference(client, auth_as, patched_models, monkeypatch, path):
    from litellm.proxy._types import LitellmUserRoles, ProxyErrorTypes, ProxyException
    from litellm.proxy.auth import auth_checks

    async def check_model(*, model, valid_token, **kwargs):
        if model == "gpt-4":
            raise ProxyException(
                message="Team is outside the model ownership scope.",
                type=ProxyErrorTypes.team_model_access_denied,
                param="model",
                code=403,
            )

    check = AsyncMock(side_effect=check_model)
    monkeypatch.setattr(auth_checks, "can_key_call_resolved_model", check)
    with auth_as(LitellmUserRoles.INTERNAL_USER, team_id="team-a"):
        response = client.get(path)
    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()["data"]] == ["claude-sonnet"]
    assert [call.kwargs["model"] for call in check.await_args_list] == ["gpt-4", "claude-sonnet"]


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_model_list_rejects_cross_team_query_for_admin_role_virtual_key(client, auth_as, patched_models, path):
    from litellm.proxy._types import LitellmUserRoles

    with auth_as(LitellmUserRoles.PROXY_ADMIN, team_id="team-a"):
        response = client.get(path, params={"team_id": "team-b"})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_model_list_expand_does_not_bypass_virtual_key_scope(
    client, auth_as, patched_models, monkeypatch, path
):
    from litellm.proxy._types import LitellmUserRoles, ProxyErrorTypes, ProxyException
    from litellm.proxy.auth import auth_checks

    async def deny_model(*, model, **kwargs):
        if model == "gpt-4":
            raise ProxyException(
                message="not allowed", type=ProxyErrorTypes.team_model_access_denied,
                param="model", code=403,
            )

    monkeypatch.setattr(auth_checks, "can_key_call_resolved_model", AsyncMock(side_effect=deny_model))
    with auth_as(LitellmUserRoles.PROXY_ADMIN, team_id="team-a"):
        response = client.get(path, params={"scope": "expand"})
    assert response.status_code == 200
    assert "gpt-4" not in [entry["id"] for entry in response.json()["data"]]


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_model_list_rejects_unbound_virtual_key_team_query(client, auth_as, patched_models, path):
    from litellm.proxy._types import LitellmUserRoles

    with auth_as(LitellmUserRoles.PROXY_ADMIN):
        response = client.get(path, params={"team_id": "team-a"})
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/v1/models", "/models"])
def test_model_list_includes_own_team_public_model_only_when_callable(
    client, auth_as, patched_models, monkeypatch, path
):
    from litellm.proxy._types import LitellmUserRoles, ProxyErrorTypes, ProxyException
    from litellm.proxy.auth import auth_checks

    patched_models.get_model_list.return_value = [
        {"model_name": "gpt-team-a", "model_info": {
            "team_id": "team-a", "xhub_model_scope": "team_only", "team_public_model_name": "gpt-team-a"
        }},
        {"model_name": "gpt-team-b", "model_info": {
            "team_id": "team-b", "xhub_model_scope": "team_only", "team_public_model_name": "gpt-team-b"
        }},
    ]

    async def check_model(*, model, **kwargs):
        if model == "gpt-4":
            raise ProxyException(
                message="not allowed", type=ProxyErrorTypes.team_model_access_denied,
                param="model", code=403,
            )

    monkeypatch.setattr(auth_checks, "can_key_call_resolved_model", AsyncMock(side_effect=check_model))
    with auth_as(LitellmUserRoles.INTERNAL_USER, team_id="team-a"):
        response = client.get(path)
    assert response.status_code == 200
    names = [entry["id"] for entry in response.json()["data"]]
    assert "gpt-team-a" in names
    assert "gpt-team-b" not in names
    assert "gpt-4" not in names


@pytest.mark.parametrize("path", ["/v1/models/gpt-4", "/models/gpt-4"])
def test_model_info_hides_model_denied_by_inference(client, auth_as, patched_models, monkeypatch, path):
    from litellm.proxy import utils as proxy_utils
    from litellm.proxy._types import LitellmUserRoles, ProxyErrorTypes, ProxyException
    from litellm.proxy.auth import auth_checks

    def validate_model(*, model_id, available_models):
        if model_id not in available_models:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Model not found")

    monkeypatch.setattr(proxy_utils, "validate_model_access", validate_model)

    async def check_model(*, model, **kwargs):
        if model == "gpt-4":
            raise ProxyException(
                message="Team is outside the model ownership scope.",
                type=ProxyErrorTypes.team_model_access_denied,
                param="model",
                code=403,
            )

    monkeypatch.setattr(auth_checks, "can_key_call_resolved_model", AsyncMock(side_effect=check_model))
    with auth_as(LitellmUserRoles.INTERNAL_USER, team_id="team-a"):
        response = client.get(path)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_explicit_team_id_rejects_other_team_even_with_cached_models():
    from fastapi import HTTPException
    from litellm.proxy._types import UserAPIKeyAuth
    from litellm.proxy.utils import get_available_models_for_user

    key = UserAPIKeyAuth(api_key="sk-test-key", team_id="team-a", team_models=[])
    with pytest.raises(HTTPException) as exc:
        await get_available_models_for_user(
            user_api_key_dict=key,
            llm_router=None,
            general_settings={},
            user_model=None,
            team_id="team-b",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_explicit_team_id_fails_closed_without_validation_dependencies():
    from fastapi import HTTPException
    from litellm.proxy._types import UserAPIKeyAuth
    from litellm.proxy.utils import get_available_models_for_user

    key = UserAPIKeyAuth(api_key="sk-test-key", team_id="team-a", team_models=[])
    with pytest.raises(HTTPException) as exc:
        await get_available_models_for_user(
            user_api_key_dict=key,
            llm_router=None,
            general_settings={},
            user_model=None,
            team_id="team-a",
        )
    assert exc.value.status_code == 503


@pytest.mark.parametrize("path", ["/v1/models/gpt-4", "/models/gpt-4"])
def test_get_model_by_id_happy_path(client, auth_as, patched_models, path):
    """Pins: ``GET /v1/models/{model_id}``, ``GET /models/{model_id}``."""
    with auth_as():
        response = client.get(path)
    assert response.status_code == 200
    assert normalize(response.json()) == {
        "id": "<VOLATILE>",
        "object": "model",
        "created": "<VOLATILE>",
        "owned_by": "openai",
    }


@pytest.mark.parametrize("path", ["/v1/models/missing", "/models/missing"])
def test_get_model_by_id_not_found(client, auth_as, patched_models, path):
    """Pins: ``GET /v1/models/{model_id}``, ``GET /models/{model_id}`` (error: 404)."""
    patched_models.get_deployment_by_model_group_name = MagicMock(return_value=None)
    with auth_as():
        response = client.get(path)
    assert response.status_code == 404
    assert "not found" in response.text.lower()
