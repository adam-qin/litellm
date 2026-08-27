import ast
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path

import litellm
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.common_utils.team_scope import (
    access_group_fully_in_scope,
    access_group_in_scope,
    assert_access_group_fully_in_scope,
    assert_access_group_in_scope,
    assert_existing_key_in_scope,
    assert_system_endpoint_disabled_when_scoped,
    assert_team_in_scope,
    filter_assigned_team_ids_for_response,
    get_caller_allowed_team_ids,
    get_effective_allowed_team_ids,
    is_team_in_scope,
    is_team_scoped_instance,
    team_id_in_filter,
)


def _enable_scope(team_ids):
    litellm.xhub_team_scope = {
        "enabled": True,
        "allowed_team_ids": list(team_ids),
    }


def _disable_scope():
    litellm.xhub_team_scope = None


@pytest.fixture(autouse=True)
def reset_team_scope():
    original = getattr(litellm, "xhub_team_scope", None)
    yield
    litellm.xhub_team_scope = original


def test_disabled_scope_preserves_unscoped_behavior():
    _disable_scope()
    admin = UserAPIKeyAuth(user_role=LitellmUserRoles.PROXY_ADMIN)

    assert is_team_scoped_instance() is False
    assert get_effective_allowed_team_ids(admin) is None
    assert is_team_in_scope(None, admin) is True
    assert is_team_in_scope("any-team", admin) is True


def test_enabled_scope_intersects_instance_and_caller():
    _enable_scope(["team-a", "team-b"])
    admin = UserAPIKeyAuth(user_role=LitellmUserRoles.PROXY_ADMIN)
    member = UserAPIKeyAuth(
        user_role=LitellmUserRoles.INTERNAL_USER,
        metadata={"available_teams": ["team-b", "team-c"]},
    )

    assert is_team_scoped_instance() is True
    assert get_effective_allowed_team_ids(admin) == {"team-a", "team-b"}
    assert get_effective_allowed_team_ids(member) == {"team-b"}
    assert is_team_in_scope("team-a", admin) is True
    assert is_team_in_scope("team-c", admin) is False
    assert is_team_in_scope("team-a", member) is False


def test_proxy_admin_cannot_query_out_of_scope_or_global_keys():
    _enable_scope(["team-a", "team-b"])
    admin = UserAPIKeyAuth(user_role=LitellmUserRoles.PROXY_ADMIN)

    assert is_team_in_scope(None, admin) is False
    with pytest.raises(HTTPException) as extra:
        assert_existing_key_in_scope({"team_id": "team-c"}, admin)
    assert extra.value.status_code == 403
    with pytest.raises(HTTPException):
        assert_team_in_scope(None, admin)


def test_non_admin_without_trusted_team_identity_has_empty_scope():
    _enable_scope(["team-a"])
    user = UserAPIKeyAuth(user_role=LitellmUserRoles.INTERNAL_USER)

    assert get_caller_allowed_team_ids(user) == set()
    assert get_effective_allowed_team_ids(user) == set()
    assert is_team_in_scope("team-a", user) is False


def test_team_id_in_filter_is_sorted():
    assert team_id_in_filter({"team-b", "team-a"}) == {
        "team_id": {"in": ["team-a", "team-b"]}
    }


def _key_filter_source() -> str:
    path = (
        Path(__file__).resolve().parents[2]
        / "litellm"
        / "proxy"
        / "management_endpoints"
        / "key_management_endpoints.py"
    )
    return path.read_text(encoding="utf-8")


def test_key_list_uses_scoped_team_id_in_filter_instead_of_first_team():
    source = _key_filter_source()
    assert "team_id = next(iter(effective_team_ids)" not in source
    assert "scoped_team_ids = sorted(effective_team_ids)" in source
    assert '{"team_id": {"in": scoped_team_ids}}' in source
    tree = ast.parse(source)
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_build_key_filter_conditions" in function_names
    assert "_can_user_query_key_info" in function_names
    assert "assert_existing_key_in_scope" in source
    assert 'is_team_in_scope(getattr(key_info, "team_id", None)' in source


def test_access_group_scope_helpers():
    _enable_scope(["team-a", "team-b"])
    admin = UserAPIKeyAuth(user_role=LitellmUserRoles.PROXY_ADMIN)

    allowed = get_effective_allowed_team_ids(admin)
    assert access_group_in_scope(["team-a", "team-c"], allowed) is True
    assert access_group_in_scope(["team-c"], allowed) is False
    assert access_group_in_scope([], allowed) is False
    assert access_group_fully_in_scope(["team-a"], allowed) is True
    assert access_group_fully_in_scope(["team-a", "team-c"], allowed) is False
    assert access_group_fully_in_scope([], allowed) is False
    assert filter_assigned_team_ids_for_response(["team-a", "team-c"], allowed) == ["team-a"]

    with pytest.raises(HTTPException) as extra:
        assert_access_group_in_scope(["team-c"], admin)
    assert extra.value.status_code == 403
    with pytest.raises(HTTPException) as extra:
        assert_access_group_fully_in_scope(["team-a", "team-c"], admin)
    assert extra.value.status_code == 403
    assert extra.value.detail == "Access group is assigned to teams outside this instance's allowed scope"


def test_system_endpoint_disabled_when_scoped():
    _enable_scope(["team-a"])
    with pytest.raises(HTTPException) as extra:
        assert_system_endpoint_disabled_when_scoped()
    assert extra.value.status_code == 403

    _disable_scope()
    assert_system_endpoint_disabled_when_scoped()


def _repo_source(relative: str) -> str:
    return (Path(__file__).resolve().parents[2] / relative).read_text(encoding="utf-8")


def test_access_group_endpoints_apply_team_scope():
    source = _repo_source("litellm/proxy/management_endpoints/access_group_endpoints.py")
    assert "assigned_teams_has_some_filter" in source
    assert "assert_access_group_in_scope" in source
    assert "assert_access_group_fully_in_scope" in source
    assert "assigned_team_ids is required when XHub Team scope is enabled" in source
    assert "filter_assigned_team_ids_for_response" in source


def test_byok_hides_unscoped_models_on_team_scoped_instance():
    source = _repo_source("litellm/proxy/proxy_server.py")
    assert "def _byok_row_outside_caller_teams" in source
    assert "return is_team_scoped_instance()" in source


def test_user_list_requires_in_scope_team_admin_when_scoped():
    source = _repo_source("litellm/proxy/management_endpoints/internal_user_endpoints.py")
    assert "async def _caller_is_in_scope_team_admin" in source
    assert "Only proxy admins and team admins can list users when XHub Team scope is enabled." in source
    assert "if effective:\n        return organization_ids" not in source
