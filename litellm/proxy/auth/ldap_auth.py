"""
XHub LDAP authentication backend.

Lets users authenticate against an LDAP / Active Directory server using the
same username + password form as the existing email/password login. When LDAP
auth succeeds, the user is provisioned as an ``internal_user`` (Create/Delete/
View permissions) so they can immediately use the XHub admin UI.
"""
import json
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LDAPSettings(BaseModel):
    """LDAP server configuration stored in the dedicated LDAP config table."""

    enabled: bool = False
    server_url: str = ""
    bind_dn: str = ""
    bind_password: str = ""
    user_search_base: str = ""
    # ``{username}`` is replaced with the login name at request time.
    user_search_filter: str = "(uid={username})"
    # LDAP attribute that holds the user's email. Used as the XHub user id.
    user_email_attribute: str = "mail"
    # Role assigned to users who log in via LDAP. Fixed to internal_user so
    # LDAP users get Create/Delete/View permissions by default.
    default_user_role: str = "internal_user"
    use_ssl: bool = True


def _parse_ldap_settings(raw: Optional[Dict[str, Any]]) -> Optional[LDAPSettings]:
    if not raw:
        return None
    try:
        return LDAPSettings(**raw)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to parse LDAP settings: {e}")
        return None


async def get_ldap_config(prisma_client: Any) -> Optional[LDAPSettings]:
    """Load and decrypt the LDAP config. Returns ``None`` when disabled/unset."""
    if prisma_client is None:
        return None

    from litellm.proxy.proxy_server import proxy_config
    from litellm.repositories.table_repositories import LDAPConfigRepository

    record = await LDAPConfigRepository(prisma_client).table.find_unique(where={"id": "ldap_config"})
    if record is None or not getattr(record, "ldap_settings", None):
        return None

    settings = record.ldap_settings
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError:
            return None
    if not isinstance(settings, dict):
        return None

    # Bind password is stored encrypted via the shared proxy config helpers.
    decrypted = proxy_config._decrypt_and_set_db_env_variables(environment_variables=settings)

    cfg = _parse_ldap_settings(decrypted)
    if cfg is None or not cfg.enabled:
        return None
    return cfg


async def authenticate_with_ldap(username: str, password: str, config: LDAPSettings) -> Optional[Dict[str, str]]:
    """Attempt an LDAP bind. Returns user info on success, else ``None``."""
    if not username or not password:
        return None
    if not config.server_url or not config.user_search_base:
        return None

    try:
        from ldap3 import ALL, SUBTREE, Connection, Server
    except ImportError:
        logger.warning("ldap3 is not installed; LDAP authentication is unavailable")
        return None

    try:
        server = Server(config.server_url, use_ssl=config.use_ssl, get_info=ALL)

        # Optional service-account bind used only to locate the user entry.
        if config.bind_dn and config.bind_password:
            search_conn = Connection(
                server, user=config.bind_dn, password=config.bind_password, auto_bind=True
            )
        else:
            search_conn = Connection(server, auto_bind=True)

        search_filter = config.user_search_filter.replace("{username}", username)
        search_conn.search(
            config.user_search_base,
            search_filter,
            SUBTREE,
            attributes=[config.user_email_attribute],
        )

        if not search_conn.entries:
            search_conn.unbind()
            return None

        entry = search_conn.entries[0]
        user_dn = entry.entry_dn
        email_value = entry.__getattribute__(config.user_email_attribute)
        email = email_value[0] if isinstance(email_value, list) and email_value else None
        search_conn.unbind()

        # Verify the supplied password by binding as the user themselves.
        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()

        return {"user_id": email or username, "user_email": email or username}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"LDAP authentication failed for user={username}: {e}")
        return None


async def ensure_internal_user_for_ldap(
    username: str, user_info: Dict[str, str], prisma_client: Any
) -> Optional[Any]:
    """Find or create the ``internal_user`` row for an LDAP-authenticated user."""
    from litellm.proxy.auth.auth_utils import LitellmUserRoles, UserAPIKeyAuth, UserRepository
    from litellm.proxy.management_endpoints.internal_user_endpoints import NewUserRequest, new_user

    user_email = (user_info.get("user_email") or username).lower()
    user_id = user_info.get("user_id") or user_email

    if prisma_client is not None:
        existing = await UserRepository(prisma_client).table.find_first(
            where={"user_email": {"equals": user_email, "mode": "insensitive"}}
        )
        if existing is not None:
            return existing

    await new_user(
        data=NewUserRequest(
            user_id=user_id,
            user_email=user_email,
            user_role=LDAPSettings().default_user_role,
            auto_create_key=False,
        ),
        user_api_key_dict=UserAPIKeyAuth(user_role=LitellmUserRoles.PROXY_ADMIN),
    )

    if prisma_client is None:
        return None

    return await UserRepository(prisma_client).table.find_first(
        where={"user_email": {"equals": user_email, "mode": "insensitive"}}
    )
