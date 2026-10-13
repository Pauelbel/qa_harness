"""Основа проверок: ошибки копятся, ``assert_valid()`` в конце теста падает одним сообщением обо всех.

    checker = Checker()
    checker.check_no_rows(rows, "Заказы без проекта")
    checker.check_equal(len(items), 5, "Записей на странице")
    checker.assert_valid()

Новая проверка — метод ``check_<что>``: при ошибке вызывает ``self.fail(текст)`` и возвращает ``self``.
Проверки одной темы — класс-наследник в своём файле: ``class OdataChecker(Checker)`` в checks/odata.py.
"""

from __future__ import annotations

import pprint
from typing import Any

import allure
from pydantic import BaseModel, ValidationError

MAX_SHOWN_ROWS = 20  # сколько найденных строк показать в сообщении об ошибке


class Checker:
    def __init__(self, title: str = "") -> None:
        self.title = title  # первая строка сообщения об ошибках, например имя отчёта
        self.errors: list[str] = []

    def fail(self, message: str) -> Checker:
        """Записать ошибку: тест упадёт на ``assert_valid()``; текст прикладывается к шагу Allure."""
        self.errors.append(message)
        allure.attach(message, name="Ошибка", attachment_type=allure.attachment_type.TEXT)
        return self

    @allure.step("Проверка: {message}")
    def check_true(self, condition: bool, message: str) -> Checker:
        if not condition:
            self.fail(message)
        return self

    @allure.step("Проверка: {message}")
    def check_equal(self, actual: Any, expected: Any, message: str) -> Checker:
        if actual != expected:
            self.fail(f"{message}: ожидалось {expected!r}, получено {actual!r}")
        return self

    @allure.step("Проверка: ответ не пустой")
    def check_not_empty(self, data: Any, message: str = "Ответ пустой") -> Checker:
        if not data:
            self.fail(message)
        return self

    @allure.step("Проверка: ответ соответствует схеме")
    def check_schema(self, data: dict | list[dict], model: type[BaseModel]) -> Checker:
        """Объект или каждый объект списка проходит валидацию pydantic-модели."""
        for item in data if isinstance(data, list) else [data]:
            try:
                model.model_validate(item)
            except ValidationError as error:
                self.fail(f"Не соответствует схеме {model.__name__}: {error}")
        return self

    @allure.step("Проверка: нет строк «{message}»")
    def check_no_rows(self, rows: list, message: str) -> Checker:
        """Запрос, который ищет нарушения, ничего не нашёл; иначе в ошибке — первые найденные строки."""
        if rows:
            more = f"\n... и ещё {len(rows) - MAX_SHOWN_ROWS}" if len(rows) > MAX_SHOWN_ROWS else ""
            self.fail(f"{message}: {len(rows)} шт.\n{pprint.pformat(rows[:MAX_SHOWN_ROWS], width=120)}{more}")
        return self

    @allure.step("Итог: ошибок нет")
    def assert_valid(self) -> None:
        """Падает одним сообщением обо всех накопленных ошибках."""
        if self.errors:
            header = [self.title] if self.title else []
            raise AssertionError("\n\n" + "\n\n".join(header + self.errors))
