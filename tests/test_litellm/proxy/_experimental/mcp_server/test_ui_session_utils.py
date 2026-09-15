import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from litellm.constants import UI_SESSION_TOKEN_TEAM_ID
from litellm.proxy._types import UserAPIKeyAuth

from litellm.proxy._experimental.mcp_server.ui_session_utils import (
    build_effective_auth_contexts,
    clone_user_api_key_auth_with_team,
    get_selected_team_id_from_request_data,
    resolve_selected_ui_session_team_auth,
    resolve_ui_session_team_ids,
)


def test_get_selected_team_id_from_request_data_prefers_litellm_metadata():
    request_data = {
        "litellm_metadata": {"team_id": "team-litellm"},
        "metadata": {"team_id": "team-legacy"},
    }

    assert get_selected_team_id_from_request_data(request_data) == "team-litellm"
    assert get_selected_team_id_from_request_data({"metadata": {"team_id": "team-legacy"}}) == "team-legacy"
    assert get_selected_team_id_from_request_data({"litellm_metadata": {"team_id": ""}}) is None


def test_clone_user_api_key_auth_with_team_creates_independent_copy():
    original = UserAPIKeyAuth(team_id="team-original", user_id="user-123")

    cloned = clone_user_api_key_auth_with_team(original, "team-override")

    assert cloned is not original
    assert cloned.team_id == "team-override"
    assert original.team_id == "team-original"


@pytest.mark.asyncio
async def test_resolve_ui_session_team_ids_returns_unique_ids(monkeypatch):
    user_auth = UserAPIKeyAuth(
        team_id=UI_SESSION_TOKEN_TEAM_ID,
        user_id="user-1",
    )

    fake_user = SimpleNamespace(
        teams=["team-a", "team-b", "team-a", "", None, "team-c"]
    )

    monkeypatch.setattr(
        "litellm.proxy.auth.auth_checks.get_user_object",
        AsyncMock(return_value=fake_user),
    )

    import litellm.proxy.proxy_server as proxy_server

    monkeypatch.setattr(proxy_server, "prisma_client", object())
    monkeypatch.setattr(proxy_server, "proxy_logging_obj", None)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", None)

    team_ids = await resolve_ui_session_team_ids(user_auth)

    assert team_ids == ["team-a", "team-b", "team-c"]


@pytest.mark.asyncio
async def test_resolve_ui_session_team_ids_short_circuits_when_not_ui_session():
    normal_user = UserAPIKeyAuth(team_id="regular-team", user_id="user-1")

    result = await resolve_ui_session_team_ids(normal_user)

    assert result == []


@pytest.mark.asyncio
async def test_resolve_selected_ui_session_team_auth_only_allows_member_team(monkeypatch):
    user_auth = UserAPIKeyAuth(team_id=UI_SESSION_TOKEN_TEAM_ID, user_id="user-selected")
    resolver = AsyncMock(return_value=["team-a", "team-b"])
    team_object = SimpleNamespace(
        team_alias="Team B",
        spend=12.5,
        tpm_limit=1000,
        rpm_limit=20,
        max_budget=100.0,
        soft_budget=80.0,
        models=["team-model"],
        blocked=False,
        metadata={"environment": "test"},
        object_permission_id="permission-1",
        object_permission={"mcp_servers": []},
        litellm_model_table=SimpleNamespace(model_aliases={"alias": "team-model"}),
    )
    team_membership = SimpleNamespace(
        spend=3.5,
        safe_get_team_member_rpm_limit=lambda: 5,
        safe_get_team_member_tpm_limit=lambda: 200,
    )
    monkeypatch.setattr(
        "litellm.proxy._experimental.mcp_server.ui_session_utils.resolve_ui_session_team_ids",
        resolver,
    )
    monkeypatch.setattr(
        "litellm.proxy.auth.auth_checks.get_team_object",
        AsyncMock(return_value=team_object),
    )
    monkeypatch.setattr(
        "litellm.proxy.auth.auth_checks.get_team_membership",
        AsyncMock(return_value=team_membership),
    )
    import litellm.proxy.proxy_server as proxy_server

    monkeypatch.setattr(proxy_server, "prisma_client", object())
    monkeypatch.setattr(proxy_server, "proxy_logging_obj", None)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", None)

    selected = await resolve_selected_ui_session_team_auth(user_auth, "team-b")
    rejected = await resolve_selected_ui_session_team_auth(user_auth, "team-outsider")

    assert selected.team_id == "team-b"
    assert selected.team_tpm_limit == 1000
    assert selected.team_rpm_limit == 20
    assert selected.team_models == ["team-model"]
    assert selected.team_model_aliases == {"alias": "team-model"}
    assert selected.team_member_rpm_limit == 5
    assert selected.team_member_tpm_limit == 200
    assert selected is not user_auth
    assert rejected is user_auth


@pytest.mark.asyncio
async def test_resolve_selected_ui_session_team_auth_fails_closed_without_membership(monkeypatch):
    user_auth = UserAPIKeyAuth(team_id=UI_SESSION_TOKEN_TEAM_ID, user_id="user-selected")
    monkeypatch.setattr(
        "litellm.proxy._experimental.mcp_server.ui_session_utils.resolve_ui_session_team_ids",
        AsyncMock(return_value=["team-a"]),
    )
    monkeypatch.setattr(
        "litellm.proxy.auth.auth_checks.get_team_object",
        AsyncMock(return_value=SimpleNamespace(team_id="team-a")),
    )
    monkeypatch.setattr(
        "litellm.proxy.auth.auth_checks.get_team_membership",
        AsyncMock(return_value=None),
    )
    import litellm.proxy.proxy_server as proxy_server

    monkeypatch.setattr(proxy_server, "prisma_client", object())
    monkeypatch.setattr(proxy_server, "proxy_logging_obj", None)
    monkeypatch.setattr(proxy_server, "user_api_key_cache", None)

    result = await resolve_selected_ui_session_team_auth(user_auth, "team-a")

    assert result is user_auth
    assert result.team_id == UI_SESSION_TOKEN_TEAM_ID


@pytest.mark.asyncio
async def test_resolve_selected_ui_session_team_auth_does_not_override_regular_key(monkeypatch):
    user_auth = UserAPIKeyAuth(team_id="regular-team", user_id="user-selected")
    resolver = AsyncMock(return_value=["team-other"])
    monkeypatch.setattr(
        "litellm.proxy._experimental.mcp_server.ui_session_utils.resolve_ui_session_team_ids",
        resolver,
    )

    result = await resolve_selected_ui_session_team_auth(user_auth, "team-other")

    assert result is user_auth
    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_effective_auth_contexts_returns_cloned_contexts(monkeypatch):
    user_auth = UserAPIKeyAuth(team_id=UI_SESSION_TOKEN_TEAM_ID, user_id="user-42")

    mock_resolve = AsyncMock(return_value=["team-one", "team-two"])
    monkeypatch.setattr(
        "litellm.proxy._experimental.mcp_server.ui_session_utils.resolve_ui_session_team_ids",
        mock_resolve,
    )

    contexts = await build_effective_auth_contexts(user_auth)

    assert [ctx.team_id for ctx in contexts] == ["team-one", "team-two"]
    assert all(ctx is not user_auth for ctx in contexts)
    mock_resolve.assert_awaited_once_with(user_auth)


@pytest.mark.asyncio
async def test_build_effective_auth_contexts_returns_original_when_no_resolution(
    monkeypatch,
):
    user_auth = UserAPIKeyAuth(team_id="existing-team", user_id="user-7")

    mock_resolve = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "litellm.proxy._experimental.mcp_server.ui_session_utils.resolve_ui_session_team_ids",
        mock_resolve,
    )

    contexts = await build_effective_auth_contexts(user_auth)

    assert contexts == [user_auth]
    mock_resolve.assert_awaited_once_with(user_auth)


@pytest.mark.asyncio
async def test_build_effective_auth_contexts_handles_unpicklable_parent_span(
    monkeypatch,
):
    class DummySpan:
        def __init__(self) -> None:
            self._lock = threading.RLock()

    parent_span = DummySpan()
    user_auth = UserAPIKeyAuth(
        team_id=UI_SESSION_TOKEN_TEAM_ID,
        user_id="user-span",
        parent_otel_span=parent_span,
    )

    mock_resolve = AsyncMock(return_value=["team-span"])
    monkeypatch.setattr(
        "litellm.proxy._experimental.mcp_server.ui_session_utils.resolve_ui_session_team_ids",
        mock_resolve,
    )

    contexts = await build_effective_auth_contexts(user_auth)

    assert contexts[0].team_id == "team-span"
    assert contexts[0].parent_otel_span is parent_span
