"""Проверки OData-ответов: $select, $filter, $top, $skip, $count, $expand, $orderby.

    items = app_api.get_items("/api/v1/orders", {"$filter": "Status eq 'Draft'"})
    checker = OdataChecker()
    checker.check_not_empty(items)
    checker.check_filter_eq(items, "Status", "Draft")
    checker.assert_valid()

Проверки не делают запросов, а работают с уже полученными записями.
Общие проверки (ответ не пустой, схема) — в checks/base.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import allure

from checks.base import Checker

ODATA_SYSTEM_FIELDS = ("@odata.id", "@odata.etag", "@odata.editLink")


class OdataChecker(Checker):
    # --- $select ---

    @allure.step("$select={field}: есть непустые значения")
    def check_select_property(self, items: list[dict], field: str) -> OdataChecker:
        """Хотя бы у одной записи поле заполнено."""
        if not any(item.get(field) not in (None, "") for item in items):
            self.fail(f"$select={field}: ни одного непустого значения")
        return self

    @allure.step("$select: в ответе нет лишних полей")
    def check_select_strict(self, items: list[dict], fields: list[str]) -> OdataChecker:
        """В записях только выбранные поля и системные поля OData."""
        extra = {key for item in items for key in item} - set(fields) - set(ODATA_SYSTEM_FIELDS)
        if extra:
            self.fail(f"$select: лишние поля {sorted(extra)}, ожидались только {fields}")
        return self

    # --- $filter ---

    @allure.step("$filter: {field} eq {expected}")
    def check_filter_eq(self, items: list[dict], field: str, expected: Any) -> OdataChecker:
        return self._check_all(items, field, lambda value: value == expected, f"{field} eq {expected!r}")

    @allure.step("$filter: {field} ne {unexpected}")
    def check_filter_ne(self, items: list[dict], field: str, unexpected: Any) -> OdataChecker:
        return self._check_all(items, field, lambda value: value != unexpected, f"{field} ne {unexpected!r}")

    @allure.step("$filter: {field} содержит {substring}")
    def check_filter_contains(self, items: list[dict], field: str, substring: str) -> OdataChecker:
        """Строковое поле содержит подстроку (с учётом регистра)."""
        return self._check_all(
            items, field, lambda value: substring in (value or ""), f"contains({field}, {substring!r})"
        )

    @allure.step("$filter: {field} от {start} до {end}")
    def check_filter_date_range(
        self, items: list[dict], field: str, start: date | str, end: date | str
    ) -> OdataChecker:
        """Дата записи в диапазоне [start, end]; даты — date или строки «2026-01-31»."""
        start, end = _to_date(start), _to_date(end)

        def in_range(value: Any) -> bool:
            day = _to_date(value)
            return day is not None and start <= day <= end

        return self._check_all(items, field, in_range, f"{field} от {start} до {end}")

    # --- $top, $skip, $count ---

    @allure.step("$top={limit}: записей не больше лимита")
    def check_top_limit(self, items: list[dict], limit: int) -> OdataChecker:
        if len(items) > limit:
            self.fail(f"$top={limit}: вернулось {len(items)} записей")
        return self

    @allure.step("$skip={skip}: страница сдвинута")
    def check_skip(
        self, first_page: list[dict], skipped_page: list[dict], skip: int, key_field: str = "Id"
    ) -> OdataChecker:
        """Первая запись страницы со $skip — запись номер ``skip`` первой страницы (при одном $orderby)."""
        if len(first_page) <= skip or not skipped_page:
            self.fail(f"$skip={skip}: мало записей для проверки: {len(first_page)} и {len(skipped_page)}")
        elif first_page[skip].get(key_field) != skipped_page[0].get(key_field):
            self.fail(
                f"$skip={skip}: первая запись {key_field}={skipped_page[0].get(key_field)}, "
                f"ожидалась {first_page[skip].get(key_field)}"
            )
        return self

    @allure.step("$count: в ответе есть @odata.count")
    def check_count(self, response: dict) -> OdataChecker:
        """В ответе целое ``@odata.count`` и записей в ``value`` не больше него."""
        count = response.get("@odata.count")
        items = response.get("value", [])
        if not isinstance(count, int):
            self.fail(f"$count: @odata.count = {count!r}, ожидалось целое число")
        elif len(items) > count:
            self.fail(f"$count: в value {len(items)} записей, больше чем @odata.count = {count}")
        return self

    # --- $expand, $orderby ---

    @allure.step("$expand={field}: связанные данные на месте")
    def check_expand_field(
        self, items: list[dict], field: str, expected_type: type | None = None
    ) -> OdataChecker:
        """У каждой записи заполнено поле; ``expected_type``: list — коллекция, dict — одна запись."""
        return self._check_all(
            items,
            field,
            lambda value: value is not None and (expected_type is None or isinstance(value, expected_type)),
            f"$expand={field}",
        )

    @allure.step("$orderby: сортировка по {field}")
    def check_orderby(self, items: list[dict], field: str, reverse: bool = False) -> OdataChecker:
        """Непустые значения поля идут по порядку.

        Если бэкенд сортирует без учёта регистра или по правилам языка, порядок
        Python ``sorted()`` может отличаться — тогда сравнивайте по-своему.
        """
        if any(field not in item for item in items):
            self.fail(f"$orderby: поля {field} нет в записях ответа")
            return self
        values = [item[field] for item in items if item[field] is not None]
        if values != sorted(values, reverse=reverse):
            self.fail(f"$orderby: записи не отсортированы по {field} {'desc' if reverse else 'asc'}: {values[:10]}")
        return self

    # --- служебное ---

    def _check_all(self, items: list[dict], field: str, is_valid: Callable[[Any], bool], rule: str) -> OdataChecker:
        """Одна ошибка на все записи, где значение поля не подходит: сколько их и какие значения."""
        bad = [item.get(field) for item in items if not is_valid(item.get(field))]
        if bad:
            self.fail(f"{rule}: не подходят {len(bad)} из {len(items)} записей, значения: {bad[:5]}")
        return self


def _to_date(value: Any) -> date | None:
    """date, datetime или ISO-строка («2026-01-31», «2026-01-31T10:00:00Z») → date; иначе None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None
