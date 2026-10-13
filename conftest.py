"""Общие настройки для всех тестов: логи и маркеры.

Здесь только то, что не зависит от тестируемой системы. Своё у каждой папки — в её conftest.py:
    examples/conftest.py             клиенты систем и тестовые данные
    examples/ui/conftest.py          браузер и вход во фронтенд
    examples/dq_reports/conftest.py  скачивание отчёта и checker
"""

import logging

import allure_commons

from config import CURRENT_ENV


# ============================================================================
# Логи
#   консоль — INFO, файл logs/pytest_<окружение>.log — DEBUG (форматы в pytest.ini)
# ============================================================================

def pytest_configure(config):
    if not config.option.log_file:  # свой путь: --log-file=...
        config.option.log_file = f"logs/pytest_{CURRENT_ENV}.log"

    logging.getLogger("urllib3").setLevel(logging.WARNING)  # без шума от requests
    allure_commons.plugin_manager.register(StepsToLog())


class StepsToLog:
    """Каждый allure-шаг (страницы, элементы, проверки) — строка ``STEP: ...`` в логе."""

    @allure_commons.hookimpl
    def start_step(self, uuid, title, params):
        logging.getLogger("steps").info("STEP: %s", title)


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
