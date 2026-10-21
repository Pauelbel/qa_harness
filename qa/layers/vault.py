"""Слой Vault: источник секретов ``SECRETS_SOURCE=vault``. Профиль requirements/vault.txt.

    pytest_plugins = ["qa.hooks.common", ..., "qa.layers.vault"]

Тесты не меняются: ACTIVE_CONFIG["app_api_token"] читает ключ APP_API_TOKEN из Vault
(без префикса окружения). Токен или AppRole, хранилища KV v1 и v2.

Адрес и путь: VAULT_ADDR, VAULT_MOUNT, VAULT_PATH. Слово {env} в пути заменяется на окружение.
Вход: VAULT_TOKEN или пара VAULT_ROLE_ID и VAULT_SECRET_ID.
Сертификат: VAULT_CACERT=/path/to/ca.pem или VAULT_VERIFY=false.

Секреты окружения читаются одним запросом при первом обращении теста к ключу и хранятся до конца запуска.
"""

from __future__ import annotations

from qa.base.config import register_secret_source, require

require(__name__, "vault", "hvac")

# Остальные импорты — после проверки: без зависимостей ошибка называет профиль, а не модуль.
import functools
import os


def read_secret(env: str, key: str) -> str | None:
    """Источник секретов ``vault`` для qa.base.config: значение ключа ``key`` или ``None``."""
    return _read_vault(env).get(key)


@functools.cache
def _read_vault(env: str) -> dict:
    """Читает секреты окружения из Vault; текст ошибки Vault наружу не попадает."""
    import hvac

    path = os.environ["VAULT_PATH"].replace("{env}", env)
    mount = os.environ["VAULT_MOUNT"]
    token = os.getenv("VAULT_TOKEN")
    verify = os.getenv("VAULT_CACERT") or os.getenv("VAULT_VERIFY", "true").lower() == "true"

    approle = None if token else (os.environ["VAULT_ROLE_ID"], os.environ["VAULT_SECRET_ID"])

    url = os.environ["VAULT_ADDR"]
    try:
        client = hvac.Client(url=url, token=token, verify=verify)
        if approle:
            client.auth.approle.login(role_id=approle[0], secret_id=approle[1])
        if os.getenv("VAULT_KV_VERSION", "2") == "1":
            return client.secrets.kv.v1.read_secret(path=path, mount_point=mount)["data"]
        return client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=mount, raise_on_deleted_version=True
        )["data"]["data"]
    except Exception as exc:
        # Ответ Vault может содержать секреты, поэтому показываем только тип ошибки.
        raise RuntimeError(f"Не удалось прочитать секрет Vault ({type(exc).__name__})") from None


# ------------------------------------------------------------------------
# Подключение: SECRETS_SOURCE=vault читает секреты через read_secret
# ------------------------------------------------------------------------

register_secret_source("vault", read_secret)
