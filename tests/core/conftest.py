"""Тесты самого ядра: вложенный pytest на локальной странице, без сети и стендов.

    result = run_ui(pytester, '''
        def test_case(page):
            page.set_content("<button>A</button>")
            BasePage(page).element("Кнопка «A»", "button").click()
    ''')

Вложенный проект подключает qa.hooks.common и qa.layers.ui, страница строится через
``page.set_content``: адрес ``ui_base_url`` не открывается. Каждый запуск — отдельный процесс:
плагины ядра регистрируются в глобальном allure_commons и не должны копиться между тестами.
"""

import json
import os
import textwrap
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

HARNESS_ROOT = Path(__file__).resolve().parents[2]
BROWSERS_PATH = Path.home() / ".cache" / "ms-playwright"  # место установки по умолчанию на Linux

INNER_CONFTEST = '''
import pytest

pytest_plugins = ["qa.hooks.common", "qa.layers.ui"]


@pytest.fixture(scope="session")
def ui_base_url():
    return "http://localhost"  # не открывается: тесты строят страницу через set_content
'''

INNER_HEADER = '''
from qa.base.report import step
from qa.layers.ui import BasePage
'''


@pytest.fixture
def run_ui(pytester, monkeypatch):
    """``run_ui(source, *args)`` — запустить вложенный тест ``test_case.py`` с ``source``."""
    monkeypatch.setenv("PYTHONPATH", str(HARNESS_ROOT))
    # pytester подменяет HOME: браузеры Playwright ищем там, где они установлены
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", os.getenv("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_PATH)))
    monkeypatch.setenv("HEADLESS", "true")
    monkeypatch.setenv("SECRETS_SOURCE", "env")
    pytester.makeconftest(INNER_CONFTEST)
    pytester.makeini("[pytest]\naddopts = -p no:cacheprovider\n")

    def run(source: str, *args: str):
        pytester.makepyfile(test_case=INNER_HEADER + textwrap.dedent(source))
        return pytester.runpytest_subprocess(*args)

    return run


@pytest.fixture
def allure_attachments():
    """``allure_attachments(results_dir)`` — все вложения из allure-results вложенного запуска."""
    return read_attachments


def read_attachments(results_dir: Path) -> list[dict]:
    """Вложения теста, его шагов и контейнеров фикстур."""
    found: list[dict] = []

    def walk(node: dict) -> None:
        found.extend(node.get("attachments", []))
        for child in node.get("steps", []):
            walk(child)
        for key in ("befores", "afters"):
            for child in node.get(key, []):
                walk(child)

    for path in results_dir.glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return found
