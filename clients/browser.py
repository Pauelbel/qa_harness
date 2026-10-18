"""Основа Page Object: элемент знает своё имя для отчёта, страница открывается от base_url браузера.

Каждое действие и проверка элемента — шаг Allure «Клик → Кнопка «Войти»».
Если не вышло, тест падает с понятным текстом, а текст ошибки прикладывается к шагу.

    LOGIN_BTN = "button[type='submit']"

    class LoginPage(BasePage):
        @step("Вход пользователя {username}")
        def login_user(self, username, password):
            ...
            self.element("Кнопка «Войти»", LOGIN_BTN).click()

Методы страниц — с декоратором ``@step`` из report.py, а не ``@allure.step``:
он не сохраняет аргументы (пароль) в файлы отчёта.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import NoReturn

import allure
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


@contextmanager
def _allure_step(title: str, timeout_ms: float) -> Iterator[None]:
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


class BasePage:
    timeout = 30  # секунд на загрузку страницы

    def __init__(self, page: Page) -> None:
        self.page = page

    def element(self, name: str, selector: str | Locator, timeout: float = 20) -> BaseElement:
        """Элемент по CSS/XPath или готовому локатору (``page.get_by_role(...)``)."""
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        return BaseElement(locator, name, timeout)

    def open(self, path: str = "/") -> None:
        """Открыть страницу; ``path`` считается от base_url браузера (его задаёт browser_context_args)."""
        with _allure_step(f"Открыть {path}", self.timeout * 1000):
            self.page.goto(path, timeout=self.timeout * 1000)

    def check_url_contains(self, part: str, timeout: float = 20) -> None:
        """Адрес страницы содержит ``part`` (ждёт перехода до таймаута)."""
        with _allure_step(f"Проверка: адрес содержит «{part}»", timeout * 1000):
            expect(self.page).to_have_url(re.compile(re.escape(part)), timeout=timeout * 1000)

    def check_url_not_contains(self, part: str, timeout: float = 20) -> None:
        """Адрес страницы не содержит ``part`` (ждёт ухода со страницы до таймаута)."""
        with _allure_step(f"Проверка: адрес не содержит «{part}»", timeout * 1000):
            expect(self.page).not_to_have_url(re.compile(re.escape(part)), timeout=timeout * 1000)
