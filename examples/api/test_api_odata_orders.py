"""Пример API-тестов OData: схема ответа и параметры запроса.

app_api — клиент OData API (фикстура из examples/conftest.py).
OdataChecker копит ошибки, assert_valid() в конце теста падает одним сообщением обо всех.
"""

from datetime import date, datetime
from uuid import UUID

import allure
import pytest
from pydantic import BaseModel

from checks.odata import OdataChecker

ENDPOINT = "/api/v1/orders"


# --- Модели ответа ---

class ServiceDto(BaseModel):
    Id: UUID
    Title: str | None = None


class OrderDto(BaseModel):
    Id: UUID
    Title: str | None = None
    ProjectId: UUID
    Status: str
    StartDate: date
    EndDate: date
    CreatedDate: datetime
    Services: list[ServiceDto] | None = None


# --- Тестовые данные ---

SELECT_FIELDS = ["Id", "Title", "ProjectId", "Status", "StartDate", "EndDate"]


# --- Тесты ---

@allure.epic("API")
@allure.feature(ENDPOINT)
class TestOrdersOdata:

    @allure.title("Ответ без параметров соответствует схеме")
    def test_schema(self, app_api):
        items = app_api.get_items(ENDPOINT)

        checker = OdataChecker()
        checker.check_not_empty(items)
        checker.check_schema(items, OrderDto)
        checker.assert_valid()

    @allure.title("$select={field}")
    @pytest.mark.parametrize("field", SELECT_FIELDS)
    def test_select(self, app_api, field):
        items = app_api.get_items(ENDPOINT, {"$select": field})

        checker = OdataChecker()
        checker.check_not_empty(items)
        checker.check_select_property(items, field)
        checker.check_select_strict(items, [field])
        checker.assert_valid()

    @allure.title("$filter по статусу")
    def test_filter_by_status(self, app_api):
        items = app_api.get_items(ENDPOINT, {"$filter": "Status eq 'Draft'"})

        checker = OdataChecker()
        checker.check_not_empty(items)
        checker.check_filter_eq(items, "Status", "Draft")
        checker.assert_valid()

    @allure.title("$filter по диапазону дат")
    def test_filter_by_dates(self, app_api):
        items = app_api.get_items(ENDPOINT, {"$filter": "StartDate ge 2026-01-01 and StartDate le 2026-01-31"})

        checker = OdataChecker()
        checker.check_filter_date_range(items, "StartDate", "2026-01-01", "2026-01-31")
        checker.assert_valid()

    @allure.title("$top ограничивает число записей")
    def test_top(self, app_api):
        items = app_api.get_items(ENDPOINT, {"$top": "5"})

        checker = OdataChecker()
        checker.check_top_limit(items, 5)
        checker.assert_valid()

    @allure.title("$skip сдвигает страницу")
    def test_skip(self, app_api):
        first_page = app_api.get_items(ENDPOINT, {"$top": "10", "$orderby": "Title asc"})
        skipped_page = app_api.get_items(ENDPOINT, {"$top": "10", "$skip": "2", "$orderby": "Title asc"})

        checker = OdataChecker()
        checker.check_skip(first_page, skipped_page, skip=2)
        checker.assert_valid()

    @allure.title("$count возвращает общее число записей")
    def test_count(self, app_api):
        response = app_api.get_json(ENDPOINT, {"$count": "true"})

        checker = OdataChecker()
        checker.check_count(response)
        checker.assert_valid()

    @allure.title("$expand подтягивает услуги заказа")
    def test_expand(self, app_api):
        items = app_api.get_items(ENDPOINT, {"$expand": "Services"})

        checker = OdataChecker()
        checker.check_not_empty(items)
        checker.check_expand_field(items, "Services", expected_type=list)
        checker.assert_valid()

    @allure.title("$orderby сортирует по названию")
    def test_orderby(self, app_api):
        items = app_api.get_items(ENDPOINT, {"$orderby": "Title desc"})

        checker = OdataChecker()
        checker.check_not_empty(items)
        checker.check_orderby(items, "Title", reverse=True)
        checker.assert_valid()
