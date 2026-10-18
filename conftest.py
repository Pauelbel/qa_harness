"""Общие настройки для всех тестов: артефакты запуска, логи, маркеры, обязательный итог проверок.

Здесь только то, что не зависит от тестируемой системы. Своё у каждой папки — в её conftest.py:
    examples/conftest.py             клиенты систем и тестовые данные
    examples/ui/conftest.py          браузер и вход во фронтенд
    examples/dq_reports/conftest.py  скачивание отчёта и checker
"""

import logging
import os
import platform
import subprocess

import allure_commons
import pytest

from checks import base
from config import CURRENT_ENV, ROOT_DIR, RUN_DIR


# ============================================================================
# Артефакты запуска
#   всё в RUN_DIR (artifacts/<дата-время>_<окружение>/): pytest.log, allure-results/,
#   playwright/ (скриншоты и trace упавших UI-тестов); свой путь — ключом запуска
# ============================================================================

@pytest.hookimpl(tryfirst=True)  # раньше плагина Allure: он читает --alluredir в своём pytest_configure
def pytest_configure(config):
    if not config.option.log_file:  # свой путь: --log-file=...
        config.option.log_file = str(RUN_DIR / "pytest.log")
    if hasattr(config.option, "allure_report_dir") and not config.option.allure_report_dir:
        config.option.allure_report_dir = str(RUN_DIR / "allure-results")  # свой путь: --alluredir=...
    if getattr(config.option, "output", None) == "test-results":  # pytest-playwright; свой путь: --output=...
        config.option.output = str(RUN_DIR / "playwright")

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
    return [f"Окружение: {CURRENT_ENV}, артефакты: {RUN_DIR}"]


def _run_info() -> dict[str, str]:
    """Сведения о запуске для вкладки Environment отчёта Allure."""
    return {
        "TEST_ENV": CURRENT_ENV,
        "APP_VERSION": os.getenv("APP_VERSION", "не задана"),  # версию тестируемого приложения передаёт CI
        "HARNESS_COMMIT": _git_commit(),
        "PYTHON": platform.python_version(),
    }


def _git_commit() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT_DIR, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT_DIR, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return "неизвестен"
    return commit + ("-dirty" if dirty.strip() else "")


# ============================================================================
# Логи
#   консоль — INFO, файл RUN_DIR/pytest.log — DEBUG (форматы в pytest.ini)
# ============================================================================

class StepsToLog:
    """Каждый allure-шаг (страницы, элементы, проверки) — строка ``STEP: ...`` в логе."""

    @allure_commons.hookimpl
    def start_step(self, uuid, title, params):
        logging.getLogger("steps").info("STEP: %s", title)


# ============================================================================
# Итог проверок
#   ошибки Checker'а, которые тест накопил, но не показал (забыли with или assert_valid()),
#   всё равно роняют тест
# ============================================================================

@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    base.start_test()  # checker'ы из фикстур теста создаются после этого
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    result = yield  # тест уже упал — его ошибку не подменяем
    errors = base.unreported_errors()
    if errors:
        raise AssertionError(
            "Проверки накопили ошибки, но тест не вызвал assert_valid() и не использовал with Checker():\n\n"
            + "\n\n".join(errors)
        )
    return result


# ============================================================================
# Маркеры
#   ставятся сами по папке теста: python -m pytest -m dq
# ============================================================================

FOLDER_MARKERS = {
    "api": "api",
    "db": "db",
    "ui": "ui",
    "dq_reports": "dq",
}


def pytest_collection_modifyitems(items):
    for item in items:
        marker = FOLDER_MARKERS.get(item.path.parent.name)
        if marker:
            item.add_marker(marker)
