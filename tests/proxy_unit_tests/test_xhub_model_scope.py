from litellm.models.team import LiteLLM_TeamTable
from litellm.proxy._types import LitellmUserRoles
from litellm.proxy.auth.model_scope import (
    MODEL_SCOPE_ORGLESS_PROXY_TEAM,
    MODEL_SCOPE_TEAM_ONLY,
    XHUB_MODEL_SCOPE_KEY,
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
