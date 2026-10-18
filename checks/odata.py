"""Проверки OData-ответов: $select, $filter, $top, $skip, $count, $expand, $orderby.

    items = app_api.get_items("/api/v1/orders", {"$filter": "Status eq 'Draft'"})
    with OdataChecker() as checker:
        checker.check_not_empty(items)
        checker.check_filter_eq(items, "Status", "Draft")

Проверки не делают запросов, а работают с уже полученными записями.
Запись без проверяемого поля — всегда ошибка; ``null`` в поле — обычное значение,
подходит ли оно, решает правило проверки. Пустой список проверки $filter проходит:
чтобы фильтр что-то доказывал, создайте подходящую запись и проверьте ``check_has_record``.
Общие проверки (ответ не пустой, схема) — в checks/base.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from checks.base import Checker
from report import step

ODATA_SYSTEM_FIELDS = ("@odata.id", "@odata.etag", "@odata.editLink")


class OdataChecker(Checker):
    # --- $select ---

    @step("$select={field}: поле есть в каждой записи")
    def check_select_property(self, items: list[dict], field: str) -> OdataChecker:
        """Выбранное поле присутствует у каждой записи; ``None`` и пустая строка допустимы.

        $select задаёт состав полей, а требования к их значениям проверяются отдельно.
        Пустой список проходит: если данные обязательны, вызовите ``check_not_empty``.
        """
        missing = [index for index, item in enumerate(items) if field not in item]
        if missing:
            self.fail(
                f"$select={field}: поля нет в {len(missing)} из {len(items)} записей; "
                f"первые индексы (с нуля): {missing[:5]}"
            )
        return self

    @step("$select: в ответе все выбранные поля без лишних")
    def check_select_strict(self, items: list[dict], fields: list[str]) -> OdataChecker:
        """В каждой записи есть все выбранные поля и нет лишних, кроме системных OData.

        Значения выбранных полей (включая ``None`` и пустую строку) не проверяются.
        """
        selected = set(fields)
        missing = [
            (index, selected - item.keys())
            for index, item in enumerate(items)
            if not selected <= item.keys()
        ]
        if missing:
            examples = "; ".join(f"[{index}]: {_field_names_preview(names)}" for index, names in missing[:5])
            self.fail(
                f"$select: выбранных полей нет в {len(missing)} из {len(items)} записей; "
                f"первые индексы (с нуля) и отсутствующие поля: {examples}"
            )
        extra = {key for item in items for key in item} - selected - set(ODATA_SYSTEM_FIELDS)
        if extra:
            self.fail(f"$select: лишних полей {len(extra)}; первые имена: {_field_names_preview(extra)}")
        return self

    # --- $filter ---

    @step("$filter: {field} eq {expected}")
    def check_filter_eq(self, items: list[dict], field: str, expected: Any) -> OdataChecker:
        return self._check_all(items, field, lambda value: value == expected, f"{field} eq {expected!r}")

    @step("$filter: {field} ne {unexpected}")
    def check_filter_ne(self, items: list[dict], field: str, unexpected: Any) -> OdataChecker:
        return self._check_all(items, field, lambda value: value != unexpected, f"{field} ne {unexpected!r}")

    @step("$filter: {field} содержит {substring}")
    def check_filter_contains(self, items: list[dict], field: str, substring: str) -> OdataChecker:
        """Строковое поле содержит подстроку (с учётом регистра); не строка — нарушение."""
        return self._check_all(
            items,
            field,
            lambda value: isinstance(value, str) and substring in value,
            f"contains({field}, {substring!r})",
        )

    @step("$filter: {field} от {start} до {end}")
    def check_filter_date_range(
        self, items: list[dict], field: str, start: date | str, end: date | str
    ) -> OdataChecker:
        """Дата записи в диапазоне [start, end]; даты — date или строки «2026-01-31»."""
        start, end = _to_date(start), _to_date(end)

        def in_range(value: Any) -> bool:
            day = _to_date(value)
            return day is not None and start <= day <= end

        return self._check_all(items, field, in_range, f"{field} от {start} до {end}")

    # --- записи, созданные тестом ---

    @step("В ответе есть запись {key_field}={key}")
    def check_has_record(self, items: list[dict], key_field: str, key: Any) -> OdataChecker:
        """Запись, подходящая под запрос (например, созданная тестом), вернулась в ответе."""
        if not any(item.get(key_field) == key for item in items):
            self.fail(f"Нет записи {key_field}={key!r} среди {len(items)} записей ответа")
        return self

    @step("В ответе нет записи {key_field}={key}")
    def check_no_record(self, items: list[dict], key_field: str, key: Any) -> OdataChecker:
        """Запись, не подходящая под запрос (например, созданная тестом), в ответ не попала."""
        if any(item.get(key_field) == key for item in items):
            self.fail(f"В ответе есть запись {key_field}={key!r}, которая не должна была попасть в выборку")
        return self

    # --- $top, $skip, $count ---

    @step("$top={limit}: записей не больше лимита")
    def check_top_limit(self, items: list[dict], limit: int) -> OdataChecker:
        """Записей не больше ``limit``. Доказывает что-то, только если на стенде записей больше лимита."""
        if len(items) > limit:
            self.fail(f"$top={limit}: вернулось {len(items)} записей")
        return self

    @step("$skip={skip}: страница сдвинута")
    def check_skip(
        self, first_page: list[dict], skipped_page: list[dict], skip: int, key_field: str = "Id"
    ) -> OdataChecker:
        """Первая запись страницы со $skip — запись номер ``skip`` первой страницы.

        Порядок должен быть однозначным: сортируйте по полю и ключу (``Title asc, Id asc``).
        """
        if len(first_page) <= skip or not skipped_page:
            return self.fail(f"$skip={skip}: мало записей для проверки: {len(first_page)} и {len(skipped_page)}")
        expected, actual = first_page[skip], skipped_page[0]
        for name, record in (("первой страницы", expected), ("страницы со $skip", actual)):
            if key_field not in record:
                return self.fail(f"$skip={skip}: у записи {name} нет поля {key_field}")
            if record[key_field] is None:
                return self.fail(f"$skip={skip}: у записи {name} пустой ключ {key_field}")
        if expected[key_field] != actual[key_field]:
            self.fail(f"$skip={skip}: первая запись {key_field}={actual[key_field]}, ожидалась {expected[key_field]}")
        return self

    @step("$count: в ответе есть @odata.count")
    def check_count(self, response: dict) -> OdataChecker:
        """В ответе целое ``@odata.count`` и записей в ``value`` не больше него."""
        count = response.get("@odata.count")
        items = response.get("value")
        if not isinstance(items, list):
            self.fail(f"$count: в ответе нет массива value: {str(response)[:300]}")
        elif isinstance(count, bool) or not isinstance(count, int):
            self.fail(f"$count: @odata.count = {count!r}, ожидалось целое число")
        elif len(items) > count:
            self.fail(f"$count: в value {len(items)} записей, больше чем @odata.count = {count}")
        return self

    # --- $expand, $orderby ---

    @step("$expand={field}: связанные данные на месте")
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

    @step("$orderby: сортировка по {field}")
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
        """Одна ошибка на все записи, где значение поля не подходит: сколько их и какие значения.

        Записи без поля — отдельная ошибка: отсутствующее поле не считается значением ``None``.
        """
        missing = sum(1 for item in items if field not in item)
        if missing:
            self.fail(f"{rule}: поля {field} нет в {missing} из {len(items)} записей")
        bad = [item[field] for item in items if field in item and not is_valid(item[field])]
        if bad:
            self.fail(f"{rule}: не подходят {len(bad)} из {len(items)} записей, значения: {bad[:5]}")
        return self


def _field_names_preview(fields: set[str]) -> str:
    """Не больше пяти имён полей, каждое до 80 символов; значения записей не показываются."""
    return repr([name if len(name) <= 80 else name[:80] + "…" for name in sorted(fields)[:5]])


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
