"""Настройки запуска тестов: окружение, секреты, папка результатов.

    from qa.base.config import ACTIVE_CONFIG, RUN_DIR
    token = ACTIVE_CONFIG["app_api_token"]

Корень запуска — каталог, от которого работает pytest (rootdir: там лежит pytest.ini).
От него читается ``.env`` и строится папка артефактов. В рабочем проекте harness лежит
в подпапке ``harness/``, а ``.env`` и ``artifacts/`` — в корне рабочего репозитория.

Значения ``ROOT_DIR``, ``CURRENT_ENV``, ``ARTIFACTS_DIR``, ``RUN_DIR`` вычисляются при первом
обращении: ``qa.hooks.common`` сначала сообщает корень запуска, потом ими пользуются тесты и плагины.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ENVIRONMENTS = ("dev", "stage", "prod")


# ------------------------------------------------------------------------
# Запуск: корень, окружение и папка артефактов определяются один раз
# ------------------------------------------------------------------------

@dataclass(frozen=True)
class _Run:
    root_dir: Path
    env: str
    artifacts_dir: Path
    run_dir: Path


_root: Path | None = None
_run: _Run | None = None


def set_root(root: Path) -> None:
    """Корень запуска (rootdir pytest). Вызывает ``qa.hooks.common`` до первого обращения к настройкам."""
    global _root, _run
    _root, _run = Path(root).resolve(), None


def _current_run() -> _Run:
    global _run
    if _run is None:
        root = _root or Path.cwd().resolve()  # вне pytest — каталог запуска
        _load_dotenv(root / ".env")

        # Окружение: TEST_ENV выбирает dev, stage или prod; по умолчанию stage.
        env = os.getenv("TEST_ENV", "stage").lower()
        if env not in ENVIRONMENTS:
            raise ValueError(f"TEST_ENV должен быть {', '.join(ENVIRONMENTS)}. Получено: {env}")

        # Артефакты: отдельная папка запуска для лога, Allure, скриншотов и отчётов.
        artifacts = root / (os.getenv("ARTIFACTS_DIR") or "artifacts")  # абсолютный путь заменяет корень
        _run = _Run(root, env, artifacts, artifacts / f"{datetime.now():%Y%m%d-%H%M%S}_{env}")
    return _run


def _load_dotenv(path: Path) -> None:
    """Локальные настройки из ``.env``, если установлен python-dotenv. Переменные окружения важнее."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path)


def __getattr__(name: str):
    """``from qa.base.config import RUN_DIR`` и другие значения запуска — при первом обращении."""
    run_values = {
        "ROOT_DIR": lambda run: run.root_dir,
        "CURRENT_ENV": lambda run: run.env,
        "ARTIFACTS_DIR": lambda run: run.artifacts_dir,
        "RUN_DIR": lambda run: run.run_dir,
    }
    if name in run_values:
        return run_values[name](_current_run())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ------------------------------------------------------------------------
# Источники секретов: env встроен, остальные регистрируют плагины
# ------------------------------------------------------------------------

SecretReader = Callable[[str, str], "str | None"]
"""``reader(env, key)``: значение секрета ``key`` окружения ``env`` или ``None``, если его нет."""

_SOURCES: dict[str, SecretReader] = {}
_SOURCE_PLUGINS = {"vault": "qa.layers.vault"}  # чем подсказать, если источник не подключён


def register_secret_source(name: str, reader: SecretReader) -> None:
    """Подключить источник секретов: ``SECRETS_SOURCE=<name>`` читает ключи через ``reader``.

    Источник читает секреты при первом обращении теста к ключу, а не при регистрации.
    """
    _SOURCES[name.lower()] = reader


def _read_env(env: str, key: str) -> str:
    env_key = f"{env.upper()}_{key}"
    value = os.getenv(env_key)
    if not value:
        raise KeyError(f"Не задана переменная окружения {env_key}")
    return value


register_secret_source("env", _read_env)


class Settings:
    """Секреты: адреса, токены, пароли.

    Тест получает секрет так: ACTIVE_CONFIG["app_api_token"].
    Источник секретов задайте в SECRETS_SOURCE:
        env   - переменные окружения с префиксом окружения, например STAGE_APP_API_TOKEN.
        vault - хранилище Vault (плагин qa.layers.vault). Имя ключа без префикса, например APP_API_TOKEN.
    Программа читает секрет только тогда, когда тесту он нужен.
    Полный список переменных есть в файле .env.example.
    """

    def __init__(self, env: str | None = None) -> None:
        self._env = env  # None — окружение запуска (TEST_ENV)

    @property
    def env(self) -> str:
        return self._env or _current_run().env

    @property
    def source(self) -> str:
        return os.getenv("SECRETS_SOURCE", "env").lower()

    def check_source(self) -> None:
        """Источник из SECRETS_SOURCE подключён; иначе ValueError с подсказкой, что подключить."""
        if self.source in _SOURCES:
            return
        plugin = _SOURCE_PLUGINS.get(self.source)
        if plugin:
            raise ValueError(f"SECRETS_SOURCE={self.source}: подключите {plugin} в conftest.py (pytest_plugins)")
        raise ValueError(f"SECRETS_SOURCE должен быть одним из: {', '.join(sorted(_SOURCES))}. Получено: {self.source}")

    def __getitem__(self, name: str) -> str:
        self.check_source()
        key = name.upper()
        value = _SOURCES[self.source](self.env, key)
        if value in (None, ""):
            raise KeyError(f"Источник секретов {self.source}: нет ключа {key}")
        return str(value)


# ------------------------------------------------------------------------
# Зависимости плагинов: понятная ошибка вместо ModuleNotFoundError
# ------------------------------------------------------------------------

class MissingDependency(ImportError):
    """Плагин подключён, а профиль его зависимостей не установлен."""


def require(plugin: str, profile: str, *modules: str) -> None:
    """Плагин ``plugin`` нужен модулям ``modules``; если их нет — ошибка с профилем ``requirements/<profile>.txt``."""
    missing = [module for module in modules if not _installed(module)]
    if missing:
        raise MissingDependency(
            f"Слою {plugin} не хватает {', '.join(missing)}: pip install -r requirements/{profile}.txt "
            f"(в рабочем проекте — harness/requirements/{profile}.txt) или уберите {plugin} из pytest_plugins в conftest.py"
        )


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ImportError:  # сломанная или частичная установка пакета
        return False


# ------------------------------------------------------------------------
# Настройки для тестов: ACTIVE_CONFIG использует выбранное окружение
# ------------------------------------------------------------------------

ACTIVE_CONFIG = Settings()
