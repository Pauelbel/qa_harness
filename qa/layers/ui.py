"""Слой UI: Page Object, браузер, вход один раз на запуск и вложения при падении. Профиль requirements/ui.txt.

    pytest_plugins = ["qa.hooks.common", "qa.layers.ui", ...]

Page Object: элемент знает своё имя для отчёта, страница открывается от base_url браузера.
Каждое действие и проверка элемента — шаг Allure «Клик → Кнопка «Войти»».
Если не вышло, тест падает с понятным текстом, а текст ошибки прикладывается к шагу.

    LOGIN_BTN = "button[type='submit']"

    class LoginPage(BasePage):
        @step("Вход пользователя {username}")
        def login_user(self, username, password):
            ...
            self.element("Кнопка «Войти»", LOGIN_BTN).click()

Методы страниц — с декоратором ``@step`` из qa/base/report.py, а не ``@allure.step``:
он не сохраняет аргументы (пароль) в файлы отчёта.

Браузер даёт pytest-playwright. Фикстуры для тестов:
    page       — страница без входа (стандартная фикстура pytest-playwright);
    auth_page  — страница, где пользователь уже вошёл: вход выполняется один раз на запуск
                 и только если хотя бы одному тесту нужна auth_page.

Модуль не знает адреса фронтенда и страницы входа — их задаёт проект в conftest.py рядом с тестами:
    ui_base_url — адрес фронтенда; от него считаются пути: ``page.goto("/orders")``;
    ui_login    — функция ``login(page)``: войти на чистой странице (через свой LoginPage).

    @pytest.fixture(scope="session")
    def ui_base_url():
        return ACTIVE_CONFIG["app_frontend_url"]

    @pytest.fixture(scope="session")
    def ui_login():
        def login(page):
            login_page = LoginPage(page)
            login_page.open()
            login_page.login_user(ACTIVE_CONFIG["app_frontend_login"], ACTIVE_CONFIG["app_frontend_password"])
            login_page.check_logged_in()
        return login

При падении к отчёту Allure прикладываются скриншот и адрес каждой страницы теста.
Ключи запуска: --headed (показать окно), --browser firefox, --tracing retain-on-failure
(trace упавших тестов — в RUN_DIR/playwright). В trace видны введённые значения, в том числе пароль:
не публикуйте trace из CI без необходимости.
"""

from __future__ import annotations

from qa.base.config import require

require(__name__, "ui", "playwright", "pytest_playwright")

# Остальные импорты — после проверки: без зависимостей ошибка называет профиль, а не модуль.
import os
import re
from collections.abc import Generator
from contextlib import contextmanager
from typing import NoReturn

import allure
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from qa.base import config as harness_config

# ------------------------------------------------------------------------
# Шаги браузера: ошибки Playwright превращаются в AssertionError с вложением
# ------------------------------------------------------------------------

@contextmanager
def _allure_step(title: str, timeout_ms: float) -> Generator[None, None, None]:
    """Шаг Allure; ошибка Playwright превращается в понятное падение с вложением «Ошибка»."""
    with allure.step(title):
        try:
            yield
        except PlaywrightTimeoutError as error:
            _fail(f"{title}: не дождались за {timeout_ms / 1000:g} с.", error)
        except AssertionError as error:  # проверка expect(...) не прошла
            _fail(f"{title}: проверка не прошла.", error)
        except PlaywrightError as error:  # например, локатор нашёл несколько элементов
            _fail(f"{title}: ошибка Playwright.", error)


def _fail(message: str, error: Exception) -> NoReturn:
    details = f"{message}\n{error}"
    allure.attach(details, name="Ошибка", attachment_type=allure.attachment_type.TEXT)
    raise AssertionError(details) from error


# ------------------------------------------------------------------------
# Элемент: локатор, понятное имя для отчёта и таймаут ожидания
# ------------------------------------------------------------------------

class BaseElement:
    def __init__(self, locator: Locator, name: str, timeout: float = 20) -> None:
        self.locator = locator
        self.name = name
        self.timeout = timeout * 1000  # мс: Playwright ждёт в миллисекундах

    def _step(self, action: str):
        """Шаг «<действие> → <имя элемента>» с обработкой ошибок."""
        return _allure_step(f"{action} → {self.name}", self.timeout)

    # ------------------------------------------------------------------------
    # Действия: Playwright сам ждёт, пока элемент станет видимым и доступным
    # ------------------------------------------------------------------------

    def click(self) -> None:
        with self._step("Клик"):
            self.locator.click(timeout=self.timeout)

    def fill(self, text: str) -> None:
        with self._step("Ввод текста"):
            self.locator.fill(text, timeout=self.timeout)

    def press_key(self, key: str) -> None:
        """``Enter``, ``Escape``, ``ArrowDown``..."""
        with self._step(f"Нажатие {key}"):
            self.locator.press(key, timeout=self.timeout)

    def hover(self) -> None:
        with self._step("Наведение"):
            self.locator.hover(timeout=self.timeout)

    def get_text(self) -> str:
        with self._step("Чтение текста"):
            return self.locator.inner_text(timeout=self.timeout)

    def get_attribute(self, name: str) -> str | None:
        with self._step(f"Чтение атрибута {name}"):
            return self.locator.get_attribute(name, timeout=self.timeout)

    # ------------------------------------------------------------------------
    # Проверки: expect ждёт нужного состояния до таймаута, потом падает
    # ------------------------------------------------------------------------

    def check_visible(self) -> None:
        with self._step("Проверка: виден"):
            expect(self.locator).to_be_visible(timeout=self.timeout)

    def check_hidden(self) -> None:
        with self._step("Проверка: не виден"):
            expect(self.locator).to_be_hidden(timeout=self.timeout)

    def check_enabled(self) -> None:
        with self._step("Проверка: доступен"):
            expect(self.locator).to_be_enabled(timeout=self.timeout)

    def check_disabled(self) -> None:
        with self._step("Проверка: недоступен"):
            expect(self.locator).to_be_disabled(timeout=self.timeout)

    def check_have_text(self, text: str) -> None:
        """Текст элемента совпадает целиком."""
        with self._step(f"Проверка: текст «{text}»"):
            expect(self.locator).to_have_text(text, timeout=self.timeout)

    def check_contain_text(self, text: str) -> None:
        """Текст элемента содержит подстроку."""
        with self._step(f"Проверка: содержит «{text}»"):
            expect(self.locator).to_contain_text(text, timeout=self.timeout)

    def check_have_value(self, value: str) -> None:
        """Значение поля ввода."""
        with self._step(f"Проверка: значение «{value}»"):
            expect(self.locator).to_have_value(value, timeout=self.timeout)

    def check_have_attribute(self, name: str, value: str) -> None:
        with self._step(f"Проверка: {name}=«{value}»"):
            expect(self.locator).to_have_attribute(name, value, timeout=self.timeout)

    def check_count(self, count: int) -> None:
        """Сколько элементов находит локатор (строки таблицы, пункты списка)."""
        with self._step(f"Проверка: количество {count}"):
            expect(self.locator).to_have_count(count, timeout=self.timeout)


# ------------------------------------------------------------------------
# Страница: открытие от base_url браузера и проверки переходов по адресу
# ------------------------------------------------------------------------

class BasePage:
    timeout = 30  # секунд на загрузку страницы

    def __init__(self, page: Page) -> None:
        self.page = page

    def element(self, name: str, selector: str | Locator, timeout: float = 20) -> BaseElement:
        """Элемент по CSS/XPath или готовому локатору (``page.get_by_role(...)``)."""
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        return BaseElement(locator, name, timeout)

    # ------------------------------------------------------------------------
    # Навигация: относительный путь считается от base_url в browser_context_args
    # ------------------------------------------------------------------------

    def open(self, path: str = "/") -> None:
        """Открыть страницу; ``path`` считается от base_url браузера (его задаёт browser_context_args)."""
        with _allure_step(f"Открыть {path}", self.timeout * 1000):
            self.page.goto(path, timeout=self.timeout * 1000)

    # ------------------------------------------------------------------------
    # Проверки адреса: expect ждёт перехода до заданного таймаута
    # ------------------------------------------------------------------------

    def check_url_contains(self, part: str, timeout: float = 20) -> None:
        """Адрес страницы содержит ``part`` (ждёт перехода до таймаута)."""
        with _allure_step(f"Проверка: адрес содержит «{part}»", timeout * 1000):
            expect(self.page).to_have_url(re.compile(re.escape(part)), timeout=timeout * 1000)

    def check_url_not_contains(self, part: str, timeout: float = 20) -> None:
        """Адрес страницы не содержит ``part`` (ждёт ухода со страницы до таймаута)."""
        with _allure_step(f"Проверка: адрес не содержит «{part}»", timeout * 1000):
            expect(self.page).not_to_have_url(re.compile(re.escape(part)), timeout=timeout * 1000)


VIEWPORT = {"width": 1920, "height": 1080}


# ------------------------------------------------------------------------
# Артефакты: скриншоты и trace Playwright — в папке запуска
# Свой путь задаётся ключом --output
# ------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if getattr(config.option, "output", None) == "test-results":  # значение по умолчанию pytest-playwright
        config.option.output = str(harness_config.RUN_DIR / "playwright")


# ------------------------------------------------------------------------
# Браузер: настройки запуска и контекста применяются к новым страницам
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Окно браузера видно по умолчанию; в CI — HEADLESS=true."""
    headless = os.getenv("HEADLESS", "false").lower() == "true"
    return {"headless": headless, **browser_type_launch_args}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, ui_base_url):
    """Настройки каждой новой страницы: адрес фронтенда, размер окна, сертификаты. Без входа."""
    return {
        **browser_context_args,
        "base_url": ui_base_url,
        "viewport": VIEWPORT,
        "ignore_https_errors": True,  # тестовые HTTPS-сертификаты
    }


# ------------------------------------------------------------------------
# Фикстуры проекта: заглушки с подсказкой, проект переопределяет их в conftest.py
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ui_base_url() -> str:
    """Адрес фронтенда. Определите фикстуру ui_base_url в conftest.py рядом с тестами."""
    pytest.fail("Определите фикстуру ui_base_url в tests/conftest.py")


@pytest.fixture(scope="session")
def ui_login():
    """Функция входа ``login(page)``. Определите фикстуру ui_login в conftest.py рядом с тестами."""
    pytest.fail("Определите фикстуру ui_login в tests/conftest.py")


# ------------------------------------------------------------------------
# Вход: авторизация один раз на запуск, auth_page использует сохранённые cookies
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ui_storage_state(browser, browser_context_args, ui_login) -> dict:
    """Вход один раз на запуск; cookies переиспользуют все тесты с auth_page."""
    context = browser.new_context(**browser_context_args)
    try:
        ui_login(context.new_page())
        return context.storage_state()
    finally:
        context.close()


@pytest.fixture
def auth_page(new_context, ui_storage_state) -> Page:
    """Новая страница, пользователь уже вошёл."""
    return new_context(storage_state=ui_storage_state).new_page()


# ------------------------------------------------------------------------
# Отчёт при падении: прикладываем скриншот и адрес каждой открытой страницы
# ------------------------------------------------------------------------

@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call" and report.failed:
        for name, value in getattr(item, "funcargs", {}).items():
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
