"""Instance-level Team scope enforcement for XHub deployments.

The instance allowlist is a server-side boundary.  It is intentionally kept
separate from caller-provided request data and is intersected with the
caller's own Team scope before a management endpoint uses it.
"""

from typing import Any, Iterable, List, Optional, Set

import litellm
from fastapi import HTTPException

from litellm.proxy._types import UserAPIKeyAuth


_SCOPE_CONFIG_KEY = "xhub_team_scope"


def _get_scope_config() -> dict:
    value = getattr(litellm, _SCOPE_CONFIG_KEY, None)
    return value if isinstance(value, dict) else {}


def is_team_scoped_instance() -> bool:
    """Return whether this process has an enabled XHub Team boundary."""
    return _get_scope_config().get("enabled", False) is True


def get_instance_allowed_team_ids() -> Optional[Set[str]]:
    """Return the immutable process-level Team allowlist.

    ``None`` means the feature is disabled and preserves the upstream
    unscoped behavior.  An enabled scope always returns a set, including an
    empty set for defensive handling of a malformed runtime value.
    """
    if not is_team_scoped_instance():
        return None
    configured = _get_scope_config().get("allowed_team_ids", [])
    if not isinstance(configured, (list, tuple, set)):
        return set()
    return {team_id for team_id in configured if isinstance(team_id, str) and team_id}


def _team_ids_from_value(value: object) -> Set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (list, tuple, set)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def get_caller_allowed_team_ids(
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> Optional[Set[str]]:
    """Resolve the caller's Team scope without trusting request parameters.

    A virtual key is scoped to its persisted ``team_id``.  Internal users and
    SSO sessions may carry ``available_teams``/``team_ids`` in server-built
    metadata.  A Proxy Admin without a narrower server-side scope is
    intentionally represented by ``None`` (unrestricted caller scope); the
    instance allowlist still bounds it in ``get_effective_allowed_team_ids``.
    """
    if user_api_key_dict is None:
        return set()

    metadata = user_api_key_dict.metadata if isinstance(user_api_key_dict.metadata, dict) else {}
    for key in ("available_teams", "team_ids", "teams"):
        team_ids = _team_ids_from_value(metadata.get(key))
        if team_ids:
            return team_ids

    if user_api_key_dict.team_id:
        return {user_api_key_dict.team_id}

    default_params = getattr(litellm, "default_internal_user_params", None)
    if isinstance(default_params, dict):
        team_ids = _team_ids_from_value(default_params.get("available_teams"))
        if team_ids:
            return team_ids

    # An unscoped admin has no caller restriction; the instance boundary still
    # applies.  Non-admin callers without a server-side Team identity must not
    # gain access by omitting team_id.
    if user_api_key_dict.user_role in ("proxy_admin", "proxy_admin_viewer"):
        return None
    return set()


def get_effective_allowed_team_ids(
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> Optional[Set[str]]:
    """Return ``instance allowlist ∩ caller allowlist``.

    ``None`` is only returned when the instance feature is disabled, allowing
    existing upstream callers to retain their previous authorization logic.
    """
    instance_ids = get_instance_allowed_team_ids()
    if instance_ids is None:
        return None
    caller_ids = get_caller_allowed_team_ids(user_api_key_dict)
    if caller_ids is None:
        return set(instance_ids)
    return instance_ids & caller_ids


def is_team_in_scope(
    team_id: Optional[str],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> bool:
    """Check a Team against the effective scope; missing IDs always fail."""
    if not team_id:
        return False if is_team_scoped_instance() else True
    effective = get_effective_allowed_team_ids(user_api_key_dict)
    return effective is None or team_id in effective


def filter_team_ids_by_scope(
    team_ids: Iterable[str],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> Set[str]:
    """Filter arbitrary Team IDs using the effective server-side scope."""
    effective = get_effective_allowed_team_ids(user_api_key_dict)
    candidate_ids = {team_id for team_id in team_ids if isinstance(team_id, str) and team_id}
    return candidate_ids if effective is None else candidate_ids & effective


def assert_team_in_scope(
    team_id: Optional[str],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> None:
    """Raise 403 when a management operation targets an out-of-scope Team."""
    if not is_team_in_scope(team_id, user_api_key_dict):
        raise HTTPException(status_code=403, detail="Team is outside this instance's allowed scope")


def assert_all_teams_in_scope(
    team_ids: Iterable[str],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> None:
    requested = {team_id for team_id in team_ids if isinstance(team_id, str) and team_id}
    if get_effective_allowed_team_ids(user_api_key_dict) is not None and not requested.issubset(
        get_effective_allowed_team_ids(user_api_key_dict) or set()
    ):
        raise HTTPException(status_code=403, detail="One or more Teams are outside this instance's allowed scope")


def get_scoped_team_id_filter(
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> Optional[Set[str]]:
    """Return the Team IDs a query may include, or ``None`` when unscoped.

    An empty set is a hard deny: the caller/instance intersection contains no
    Teams, so list queries must return no rows instead of falling back to a
    global scan.
    """
    return get_effective_allowed_team_ids(user_api_key_dict)


def team_id_in_filter(team_ids: Set[str]) -> dict:
    """Prisma ``team_id IN (...)`` filter for a non-empty scoped Team set."""
    return {"team_id": {"in": sorted(team_ids)}}


def assert_existing_key_in_scope(
    key_info: Any,
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> None:
    """Raise 403 when a persisted key is outside the effective Team scope.

    Keys without a Team remain forbidden on a scoped instance, including for
    Proxy Admin. This keeps /key/info, delete, block, and regenerate aligned
    with the same server-side boundary as list and create.
    """
    team_id = getattr(key_info, "team_id", None)
    if isinstance(key_info, dict):
        team_id = key_info.get("team_id")
    assert_team_in_scope(team_id, user_api_key_dict)


def assert_system_endpoint_disabled_when_scoped() -> None:
    """Block system-level routes that have no Team binding on scoped instances."""
    if is_team_scoped_instance():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is disabled when XHub Team scope is enabled",
        )


def user_teams_has_some_filter(team_ids: Set[str]) -> dict:
    """Prisma filter for users belonging to at least one scoped Team."""
    return {"teams": {"hasSome": sorted(team_ids)}}


def assert_user_teams_in_scope(
    user_teams: Optional[Iterable[str]],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> None:
    """Raise 403 when a user has no Team overlapping the effective scope."""
    effective = get_effective_allowed_team_ids(user_api_key_dict)
    if effective is None:
        return
    teams = {team_id for team_id in (user_teams or []) if isinstance(team_id, str) and team_id}
    if not teams & effective:
        raise HTTPException(
            status_code=403,
            detail="User is outside this instance's allowed Team scope",
        )


def intersection_team_ids(
    team_ids: Optional[Iterable[str]],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> Optional[Set[str]]:
    """Intersect caller-supplied Team IDs with the effective scope.

    ``None`` is returned when the instance feature is disabled.  An empty
    set means the caller has no remaining Teams after the boundary.
    """
    effective = get_effective_allowed_team_ids(user_api_key_dict)
    if effective is None:
        return None if team_ids is None else {t for t in team_ids if isinstance(t, str) and t}
    candidates = {t for t in (team_ids or []) if isinstance(t, str) and t}
    return candidates & effective if team_ids is not None else set(effective)


def empty_paginated_teams(page: int = 1, page_size: int = 10) -> dict:
    return {
        "teams": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 0,
    }


def empty_paginated_users(page: int = 1, page_size: int = 10) -> dict:
    return {
        "users": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_pages": 0,
    }


def assigned_teams_has_some_filter(team_ids: Set[str]) -> dict:
    """Prisma filter for access groups assigned to at least one scoped Team."""
    return {"assigned_team_ids": {"hasSome": sorted(team_ids)}}


def access_group_in_scope(assigned_team_ids: Optional[Iterable[str]], allowed_team_ids: Optional[Set[str]]) -> bool:
    """Return whether an Access Group intersects the effective Team scope.

    Unscoped instances always pass.  On a scoped instance an Access Group
    without overlapping Teams (including no assigned Teams) is hidden.
    """
    if allowed_team_ids is None:
        return True
    teams = {team_id for team_id in (assigned_team_ids or []) if isinstance(team_id, str) and team_id}
    return bool(teams & allowed_team_ids)


def filter_assigned_team_ids_for_response(
    assigned_team_ids: Optional[Iterable[str]],
    allowed_team_ids: Optional[Set[str]],
) -> List[str]:
    """Strip out-of-scope Team IDs from an Access Group response payload."""
    teams = [team_id for team_id in (assigned_team_ids or []) if isinstance(team_id, str) and team_id]
    if allowed_team_ids is None:
        return teams
    return [team_id for team_id in teams if team_id in allowed_team_ids]


def assert_access_group_in_scope(
    assigned_team_ids: Optional[Iterable[str]],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> None:
    """Raise 403 when an Access Group has no Team overlapping the effective scope."""
    effective = get_effective_allowed_team_ids(user_api_key_dict)
    if not access_group_in_scope(assigned_team_ids, effective):
        raise HTTPException(
            status_code=403,
            detail="Access group is outside this instance's allowed Team scope",
        )


def access_group_fully_in_scope(
    assigned_team_ids: Optional[Iterable[str]],
    allowed_team_ids: Optional[Set[str]],
) -> bool:
    """Return whether every assigned Team is inside the effective scope.

    Unscoped instances always pass.  On a scoped instance an Access Group
    with no assigned Teams, or any Team outside the allowlist, fails.
    """
    if allowed_team_ids is None:
        return True
    teams = {team_id for team_id in (assigned_team_ids or []) if isinstance(team_id, str) and team_id}
    return bool(teams) and teams.issubset(allowed_team_ids)


def assert_access_group_fully_in_scope(
    assigned_team_ids: Optional[Iterable[str]],
    user_api_key_dict: Optional[UserAPIKeyAuth],
) -> None:
    """Raise 403 when an Access Group is assigned to any Team outside the scope."""
    effective = get_effective_allowed_team_ids(user_api_key_dict)
    if not access_group_fully_in_scope(assigned_team_ids, effective):
        raise HTTPException(
            status_code=403,
            detail="Access group is assigned to teams outside this instance's allowed scope",
        )
