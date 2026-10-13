"""UI-тесты: браузер и вход во фронтенд.

Браузер даёт pytest-playwright: тест просит фикстуру ``page`` — новая страница, пользователь
уже вошёл, адреса считаются от app_frontend_url (``page.goto("/orders")``). Страница без входа:
    @pytest.mark.browser_context_args(storage_state=None)  (декоратор над тестом)

Ключи запуска: --headed (показать окно), --browser firefox,
--screenshot only-on-failure, --tracing retain-on-failure.
"""

import os

import pytest

from config import ACTIVE_CONFIG
from examples.ui.pages.login_page import LoginPage


# ============================================================================
# Браузер
# ============================================================================

@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Окно браузера видно по умолчанию; в CI — HEADLESS=true."""
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    return {"headless": headless, **browser_type_launch_args}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, app_storage_state):
    """Настройки каждой новой страницы: адрес фронтенда, размер окна, сертификаты, вход."""
    return {
        **browser_context_args,
        "base_url": ACTIVE_CONFIG["app_frontend_url"],
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,  # тестовые HTTPS-сертификаты
        "storage_state": app_storage_state,
    }


# ============================================================================
# Вход
# ============================================================================

@pytest.fixture(scope="session")
def app_storage_state(browser) -> dict:
    """Вход один раз на запуск; cookies переиспользуют все UI-тесты."""
    context = browser.new_context(base_url=ACTIVE_CONFIG["app_frontend_url"], ignore_https_errors=True)
    try:
        login_page = LoginPage(context.new_page())
        login_page.open()
        login_page.login_user(ACTIVE_CONFIG["app_frontend_login"], ACTIVE_CONFIG["app_frontend_password"])
        login_page.check_logged_in()
        return context.storage_state()
    finally:
        context.close()
