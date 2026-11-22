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

Пароль и токен вводите через ``fill(значение, secret=True)``: при падении шага исходная ошибка
Playwright с введённым значением не попадает в traceback. Аргумент самого метода страницы
pytest показывает при ``--tb=long``, поэтому метод входа лучше читает пароль из ACTIVE_CONFIG сам,
а не принимает его параметром.

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

При падении шага текст ошибки начинается с пути шагов, внутренние кадры ядра скрыты из traceback:
    Добавить замещающего Иванов И.И. → Клик → Кнопка «Добавить»: не дождались за 20 с.
Локатор, который нашёл несколько элементов: «…: найдено 3 элементов, ожидался 1.»

При падении к отчёту Allure прикладываются скриншот и адрес каждой страницы теста, а после
закрытия браузера — trace Playwright (вложение «trace», RUN_DIR/playwright): по умолчанию
--tracing retain-on-failure, явный --tracing off или on важнее. Открыть trace:
``playwright show-trace trace.zip``. В trace видны введённые значения, в том числе пароль:
не публикуйте trace из CI без необходимости.
Ключи запуска: --headed (показать окно), --browser firefox.
"""

from __future__ import annotations

from qa.base.config import require

require(__name__, "ui", "playwright", "pytest_playwright")

# Остальные импорты — после проверки: без зависимостей ошибка называет профиль, а не модуль.
import os
import re
import shlex
from typing import NoReturn

import allure
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from qa.base import config as harness_config
from qa.base.report import current_steps

# ------------------------------------------------------------------------
# Шаги браузера: ошибки Playwright превращаются в AssertionError с вложением
# ------------------------------------------------------------------------

STRICT_VIOLATION = re.compile(r"strict mode violation: .* resolved to (\d+) elements")


class _allure_step:  # noqa: N801 — используется как функция: with _allure_step(...)
    """Шаг Allure; ошибка Playwright превращается в понятное падение с вложением «Ошибка».

    Класс, а не @contextmanager: кадры contextlib нельзя скрыть из traceback.
    ``hide_cause`` оставлен для совместимости: исходное исключение не прикладывается никогда —
    его текст уже в сообщении, а его traceback — внутренности Playwright и аргументы вызова (пароль).
    """

    def __init__(self, title: str, timeout_ms: float, hide_cause: bool = False) -> None:
        self.title = title
        self.timeout_ms = timeout_ms
        self.step = allure.step(title)

    def __enter__(self) -> None:
        self.step.__enter__()

    def __exit__(self, exc_type, error, tb) -> bool:
        __tracebackhide__ = True
        if error is None:
            self.step.__exit__(None, None, None)
            return False
        try:
            _raise_readable(self.title, self.timeout_ms, error)
        except AssertionError as readable:
            # шаг Allure закрывается понятной ошибкой: статус failed (красный), а не broken
            self.step.__exit__(type(readable), readable, readable.__traceback__)
            raise
        self.step.__exit__(exc_type, error, tb)  # не ошибка Playwright — как есть
        return False


def _raise_readable(title: str, timeout_ms: float, error: BaseException) -> None:
    """Ошибку Playwright или expect — в AssertionError с путём шагов; остальные пропускаем как есть."""
    __tracebackhide__ = True
    if getattr(error, "qa_readable", False):  # уже понятная ошибка вложенного шага
        return
    strict = STRICT_VIOLATION.search(str(error))
    if strict and isinstance(error, (PlaywrightError, AssertionError)):
        _fail(f"{title}: найдено {strict.group(1)} элементов, ожидался 1.", error)
    if isinstance(error, PlaywrightTimeoutError):
        _fail(f"{title}: не дождались за {timeout_ms / 1000:g} с.", error)
    if isinstance(error, AssertionError):  # проверка expect(...) не прошла
        _fail(f"{title}: проверка не прошла.", error)
    if isinstance(error, PlaywrightError):
        _fail(f"{title}: ошибка Playwright.", error)


def _fail(message: str, error: BaseException) -> NoReturn:
    __tracebackhide__ = True
    path = current_steps()[:-1]  # последний — шаг самого действия, он уже в message
    if path:
        message = " → ".join(path) + " → " + message
    details = f"{message}\n{error}"
    allure.attach(details, name="Ошибка", attachment_type=allure.attachment_type.TEXT)
    failure = AssertionError(details)
    failure.qa_readable = True  # внешний _allure_step не переписывает текст
    raise failure from None


# ------------------------------------------------------------------------
# Элемент: локатор, понятное имя для отчёта и таймаут ожидания
# ------------------------------------------------------------------------

class BaseElement:
    def __init__(self, locator: Locator, name: str, timeout: float = 20) -> None:
        self.locator = locator
        self.name = name
        self.timeout = timeout * 1000  # мс: Playwright ждёт в миллисекундах

    def _step(self, action: str, hide_cause: bool = False):
        """Шаг «<действие> → <имя элемента>» с обработкой ошибок."""
        return _allure_step(f"{action} → {self.name}", self.timeout, hide_cause)

    # ------------------------------------------------------------------------
    # Действия: Playwright сам ждёт, пока элемент станет видимым и доступным
    # ------------------------------------------------------------------------

    def click(self) -> None:
        __tracebackhide__ = True
        with self._step("Клик"):
            self.locator.click(timeout=self.timeout)

    def fill(self, text: str, secret: bool = False) -> None:
        """``secret=True`` — пароль, токен: значение не попадает ни в шаг, ни в traceback падения."""
        __tracebackhide__ = True  # аргумент text — значение поля, в том числе пароль
        with self._step("Ввод текста", hide_cause=secret):
            self.locator.fill(text, timeout=self.timeout)

    def press_key(self, key: str) -> None:
        """``Enter``, ``Escape``, ``ArrowDown``..."""
        __tracebackhide__ = True
        with self._step(f"Нажатие {key}"):
            self.locator.press(key, timeout=self.timeout)

    def hover(self) -> None:
        __tracebackhide__ = True
        with self._step("Наведение"):
            self.locator.hover(timeout=self.timeout)

    def get_text(self) -> str:
        __tracebackhide__ = True
        with self._step("Чтение текста"):
            return self.locator.inner_text(timeout=self.timeout)

    def get_attribute(self, name: str) -> str | None:
        __tracebackhide__ = True
        with self._step(f"Чтение атрибута {name}"):
            return self.locator.get_attribute(name, timeout=self.timeout)

    # ------------------------------------------------------------------------
    # Проверки: expect ждёт нужного состояния до таймаута, потом падает
    # ------------------------------------------------------------------------

    def check_visible(self) -> None:
        __tracebackhide__ = True
        with self._step("Проверка: виден"):
            expect(self.locator).to_be_visible(timeout=self.timeout)

    def check_hidden(self) -> None:
        __tracebackhide__ = True
        with self._step("Проверка: не виден"):
            expect(self.locator).to_be_hidden(timeout=self.timeout)

    def check_enabled(self) -> None:
        __tracebackhide__ = True
        with self._step("Проверка: доступен"):
            expect(self.locator).to_be_enabled(timeout=self.timeout)

    def check_disabled(self) -> None:
        __tracebackhide__ = True
        with self._step("Проверка: недоступен"):
            expect(self.locator).to_be_disabled(timeout=self.timeout)

    def check_editable(self) -> None:
        """Поле можно редактировать: не disabled и не readonly."""
        __tracebackhide__ = True
        with self._step("Проверка: редактируется"):
            expect(self.locator).to_be_editable(timeout=self.timeout)

    def check_not_editable(self) -> None:
        """Поле нельзя редактировать: disabled или readonly."""
        __tracebackhide__ = True
        with self._step("Проверка: не редактируется"):
            expect(self.locator).not_to_be_editable(timeout=self.timeout)

    def check_have_text(self, text: str) -> None:
        """Текст элемента совпадает целиком."""
        __tracebackhide__ = True
        with self._step(f"Проверка: текст «{text}»"):
            expect(self.locator).to_have_text(text, timeout=self.timeout)

    def check_contain_text(self, text: str) -> None:
        """Текст элемента содержит подстроку."""
        __tracebackhide__ = True
        with self._step(f"Проверка: содержит «{text}»"):
            expect(self.locator).to_contain_text(text, timeout=self.timeout)

    def check_have_value(self, value: str) -> None:
        """Значение поля ввода."""
        __tracebackhide__ = True
        with self._step(f"Проверка: значение «{value}»"):
            expect(self.locator).to_have_value(value, timeout=self.timeout)

    def check_have_attribute(self, name: str, value: str) -> None:
        __tracebackhide__ = True
        with self._step(f"Проверка: {name}=«{value}»"):
            expect(self.locator).to_have_attribute(name, value, timeout=self.timeout)

    def check_count(self, count: int) -> None:
        """Сколько элементов находит локатор (строки таблицы, пункты списка)."""
        __tracebackhide__ = True
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
        __tracebackhide__ = True
        with _allure_step(f"Открыть {path}", self.timeout * 1000):
            self.page.goto(path, timeout=self.timeout * 1000)

    # ------------------------------------------------------------------------
    # Проверки адреса: expect ждёт перехода до заданного таймаута
    # ------------------------------------------------------------------------

    def check_url_contains(self, part: str, timeout: float = 20) -> None:
        """Адрес страницы содержит ``part`` (ждёт перехода до таймаута)."""
        __tracebackhide__ = True
        with _allure_step(f"Проверка: адрес содержит «{part}»", timeout * 1000):
            expect(self.page).to_have_url(re.compile(re.escape(part)), timeout=timeout * 1000)

    def check_url_not_contains(self, part: str, timeout: float = 20) -> None:
        """Адрес страницы не содержит ``part`` (ждёт ухода со страницы до таймаута)."""
        __tracebackhide__ = True
        with _allure_step(f"Проверка: адрес не содержит «{part}»", timeout * 1000):
            expect(self.page).not_to_have_url(re.compile(re.escape(part)), timeout=timeout * 1000)


VIEWPORT = {"width": 1920, "height": 1080}


# ------------------------------------------------------------------------
# Артефакты: скриншоты и trace Playwright — в папке запуска
# Свой путь задаётся ключом --output
# ------------------------------------------------------------------------

@pytest.hookimpl(trylast=True)  # после qa.hooks.common: RUN_DIR считается от корня запуска, а не от cwd
def pytest_configure(config):
    # pytest-playwright читает --output только в фикстурах, поэтому позднего хука достаточно.
    if getattr(config.option, "output", None) == "test-results":  # значение по умолчанию pytest-playwright
        config.option.output = str(harness_config.RUN_DIR / "playwright")
    # trace упавших тестов — по умолчанию; явный --tracing из командной строки важнее
    if getattr(config.option, "tracing", None) == "off" and not _option_given(config, "--tracing"):
        config.option.tracing = "retain-on-failure"


def _option_given(config, option: str) -> bool:
    """Ключ задан явно: в командной строке, в addopts из pytest.ini или в PYTEST_ADDOPTS."""
    args = [
        *config.invocation_params.args,
        *config.getini("addopts"),
        *shlex.split(os.environ.get("PYTEST_ADDOPTS", "")),
    ]
    return any(arg == option or arg.startswith(option + "=") for arg in args)


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
# Отчёт при падении: прикладываем скриншот и адрес каждой открытой страницы,
# после закрытия браузера — trace Playwright
# ------------------------------------------------------------------------

@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "teardown":
        _attach_traces(item, report)
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


def _attach_traces(item, report) -> None:
    """trace.zip, который pytest-playwright сохранил при закрытии контекста, — вложение «trace».

    Путь pytest-playwright кладёт в user_properties отчёта teardown (относительно папки запуска).
    Открыть: ``playwright show-trace <файл>`` или https://trace.playwright.dev.
    """
    for name, path in report.user_properties:
        if name != "playwright_trace":
            continue
        trace = item.config.invocation_params.dir / path
        try:
            allure.attach.file(str(trace), name="trace", extension="zip")
        except OSError as error:  # файл не дописан или удалён — отчёт важнее вложения
            allure.attach(str(error), name="trace: вложение не снято")
