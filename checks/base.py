"""Основа проверок: ошибки копятся, тест падает в конце одним сообщением обо всех.

    with Checker() as checker:
        checker.check_no_rows(rows, "Заказы без проекта")
        checker.check_equal(len(items), 5, "Записей на странице")

Выход из ``with`` вызывает ``assert_valid()``. Если проверки шли без ``with`` и ``assert_valid()``
забыли, тест всё равно упадёт: корневой conftest.py проверяет накопленные ошибки после теста.

Каждая проверка — шаг Allure (``@step`` из report.py). Проваленная проверка отмечается
в отчёте красным, но тест идёт дальше: независимые проверки выполняются все.

Проверки содержимого на пустых данных проходят: если пустой ответ — ошибка, сначала
``check_not_empty``. Порядок в тесте: структура (не пустой, схема, колонки), потом содержимое.

Новая проверка — метод ``check_<что>`` с декоратором ``@step("Заголовок {аргумент}")``:
при ошибке вызывает ``self.fail(текст)`` и возвращает ``self``. Проверки одной темы —
класс-наследник в своём файле: ``class OdataChecker(Checker)`` в checks/odata.py.
"""

from __future__ import annotations

import pprint
from typing import Any

import allure
from pydantic import BaseModel, ValidationError

from report import step

MAX_SHOWN_ROWS = 20  # сколько найденных строк показать в сообщении об ошибке

# Checker'ы текущего теста: корневой conftest.py роняет тест, если ошибки остались непоказанными.
_active: list[Checker] = []


class Checker:
    collects_errors = True  # @step отмечает шаг красным, если метод записал ошибку

    def __init__(self, title: str = "") -> None:
        self.title = title  # первая строка сообщения об ошибках, например имя отчёта
        self.errors: list[str] = []
        self.reported = 0  # сколько ошибок уже показал assert_valid()
        _active.append(self)

    def __enter__(self) -> Checker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:  # тест уже падает по другой причине — не подменяем его ошибку
            self.assert_valid()

    def fail(self, message: str) -> Checker:
        """Записать ошибку: тест упадёт на ``assert_valid()``; текст прикладывается к шагу Allure."""
        self.errors.append(message)
        allure.attach(message, name="Ошибка", attachment_type=allure.attachment_type.TEXT)
        return self

    @step("Проверка: {message}")
    def check_true(self, condition: bool, message: str) -> Checker:
        if not condition:
            self.fail(message)
        return self

    @step("Проверка: {message}")
    def check_equal(self, actual: Any, expected: Any, message: str) -> Checker:
        if actual != expected:
            self.fail(f"{message}: ожидалось {expected!r}, получено {actual!r}")
        return self

    @step("Проверка: ответ не пустой")
    def check_not_empty(self, data: Any, message: str = "Ответ пустой") -> Checker:
        if not data:
            self.fail(message)
        return self

    @step("Проверка: ответ соответствует схеме {model}")
    def check_schema(self, data: dict | list[dict], model: type[BaseModel]) -> Checker:
        """Объект или каждый объект списка проходит валидацию pydantic-модели."""
        items = data if isinstance(data, list) else [data]
        bad = []
        for index, item in enumerate(items):
            try:
                model.model_validate(item)
            except ValidationError as error:
                bad.append(f"[{index}] {error}")
        if bad:
            more = f"\n... и ещё {len(bad) - MAX_SHOWN_ROWS}" if len(bad) > MAX_SHOWN_ROWS else ""
            self.fail(
                f"Не соответствуют схеме {model.__name__}: {len(bad)} из {len(items)}\n"
                + "\n".join(bad[:MAX_SHOWN_ROWS])
                + more
            )
        return self

    @step("Проверка: нет строк «{message}»")
    def check_no_rows(self, rows: list, message: str) -> Checker:
        """Запрос, который ищет нарушения, ничего не нашёл; иначе в ошибке — первые найденные строки."""
        if rows:
            more = f"\n... и ещё {len(rows) - MAX_SHOWN_ROWS}" if len(rows) > MAX_SHOWN_ROWS else ""
            self.fail(f"{message}: {len(rows)} шт.\n{pprint.pformat(rows[:MAX_SHOWN_ROWS], width=120)}{more}")
        return self

    def assert_valid(self) -> None:
        """Падает одним сообщением обо всех накопленных ошибках."""
        self.reported = len(self.errors)
        if not self.errors:
            return
        with allure.step(f"Итог: ошибок {len(self.errors)}"):
            header = [self.title] if self.title else []
            raise AssertionError("\n\n" + "\n\n".join(header + self.errors))


# --- для корневого conftest.py ------------------------------------------------

def start_test() -> None:
    """Перед тестом: забыть checker'ы прошлых тестов."""
    _active.clear()


def unreported_errors() -> list[str]:
    """Ошибки, которые тест накопил, но не показал через ``with`` или ``assert_valid()``."""
    errors = []
    for checker in _active:
        new = checker.errors[checker.reported:]
        if new:
            errors += ([checker.title] if checker.title else []) + new
    _active.clear()
    return errors

