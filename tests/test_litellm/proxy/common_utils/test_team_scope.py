import pytest
from fastapi import HTTPException

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


def test_orgless_proxy_admin_model_rejects_org_and_non_admin_teams():
    model_info = {"db_model": True, XHUB_MODEL_SCOPE_KEY: MODEL_SCOPE_ORGLESS_PROXY_TEAM}

    assert team_can_use_model_info(model_info, _team("standalone")) is True
    assert team_can_use_model_info(model_info, _team("org-team", organization_id="org-a")) is False
    assert (
        team_can_use_model_info(
            model_info,
            _team("user-team", creator_role=LitellmUserRoles.INTERNAL_USER.value),
        )
        is False
    )


def test_team_only_model_requires_exact_team_id():
    model_info = {
        "db_model": True,
        "team_id": "team-a",
        XHUB_MODEL_SCOPE_KEY: MODEL_SCOPE_TEAM_ONLY,
    }

    assert team_can_use_model_info(model_info, _team("team-a", organization_id="org-a")) is True
    assert team_can_use_model_info(model_info, _team("team-b", organization_id="org-a")) is False


def test_legacy_db_models_are_restricted_and_config_models_remain_global():
    assert get_model_scope({"db_model": True}) == MODEL_SCOPE_ORGLESS_PROXY_TEAM
    assert get_model_scope({"db_model": True, "team_id": "team-a"}) == MODEL_SCOPE_TEAM_ONLY
    assert get_model_scope({"db_model": False}) is None
    assert team_can_use_model_info({"db_model": False}, _team("org-team", "org-a")) is True


def test_scope_failure_is_explicit_for_unknown_scope():
    model_info = {XHUB_MODEL_SCOPE_KEY: "unknown_scope"}
    assert team_can_use_model_info(model_info, _team("team-a")) is False
