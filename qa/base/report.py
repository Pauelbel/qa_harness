"""Шаги отчёта Allure: один декоратор ``@step`` для проверок, страниц и любых методов.

    @step("Авторизация пользователя {username}")
    def login_user(self, username, password): ...

Почему не ``@allure.step``:
    - ``@allure.step`` сохраняет все аргументы метода параметрами шага в файлы allure-results:
      пароли, целые ответы и таблицы. ``@step`` пишет только заголовок; ``{имя}`` в нём —
      значение аргумента, коллекции длиннее 5 элементов показываются как «<list из 1000>»;
    - метод Checker'а не бросает исключение при ошибке, а копит её. ``@step`` всё равно
      отмечает такой шаг красным, а тест идёт дальше (см. qa/base/checks.py).

Для блока внутри метода — обычный ``with allure.step("..."):``: он аргументов не сохраняет.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, TypeVar

import allure
import allure_commons

MAX_TITLE_VALUE = 80  # длина значения аргумента в заголовке шага

F = TypeVar("F", bound=Callable[..., Any])


# ------------------------------------------------------------------------
# Ошибка шага: помечает проверку красным, не прерывая накопление ошибок
# ------------------------------------------------------------------------

class CheckFailed(AssertionError):
    """Проверка записала ошибку: ловится сразу за шагом, чтобы шаг стал красным, а тест шёл дальше."""


# ------------------------------------------------------------------------
# Декоратор @step: сохраняет заголовок без автоматической записи аргументов
# ------------------------------------------------------------------------

def step(title: str) -> Callable[[F], F]:
    """Шаг Allure с заголовком ``title``; ``{имя}`` — значение аргумента метода."""

    def decorator(func: F) -> F:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            __tracebackhide__ = True  # args — аргументы метода, в том числе пароль: в traceback не показываем
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


# ------------------------------------------------------------------------
# Стек шагов: какие шаги Allure сейчас открыты — для текста ошибки
# Плагин регистрирует qa/hooks/common.py; без него стек пуст
# ------------------------------------------------------------------------

_OPEN_STEPS: ContextVar[tuple[tuple[str, str], ...]] = ContextVar("qa_open_steps", default=())


def current_steps() -> list[str]:
    """Заголовки открытых шагов Allure, от внешнего к внутреннему."""
    return [title for _, title in _OPEN_STEPS.get()]


class StepStack:
    """Плагин allure_commons: запоминает открытые шаги (``@step``, ``allure.step``, шаги элементов)."""

    @allure_commons.hookimpl
    def start_step(self, uuid, title, params):
        _OPEN_STEPS.set((*_OPEN_STEPS.get(), (uuid, title)))

    @allure_commons.hookimpl
    def stop_step(self, uuid, exc_type, exc_val, exc_tb):
        steps = _OPEN_STEPS.get()
        ids = [step_id for step_id, _ in steps]
        if uuid in ids:  # закрываем шаг и всё, что осталось открытым внутри него
            _OPEN_STEPS.set(steps[: ids.index(uuid)])


# ------------------------------------------------------------------------
# Заголовок шага: длинные значения сокращаются, большие коллекции не раскрываются
# ------------------------------------------------------------------------

def _short(value: Any) -> str:
    """Значение аргумента для заголовка шага: имя класса, длина коллекции или обрезанный текст."""
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, (list, tuple, set, dict)) and len(value) > 5:
        return f"<{type(value).__name__} из {len(value)}>"
    text = str(value)
    return text if len(text) <= MAX_TITLE_VALUE else text[:MAX_TITLE_VALUE] + "…"
