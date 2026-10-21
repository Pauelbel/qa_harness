"""Общие хуки pytest, нужные любому тесту. Подключается первой строкой pytest_plugins в conftest.py.

    артефакты запуска    лог, Allure — в RUN_DIR (папка в корне запуска, см. qa/base/config.py)
    лог шагов            каждый шаг Allure — строка STEP: ... в логе
    итог проверок        забытый with или assert_valid() не скрывает ошибки Checker
    маркеры по папке     api, db, ui, dq — по имени папки теста, выбор слоя через pytest -m
    папки слоёв          папка слоя, чей модуль не подключён, не собирается

Здесь только то, что не зависит от тестируемой системы и слоя. Хуки слоёв — в qa/layers/<слой>.py,
фикстуры систем — в conftest.py рядом с тестами.
"""

import logging
import os
import platform
import subprocess

import allure_commons
import pytest

from qa.base import checks, config as harness_config


# ------------------------------------------------------------------------
# Артефакты запуска: лог и Allure сохраняются в RUN_DIR
# Свой путь задаётся ключами --log-file и --alluredir
# ------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True)  # раньше плагина Allure: он читает --alluredir в своём pytest_configure
def pytest_configure(config):
    harness_config.set_root(config.rootpath)  # .env и artifacts/ — в корне запуска, а не в папке harness
    try:
        run_dir = harness_config.RUN_DIR
        harness_config.ACTIVE_CONFIG.check_source()
    except ValueError as error:
        raise pytest.UsageError(str(error)) from None

    if hasattr(config.option, "log_file") and not config.option.log_file:  # свой путь: --log-file=...
        config.option.log_file = str(run_dir / "pytest.log")
    if hasattr(config.option, "allure_report_dir") and not config.option.allure_report_dir:
        config.option.allure_report_dir = str(run_dir / "allure-results")  # свой путь: --alluredir=...

    for marker, description in LAYER_MARKERS.items():
        config.addinivalue_line("markers", f"{marker}: {description}")

    logging.getLogger("urllib3").setLevel(logging.WARNING)  # без шума от requests
    allure_commons.plugin_manager.register(StepsToLog())


def pytest_sessionstart(session):
    allure_dir = getattr(session.config.option, "allure_report_dir", None)
    if allure_dir and not hasattr(session.config, "workerinput"):
        os.makedirs(allure_dir, exist_ok=True)
        with open(os.path.join(allure_dir, "environment.properties"), "w", encoding="utf-8") as file:
            for key, value in _run_info().items():
                file.write(f"{key}={value}\n")


def pytest_report_header(config):
    lines = [f"Окружение: {harness_config.CURRENT_ENV}, артефакты: {harness_config.RUN_DIR}"]
    skipped = [f"{folder}/ (нет {plugin})" for folder, plugin in LAYER_PLUGINS.items() if not _enabled(config, plugin)]
    if skipped:
        lines.append(f"Не собираются папки слоёв без плагина: {', '.join(skipped)}")
    return lines


def _run_info() -> dict[str, str]:
    """Сведения о запуске для вкладки Environment отчёта Allure."""
    return {
        "TEST_ENV": harness_config.CURRENT_ENV,
        "APP_VERSION": os.getenv("APP_VERSION", "не задана"),  # версию тестируемого приложения передаёт CI
        "GIT_COMMIT": _git_commit(),
        "PYTHON": platform.python_version(),
    }


def _git_commit() -> str:
    """Коммит репозитория, из которого запущены тесты (в рабочем проекте — вместе с harness/)."""
    root = harness_config.ROOT_DIR
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return "неизвестен"
    return commit + ("-dirty" if dirty.strip() else "")


# ------------------------------------------------------------------------
# Логи: каждый шаг Allure записывается в лог
# Уровни: консоль — INFO, файл — DEBUG; форматы задаются в pytest.ini
# ------------------------------------------------------------------------

class StepsToLog:
    """Каждый allure-шаг (страницы, элементы, проверки) — строка ``STEP: ...`` в логе."""

    @allure_commons.hookimpl
    def start_step(self, uuid, title, params):
        logging.getLogger("steps").info("STEP: %s", title)


# ------------------------------------------------------------------------
# Итог проверок: забытый with или assert_valid() не скрывает ошибки Checker
# Учёт начинается до создания фикстур, непоказанные ошибки роняют тест
# ------------------------------------------------------------------------

@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    checks.start_test()  # checker'ы из фикстур теста создаются после этого
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    result = yield  # тест уже упал — его ошибку не подменяем
    errors = checks.unreported_errors()
    if errors:
        raise AssertionError(
            "Проверки накопили ошибки, но тест не вызвал assert_valid() и не использовал with Checker():\n\n"
            + "\n\n".join(errors)
        )
    return result


# ------------------------------------------------------------------------
# Слои: маркер по папке теста, папка без подключённого плагина не собирается
# Работает для папок слоёв внутри tests/ на любом уровне вложенности
# ------------------------------------------------------------------------

FOLDER_MARKERS = {  # имя папки → маркер; папка может быть на любом уровне: tests/ui/orders/test_...
    "api": "api",
    "db": "db",
    "ui": "ui",
    "dq": "dq",
}
LAYER_MARKERS = {
    "api": "тесты HTTP API",
    "db": "тесты базы данных",
    "ui": "тесты в браузере",
    "dq": "проверки качества данных Excel-отчётов",
}
LAYER_PLUGINS = {  # папка → плагин, без которого её тесты не соберутся
    "api": "qa.layers.api",
    "db": "qa.layers.db",
    "ui": "qa.layers.ui",
    "dq": "qa.layers.dq",
}


def _enabled(config, plugin: str) -> bool:
    return config.pluginmanager.has_plugin(plugin)


def pytest_ignore_collect(collection_path, config):
    plugin = LAYER_PLUGINS.get(collection_path.name)
    if plugin and collection_path.is_dir() and not _enabled(config, plugin):
        return True
    return None


def pytest_collection_modifyitems(config, items):
    for item in items:
        try:
            folders = item.path.parent.relative_to(config.rootpath).parts
        except ValueError:  # тест вне корня запуска
            folders = item.path.parent.parts
        for marker in {FOLDER_MARKERS[name] for name in folders if name in FOLDER_MARKERS}:
            item.add_marker(marker)
