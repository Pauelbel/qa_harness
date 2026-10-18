"""Шаги отчёта Allure: один декоратор ``@step`` для проверок, страниц и любых методов.

    @step("Авторизация пользователя {username}")
    def login_user(self, username, password): ...

Почему не ``@allure.step``:
    - ``@allure.step`` сохраняет все аргументы метода параметрами шага в файлы allure-results:
      пароли, целые ответы и таблицы. ``@step`` пишет только заголовок; ``{имя}`` в нём —
      значение аргумента, коллекции длиннее 5 элементов показываются как «<list из 1000>»;
    - метод Checker'а не бросает исключение при ошибке, а копит её. ``@step`` всё равно
      отмечает такой шаг красным, а тест идёт дальше (см. checks/base.py).

Для блока внутри метода — обычный ``with allure.step("..."):``: он аргументов не сохраняет.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

import allure

MAX_TITLE_VALUE = 80  # длина значения аргумента в заголовке шага

F = TypeVar("F", bound=Callable[..., Any])


class CheckFailed(AssertionError):
    """Проверка записала ошибку: ловится сразу за шагом, чтобы шаг стал красным, а тест шёл дальше."""


def step(title: str) -> Callable[[F], F]:
    """Шаг Allure с заголовком ``title``; ``{имя}`` — значение аргумента метода."""

    def decorator(func: F) -> F:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            step_title = title.format_map({name: _short(value) for name, value in bound.arguments.items()})

            # Checker (collects_errors = True) копит ошибки в self.errors вместо исключений.
            owner = args[0] if args and getattr(args[0], "collects_errors", False) else None
            if owner is None:
                with allure.step(step_title):
                    return func(*args, **kwargs)

            errors_before = len(owner.errors)
            result = None
            try:
                with allure.step(step_title):
                    result = func(*args, **kwargs)
                    new_errors = owner.errors[errors_before:]
                    if new_errors:
                        raise CheckFailed("\n\n".join(new_errors))
            except CheckFailed:
                pass  # ошибка уже в owner.errors; тест упадёт в assert_valid()
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def _short(value: Any) -> str:
    """Значение аргумента для заголовка шага: имя класса, длина коллекции или обрезанный текст."""
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, (list, tuple, set, dict)) and len(value) > 5:
        return f"<{type(value).__name__} из {len(value)}>"
    text = str(value)
    return text if len(text) <= MAX_TITLE_VALUE else text[:MAX_TITLE_VALUE] + "…"
