from typing import Any, Optional
from ldap3 import Connection, Server, ALL
from ldap3.core.exceptions import LDAPException
from config import config
from loguru import logger


# Функции для LDAP аутентификации
class LDAPAuth:
    def __init__(self):
        self.server = Server(
            config.LDAP_SERVER,
            port=config.LDAP_PORT,
            use_ssl=config.LDAP_USE_SSL,
            get_info=ALL,
        )

    def authenticate(self, username: str, password: str) -> Optional[dict[str, Any]]:
        try:
            # 1. bind под администратором
            admin_conn = Connection(
                self.server,
                config.LDAP_ADMIN_DN,
                config.LDAP_ADMIN_PASSWORD,
                auto_bind=True,
            )

            # 2. ищем пользователя
            admin_conn.search(
                search_base=config.LDAP_SEARCH_BASE,
                search_filter=config.LDAP_SEARCH_FILTER.format(username=username),
                attributes=config.LDAP_ATTRIBUTES,
            )

            if not admin_conn.entries:
                admin_conn.unbind()
                return None

            entry = admin_conn.entries[0]
            user_dn = entry.entry_dn

            # 3. bind под пользователем
            user_conn = Connection(
                self.server,
                user_dn,
                password,
                auto_bind=True,
            )

            user_info = {
                "username": username,
                "full_name": str(entry.cn) if hasattr(entry, "cn") else username,
                "email": str(entry.mail) if hasattr(entry, "mail") else None,
                "auth_method": "ldap",
            }

            admin_conn.unbind()
            user_conn.unbind()
            return user_info

        except LDAPException as e:
            logger.warning(f"LDAP auth failed: {e}")
            return None

    def search_user(self, username: str) -> Optional[dict[str, Any]]:
        """Поиск пользователя в LDAP (без аутентификации)"""
        try:
            conn = Connection(
                self.server,
                config.LDAP_ADMIN_DN,
                config.LDAP_ADMIN_PASSWORD,
                auto_bind=True,
            )

            conn.search(
                search_base=config.LDAP_SEARCH_BASE,
                search_filter=config.LDAP_SEARCH_FILTER.format(username=username),
                attributes=config.LDAP_ATTRIBUTES,
            )

            if conn.entries:
                entry = conn.entries[0]
                user_info = {
                    "username": username,
                    "full_name": str(entry.cn) if hasattr(entry, "cn") else username,
                    "email": str(entry.mail)
                    if hasattr(entry, "mail")
                    else f"{username}@company.com",
                    "auth_method": "ldap",
                }
                conn.unbind()
                return user_info

            conn.unbind()
        except LDAPException as e:
            logger.error(f"LDAP search failed: {e}")

        return None


ldap_auth = LDAPAuth()
