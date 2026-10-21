"""Настройки запуска тестов: окружение, секреты, папка результатов."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------------
# Локальные настройки: .env читается, если установлен python-dotenv
# ------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv()


# ------------------------------------------------------------------------
# Окружение: TEST_ENV выбирает dev, stage или prod; по умолчанию stage
# ------------------------------------------------------------------------
CURRENT_ENV = os.getenv("TEST_ENV", "stage").lower()
if CURRENT_ENV not in {"dev", "stage", "prod"}:
    raise ValueError(f"TEST_ENV должен быть dev, stage или prod. Получено: {CURRENT_ENV}")

# ------------------------------------------------------------------------
# Артефакты: отдельная папка запуска для лога, Allure, скриншотов и отчётов
# ------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR") or ROOT_DIR / "artifacts")
RUN_DIR = ARTIFACTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{CURRENT_ENV}"


# ------------------------------------------------------------------------
# Секреты: env или Vault читаются только при обращении к ключу настроек
# ------------------------------------------------------------------------

class Settings:
    """Секреты: адреса, токены, пароли.

    Тест получает секрет так: ACTIVE_CONFIG["app_api_token"].
    Источник секретов задайте в SECRETS_SOURCE:
        env   - переменные окружения с префиксом окружения, например STAGE_APP_API_TOKEN.
        vault - хранилище Vault. Имя ключа без префикса, например APP_API_TOKEN.
    Программа читает секрет только тогда, когда тесту он нужен.
    Полный список переменных есть в файле .env.example.
    """

    def __init__(self, env: str) -> None:
        self.env = env
        self.source = os.getenv("SECRETS_SOURCE", "env").lower()
        if self.source not in {"env", "vault"}:
            raise ValueError("SECRETS_SOURCE должен быть 'env' или 'vault'")
        self._vault: dict | None = None

    def __getitem__(self, name: str) -> str:
        key = name.upper()
        if self.source == "env":
            env_key = f"{self.env.upper()}_{key}"
            value = os.getenv(env_key)
            if not value:
                raise KeyError(f"Не задана переменная окружения {env_key}")
            return value

        if self._vault is None:
            self._vault = _read_vault(self.env)
        value = self._vault.get(key)
        if value in (None, ""):
            raise KeyError(f"В Vault нет ключа {key}")
        return str(value)


# ------------------------------------------------------------------------
# Vault: токен или AppRole, поддерживаются хранилища KV v1 и v2
# ------------------------------------------------------------------------

def _read_vault(env: str) -> dict:
    """Читает секреты окружения из Vault.

    Адрес и путь: VAULT_ADDR, VAULT_MOUNT, VAULT_PATH. Слово {env} в пути заменяется на окружение.
    Вход: VAULT_TOKEN или пара VAULT_ROLE_ID и VAULT_SECRET_ID.
    """
    import hvac

    path = os.environ["VAULT_PATH"].replace("{env}", env)
    mount = os.environ["VAULT_MOUNT"]
    token = os.getenv("VAULT_TOKEN")
    verify = os.getenv("VAULT_CACERT") or os.getenv("VAULT_VERIFY", "true").lower() == "true"

    approle = None if token else (os.environ["VAULT_ROLE_ID"], os.environ["VAULT_SECRET_ID"])

    client = hvac.Client(url=os.environ["VAULT_ADDR"], token=token, verify=verify)
    try:
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
# Настройки для тестов: ACTIVE_CONFIG использует выбранное окружение
# ------------------------------------------------------------------------

ACTIVE_CONFIG = Settings(CURRENT_ENV)
