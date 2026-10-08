"""XHub model ownership and team-scope enforcement helpers."""

from typing import Any, Dict, Iterable, Optional

from litellm.models.team import LiteLLM_TeamTable
from litellm.proxy._types import LitellmUserRoles

XHUB_MODEL_SCOPE_KEY = "xhub_model_scope"
XHUB_CREATOR_ROLE_KEY = "xhub_creator_role"
XHUB_TEAM_CREATED_BY_KEY = "xhub_created_by"
XHUB_TEAM_CREATED_BY_ROLE_KEY = "xhub_created_by_role"

MODEL_SCOPE_ORGLESS_PROXY_TEAM = "orgless_proxy_team"
MODEL_SCOPE_TEAM_ONLY = "team_only"


def normalize_optional_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def normalized_role(value: Any) -> Optional[str]:
    if isinstance(value, LitellmUserRoles):
        return value.value
    return normalize_optional_id(value)


def stamp_model_scope(model_info: Any, creator_role: Any) -> None:
    """Persist the immutable XHub scope for a newly created DB deployment."""
    team_id = normalize_optional_id(getattr(model_info, "team_id", None))
    setattr(model_info, "team_id", team_id)
    setattr(
        model_info,
        XHUB_MODEL_SCOPE_KEY,
        MODEL_SCOPE_TEAM_ONLY if team_id is not None else MODEL_SCOPE_ORGLESS_PROXY_TEAM,
    )
    setattr(model_info, XHUB_CREATOR_ROLE_KEY, normalized_role(creator_role))


def get_model_scope(model_info: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(model_info, dict):
        return None
    scope = normalize_optional_id(model_info.get(XHUB_MODEL_SCOPE_KEY))
    if scope is not None:
        return scope
    if normalize_optional_id(model_info.get("team_id")) is not None:
        return MODEL_SCOPE_TEAM_ONLY
    if model_info.get("db_model") is True:
        return MODEL_SCOPE_ORGLESS_PROXY_TEAM
    return None


def is_proxy_admin_created_team(team: LiteLLM_TeamTable) -> bool:
    metadata = team.metadata if isinstance(team.metadata, dict) else {}
    return normalized_role(metadata.get(XHUB_TEAM_CREATED_BY_ROLE_KEY)) == LitellmUserRoles.PROXY_ADMIN.value


def team_can_use_model_info(model_info: Optional[Dict[str, Any]], team: LiteLLM_TeamTable) -> bool:
    """Return whether a team is inside a deployment's hard ownership scope."""
    scope = get_model_scope(model_info)
    if scope is None:
        return True

    model_team_id = normalize_optional_id((model_info or {}).get("team_id"))
    if scope == MODEL_SCOPE_TEAM_ONLY:
        return model_team_id is not None and model_team_id == team.team_id

    if scope == MODEL_SCOPE_ORGLESS_PROXY_TEAM:
        # An unstamped legacy model is not proof of Proxy-Admin ownership.
        # Keep it visible to Proxy Admin, but deny the default team grant.
        creator_role = normalized_role((model_info or {}).get(XHUB_CREATOR_ROLE_KEY))
        return (
            model_team_id is None
            and creator_role == LitellmUserRoles.PROXY_ADMIN.value
            and normalize_optional_id(team.organization_id) is None
            and is_proxy_admin_created_team(team)
        )

    return False


def model_is_visible_to_any_team(model_info: Optional[Dict[str, Any]], teams: Iterable[LiteLLM_TeamTable]) -> bool:
    return any(team_can_use_model_info(model_info, team) for team in teams)
