"""
XHub LDAP authentication backend.

Users authenticate through the existing username/password form. Successful LDAP
users are provisioned as ``internal_user`` and are linked to a stable LDAP
subject so subsequent logins always re-validate against LDAP.
"""
import asyncio
import hashlib
import json
import logging
import ssl
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
    user_search_filter: str = "(uid={username})"
    user_email_attribute: str = "mail"
    default_user_role: str = Field(default="internal_user", frozen=True)
    use_ssl: bool = True
    start_tls: bool = False
    ca_cert_file: Optional[str] = None
    connect_timeout: float = Field(default=5.0, gt=0, le=60)
    receive_timeout: float = Field(default=10.0, gt=0, le=120)


def _parse_ldap_settings(raw: Optional[Dict[str, Any]]) -> Optional[LDAPSettings]:
    if not raw:
        return None
    try:
        return LDAPSettings(**raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to parse LDAP settings: %s", e)
        return None


def _parse_json_object(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw if isinstance(raw, dict) else None


async def get_ldap_config(prisma_client: Any) -> Optional[LDAPSettings]:
    """Load and decrypt the LDAP config. Returns ``None`` when disabled/unset."""
    if prisma_client is None:
        return None

    from litellm.proxy.proxy_server import proxy_config
    from litellm.repositories.table_repositories import LDAPConfigRepository

    record = await LDAPConfigRepository(prisma_client).table.find_unique(where={"id": "ldap_config"})
    if record is None:
        return None
    settings = _parse_json_object(getattr(record, "ldap_settings", None))
    if settings is None:
        return None

    decrypted = proxy_config._decrypt_and_set_db_env_variables(environment_variables=settings)
    cfg = _parse_ldap_settings(decrypted)
    if cfg is None or not cfg.enabled:
        return None
    return cfg


def _ldap_attribute_value(entry: Any, attribute_name: str) -> Optional[str]:
    """Read the first scalar value from a real ldap3 Entry or a test double."""
    if attribute_name == "entry_dn":
        return str(getattr(entry, "entry_dn", "")) or None

    value: Any = None
    try:
        value = entry[attribute_name].value
    except (KeyError, AttributeError, TypeError):
        try:
            value = getattr(entry, attribute_name)
        except AttributeError:
            value = None

    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, bytes):
        value = value.hex()
    return str(value) if value not in (None, "") else None


def _ldap_tls(config: LDAPSettings, ldap3_module: Any) -> Optional[Any]:
    if not config.ca_cert_file:
        return None
    return ldap3_module.Tls(
        validate=ssl.CERT_REQUIRED,
        ca_certs_file=config.ca_cert_file,
        version=ssl.PROTOCOL_TLS_CLIENT,
    )


def _authenticate_with_ldap_sync(username: str, password: str, config: LDAPSettings) -> Optional[Dict[str, str]]:
    from ldap3 import ALL, SUBTREE, Connection, Server, escape_filter_chars

    # Never interpolate an unescaped login value into an LDAP filter.
    if "{username}" not in config.user_search_filter:
        logger.error("LDAP user_search_filter must contain {username}")
        return None
    escaped_username = escape_filter_chars(username)
    search_filter = config.user_search_filter.replace("{username}", escaped_username)
    tls = _ldap_tls(config, __import__("ldap3"))
    server = Server(
        config.server_url,
        use_ssl=config.use_ssl,
        tls=tls,
        connect_timeout=config.connect_timeout,
        get_info=ALL,
    )

    search_conn = None
    user_conn = None
    try:
        bind_kwargs: Dict[str, Any] = {
            "auto_bind": False,
            "receive_timeout": config.receive_timeout,
        }
        if config.bind_dn and config.bind_password:
            bind_kwargs.update(user=config.bind_dn, password=config.bind_password)
        search_conn = Connection(server, **bind_kwargs)
        if not search_conn.bind():
            return None
        if config.start_tls:
            if config.use_ssl:
                logger.error("LDAP start_tls cannot be combined with LDAPS use_ssl")
                return None
            if not search_conn.start_tls():
                return None
        if not search_conn.search(
            config.user_search_base,
            search_filter,
            SUBTREE,
            attributes=[config.user_email_attribute],
        ):
            return None
        if len(search_conn.entries) != 1:
            logger.warning(
                "LDAP search for username=%s returned %d entries; refusing authentication",
                username,
                len(search_conn.entries),
            )
            return None

        entry = search_conn.entries[0]
        user_dn = _ldap_attribute_value(entry, "entry_dn")
        if not user_dn:
            return None
        email = _ldap_attribute_value(entry, config.user_email_attribute)
        external_subject = user_dn.strip().lower()

        user_conn = Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=False,
            receive_timeout=config.receive_timeout,
        )
        if not user_conn.bind():
            return None
        return {
            "external_subject": external_subject,
            "user_id": f"ldap:{hashlib.sha256(external_subject.encode('utf-8')).hexdigest()[:32]}",
            "user_email": email or username,
        }
    except Exception as e:  # noqa: BLE001
        logger.debug("LDAP authentication failed for user=%s: %s", username, e)
        return None
    finally:
        if search_conn is not None:
            try:
                search_conn.unbind()
            except Exception:
                logger.debug("Failed to unbind LDAP search connection", exc_info=True)
        if user_conn is not None:
            try:
                user_conn.unbind()
            except Exception:
                logger.debug("Failed to unbind LDAP user connection", exc_info=True)


async def authenticate_with_ldap(username: str, password: str, config: LDAPSettings) -> Optional[Dict[str, str]]:
    """Attempt an LDAP bind without blocking the asyncio event loop."""
    if not username or not password or not config.server_url or not config.user_search_base:
        return None
    try:
        import ldap3  # noqa: F401
    except ImportError:
        logger.warning("ldap3 is not installed; LDAP authentication is unavailable")
        return None
    return await asyncio.to_thread(_authenticate_with_ldap_sync, username, password, config)


def _metadata_dict(record: Any) -> Dict[str, Any]:
    metadata = getattr(record, "metadata", None)
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return metadata if isinstance(metadata, dict) else {}


async def ensure_internal_user_for_ldap(
    username: str, user_info: Dict[str, str], prisma_client: Any
) -> Optional[Any]:
    """Find or create the bound LDAP user; never claim a local account by email."""
    from litellm.repositories.user_repository import UserRepository

    external_subject = user_info.get("external_subject")
    if not external_subject:
        raise ValueError("LDAP authentication did not return a stable external subject")
    ldap_sso_id = f"ldap:{external_subject}"
    user_email = (user_info.get("user_email") or username).strip().lower()
    repository = UserRepository(prisma_client)

    existing = await repository.find_by_sso_id(ldap_sso_id)
    if existing is not None:
        if _metadata_dict(existing).get("auth_provider") != "ldap":
            raise ValueError("LDAP identity is already linked to another authentication provider")
        return existing

    email_owner = await repository.table.find_first(
        where={"user_email": {"equals": user_email, "mode": "insensitive"}}
    )
    if email_owner is not None:
        raise ValueError("LDAP email is already used by a non-LDAP user")

    return await repository.create_user(
        user_id=user_info.get("user_id") or f"ldap:{hashlib.sha256(ldap_sso_id.encode()).hexdigest()[:32]}",
        user_email=user_email,
        user_role="internal_user",
        sso_user_id=ldap_sso_id,
        metadata={"auth_provider": "ldap", "ldap_username": username},
    )
