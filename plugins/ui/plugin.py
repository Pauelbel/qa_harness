"""UI-тесты: браузер, вход во фронтенд и вложения при падении.

Браузер даёт pytest-playwright. Адреса считаются от app_frontend_url (``page.goto("/orders")``).
    page       — страница без входа (стандартная фикстура pytest-playwright);
    auth_page  — страница, где пользователь уже вошёл: вход выполняется один раз на запуск
                 и только если хотя бы одному тесту нужна auth_page.

При падении к отчёту Allure прикладываются скриншот и адрес каждой страницы теста.
Ключи запуска: --headed (показать окно), --browser firefox, --tracing retain-on-failure
(trace упавших тестов — в RUN_DIR/playwright). В trace видны введённые значения, в том числе пароль:
не публикуйте trace из CI без необходимости.
"""

import os

import allure
import pytest
from playwright.sync_api import Page

from config import ACTIVE_CONFIG
from examples.ui.pages.login_page import LoginPage


# ------------------------------------------------------------------------
# Браузер: настройки запуска и контекста применяются к новым страницам
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Окно браузера видно по умолчанию; в CI — HEADLESS=true."""
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    return {"headless": headless, **browser_type_launch_args}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Настройки каждой новой страницы: адрес фронтенда, размер окна, сертификаты. Без входа."""
    return {
        **browser_context_args,
        "base_url": ACTIVE_CONFIG["app_frontend_url"],
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True,  # тестовые HTTPS-сертификаты
    }


# ------------------------------------------------------------------------
# Вход: авторизация один раз на запуск, auth_page использует сохранённые cookies
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app_storage_state(browser, browser_context_args) -> dict:
    """Вход один раз на запуск; cookies переиспользуют все тесты с auth_page."""
    context = browser.new_context(**browser_context_args)
    try:
        login_page = LoginPage(context.new_page())
        login_page.open()
        login_page.login_user(ACTIVE_CONFIG["app_frontend_login"], ACTIVE_CONFIG["app_frontend_password"])
        login_page.check_logged_in()
        return context.storage_state()
    finally:
        context.close()


@pytest.fixture
def auth_page(new_context, app_storage_state) -> Page:
    """Новая страница, пользователь уже вошёл."""
    return new_context(storage_state=app_storage_state).new_page()


# ------------------------------------------------------------------------
# Отчёт при падении: прикладываем скриншот и адрес каждой открытой страницы
# ------------------------------------------------------------------------

@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call" and report.failed:
        for name, value in item.funcargs.items():
            if isinstance(value, Page) and not value.is_closed():
                try:
                    allure.attach(value.url, name=f"{name}: адрес", attachment_type=allure.attachment_type.URI_LIST)
                    allure.attach(
                        value.screenshot(full_page=True),
                        name=f"{name}: скриншот",
                        attachment_type=allure.attachment_type.PNG,
                    )
                except Exception as error:  # браузер уже недоступен — отчёт важнее вложения
                    allure.attach(str(error), name=f"{name}: вложение не снято")
    return report
