from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from litellm.models.team import LiteLLM_TeamTable
from litellm.proxy._types import LiteLLM_UserTable, LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.auth.model_scope import (
    MODEL_SCOPE_ORGLESS_PROXY_TEAM,
    MODEL_SCOPE_TEAM_ONLY,
    XHUB_MODEL_SCOPE_KEY,
    XHUB_CREATOR_ROLE_KEY,
    XHUB_TEAM_CREATED_BY_ROLE_KEY,
    get_model_scope,
    team_can_use_model_info,
)


def _team(team_id: str, organization_id=None, creator_role=LitellmUserRoles.PROXY_ADMIN.value):
    return LiteLLM_TeamTable(
        team_id=team_id,
        organization_id=organization_id,
        metadata={XHUB_TEAM_CREATED_BY_ROLE_KEY: creator_role},
    )


def test_proxy_admin_orgless_model_only_allows_proxy_admin_orgless_team():
    model_info = {
        "db_model": True,
        XHUB_MODEL_SCOPE_KEY: MODEL_SCOPE_ORGLESS_PROXY_TEAM,
        XHUB_CREATOR_ROLE_KEY: LitellmUserRoles.PROXY_ADMIN.value,
    }

    assert team_can_use_model_info(model_info, _team("standalone")) is True
    assert team_can_use_model_info(model_info, _team("org-team", organization_id="org-a")) is False
    assert (
        team_can_use_model_info(
            model_info,
            _team("user-team", creator_role=LitellmUserRoles.INTERNAL_USER.value),
        )
        is False
    )
    assert team_can_use_model_info(model_info, LiteLLM_TeamTable(team_id="legacy", metadata={})) is False
    assert team_can_use_model_info({**model_info, XHUB_CREATOR_ROLE_KEY: "internal_user"}, _team("standalone")) is False
    assert team_can_use_model_info({**model_info, XHUB_CREATOR_ROLE_KEY: None}, _team("standalone")) is False
    assert team_can_use_model_info({**model_info, "team_id": "owner"}, _team("standalone")) is False


def test_team_scoped_model_only_allows_exact_team():
    model_info = {
        "db_model": True,
        "team_id": "team-a",
        XHUB_MODEL_SCOPE_KEY: MODEL_SCOPE_TEAM_ONLY,
    }

    assert team_can_use_model_info(model_info, _team("team-a", organization_id="org-a")) is True
    assert team_can_use_model_info(model_info, _team("team-b", organization_id="org-a")) is False
    assert team_can_use_model_info(model_info, _team("team-b")) is False


def test_legacy_db_models_infer_restricted_scope():
    assert get_model_scope({"db_model": True}) == MODEL_SCOPE_ORGLESS_PROXY_TEAM
    assert get_model_scope({"db_model": True, "team_id": "team-a"}) == MODEL_SCOPE_TEAM_ONLY


def test_config_models_keep_existing_global_semantics():
    model_info = {"id": "config-model", "db_model": False}

    assert get_model_scope(model_info) is None
    assert team_can_use_model_info(model_info, _team("org-team", organization_id="org-a")) is True


def test_team_id_alone_is_always_team_only():
    model_info = {"id": "team-model", "team_id": "team-a"}

    assert get_model_scope(model_info) == MODEL_SCOPE_TEAM_ONLY
    assert team_can_use_model_info(model_info, _team("team-a")) is True
    assert team_can_use_model_info(model_info, _team("team-b")) is False


def _deployments():
    return [
        {"model_name": "shared", "model_info": {"id": "orgless", "db_model": True,
         XHUB_MODEL_SCOPE_KEY: MODEL_SCOPE_ORGLESS_PROXY_TEAM,
         XHUB_CREATOR_ROLE_KEY: LitellmUserRoles.PROXY_ADMIN.value}},
        {"model_name": "private", "model_info": {"id": "private", "db_model": True,
         "team_id": "owner", XHUB_MODEL_SCOPE_KEY: MODEL_SCOPE_TEAM_ONLY}},
    ]


def test_explicit_team_allowlist_still_inherits_orgless_proxy_model():
    from litellm.proxy.proxy_server import _add_team_models_to_all_models

    teams = [
        _team("eligible"),
        _team("org", organization_id="org-a"),
        _team("other", creator_role=LitellmUserRoles.INTERNAL_USER.value),
        _team("owner", organization_id="org-a"),
    ]
    for team in teams:
        team.models = ["something-else"]
    teams[-1].models = ["private"]
    router = MagicMock()
    router.get_model_list.side_effect = lambda model_name=None, team_id=None: (
        _deployments() if model_name is None else
        [_deployments()[1]] if model_name == "private" and team_id == "owner" else []
    )

    access = _add_team_models_to_all_models(teams, router)
    assert access["orgless"] == {"eligible"}
    assert access["private"] == {"owner"}


@pytest.mark.asyncio
async def test_proxy_admin_lists_unassigned_and_all_team_models_without_eligible_teams():
    from litellm.proxy.proxy_server import get_all_team_and_direct_access_models

    router = MagicMock()
    router.get_model_ids.return_value = ["orgless"]
    models = _deployments()
    with patch("litellm.proxy.proxy_server.get_all_team_models", new_callable=AsyncMock, return_value={}):
        result = await get_all_team_and_direct_access_models(
            UserAPIKeyAuth(user_role=LitellmUserRoles.PROXY_ADMIN), MagicMock(), router, models
        )
    assert {row["model_info"]["id"] for row in result} == {"orgless", "private"}
    assert all(row["model_info"]["direct_access"] for row in result)


@pytest.mark.asyncio
async def test_restricted_caller_does_not_inherit_unassigned_model_without_eligible_team():
    from litellm.proxy.proxy_server import get_all_team_and_direct_access_models

    user = UserAPIKeyAuth(user_id="user", user_role=LitellmUserRoles.INTERNAL_USER)
    user_row = LiteLLM_UserTable(user_id="user", teams=["org"])
    with (
        patch("litellm.proxy.proxy_server.UserRepository") as users,
        patch("litellm.proxy.proxy_server.get_all_team_models", new_callable=AsyncMock, return_value={}),
        patch("litellm.proxy.proxy_server.get_direct_access_models", return_value=["orgless"]),
    ):
        users.return_value.table.find_unique = AsyncMock(return_value=user_row)
        result = await get_all_team_and_direct_access_models(user, MagicMock(), MagicMock(), _deployments())
    assert result == []


@pytest.mark.asyncio
async def test_orgless_proxy_model_default_grant_only_for_eligible_team():
    from litellm.proxy.auth.auth_checks import can_team_access_model
    from litellm.proxy._types import ProxyException

    router = MagicMock()
    router.has_model_id.return_value = False
    router.get_model_list.side_effect = lambda model_name=None, team_id=None: (
        [_deployments()[0]] if model_name == "shared" else []
    )
    eligible = _team("eligible")
    eligible.models = ["other"]
    assert await can_team_access_model("shared", eligible, router) is True
    for denied in (
        _team("org", organization_id="org-a"),
        _team("other", creator_role=LitellmUserRoles.INTERNAL_USER.value),
    ):
        denied.models = ["other"]
        with pytest.raises(ProxyException):
            await can_team_access_model("shared", denied, router)
