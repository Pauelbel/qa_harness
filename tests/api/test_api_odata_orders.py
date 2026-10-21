"""Когда брать: OData API — схема ответа, $select, $filter, $top, $skip, $count, $expand, $orderby.

app_api — клиент OData API, create_order — фабрика тестовых заказов (обе фикстуры из tests/conftest.py).
Проверки идут внутри ``with OdataChecker() as checker:``: на выходе тест падает одним сообщением обо всех ошибках.

Тест не полагается на содержимое стенда: для $filter создаёт подходящую и неподходящую запись,
для $top, $skip и $orderby создаёт свою группу заказов с общим префиксом названия и фильтрует по нему.
Пример параметризации — test_select: один тест на каждое поле из SELECT_FIELDS.
"""

from datetime import date, datetime
from uuid import UUID

import allure
import pytest
from pydantic import BaseModel

from qa.base.data import unique_title
from qa.layers.odata import OdataChecker

ENDPOINT = "/api/v1/orders"


# ------------------------------------------------------------------------
# Модели ответа: схема заказа и вложенной услуги
# ------------------------------------------------------------------------

class ServiceDto(BaseModel):
    Id: UUID
    Title: str | None = None


# ------------------------------------------------------------------------
# Заказ: обязательные поля ответа и необязательные данные $expand
# ------------------------------------------------------------------------

class OrderDto(BaseModel):
    Id: UUID
    Title: str | None = None
    ProjectId: UUID
    Status: str
    StartDate: date
    EndDate: date
    CreatedDate: datetime
    Services: list[ServiceDto] | None = None


# ------------------------------------------------------------------------
# Параметры проверок: пагинации нужен однозначный порядок по названию и ключу
# ------------------------------------------------------------------------

SELECT_FIELDS = ["Id", "Title", "ProjectId", "Status", "StartDate", "EndDate"]
TOP = 3
SKIP = 2
OWN_ORDERS = 5  # больше TOP и SKIP: иначе $top и $skip ничего не доказывают
STABLE_ORDER = "Title asc, Id asc"  # второй ключ делает порядок однозначным при одинаковых Title


@pytest.fixture
def own_orders(create_order) -> tuple[str, list[dict]]:
    """Группа заказов теста с общим префиксом названия: ``$filter=startswith(Title, префикс)`` вернёт только их."""
    prefix = unique_title()
    return prefix, [create_order(Title=f"{prefix}-{number}") for number in range(OWN_ORDERS)]


def only(prefix: str) -> str:
    return f"startswith(Title, '{prefix}')"


# ------------------------------------------------------------------------
# Структура ответа: схема, $select, $count, $expand на данных стенда
# ------------------------------------------------------------------------

@allure.epic("API")
@allure.feature(ENDPOINT)
class TestOrdersOdata:

    @allure.title("Ответ без параметров соответствует схеме")
    def test_schema(self, app_api):
        items = app_api.get_items(ENDPOINT)

        with OdataChecker() as checker:
            checker.check_not_empty(items)
            checker.check_schema(items, OrderDto)

    @allure.title("$select={field}")
    @pytest.mark.parametrize("field", SELECT_FIELDS)
    def test_select(self, app_api, field):
        items = app_api.get_items(ENDPOINT, {"$select": field})

        with OdataChecker() as checker:
            checker.check_not_empty(items)
            checker.check_select_property(items, field)
            checker.check_select_strict(items, [field])

    @allure.title("$count возвращает общее число записей")
    def test_count(self, app_api):
        response = app_api.get_response(ENDPOINT, {"$count": "true"})

        with OdataChecker() as checker:
            checker.check_count(response)

    @allure.title("$expand подтягивает услуги заказа")
    def test_expand(self, app_api):
        items = app_api.get_items(ENDPOINT, {"$expand": "Services"})

        with OdataChecker() as checker:
            checker.check_not_empty(items)
            checker.check_expand_field(items, "Services", expected_type=list)

    # ------------------------------------------------------------------------
    # $filter: подходящая запись в ответе есть, неподходящей нет
    # ------------------------------------------------------------------------

    @allure.title("$filter по статусу")
    def test_filter_by_status(self, app_api, create_order):
        draft = create_order(Status="Draft")
        closed = create_order(Status="Closed")

        items = app_api.get_items(ENDPOINT, {"$filter": "Status eq 'Draft'"})

        with OdataChecker() as checker:
            checker.check_filter_eq(items, "Status", "Draft")
            checker.check_has_record(items, "Id", draft["Id"])
            checker.check_no_record(items, "Id", closed["Id"])

    @allure.title("$filter по диапазону дат")
    def test_filter_by_dates(self, app_api, create_order):
        # Фиксированные даты — только у записей, созданных тестом.
        inside = create_order(StartDate="2026-01-15", EndDate="2026-01-20")
        outside = create_order(StartDate="2026-02-15", EndDate="2026-02-20")

        items = app_api.get_items(ENDPOINT, {"$filter": "StartDate ge 2026-01-01 and StartDate le 2026-01-31"})

        with OdataChecker() as checker:
            checker.check_filter_date_range(items, "StartDate", "2026-01-01", "2026-01-31")
            checker.check_has_record(items, "Id", inside["Id"])
            checker.check_no_record(items, "Id", outside["Id"])

    # ------------------------------------------------------------------------
    # $top, $skip, $orderby: на своей группе заказов, их число известно заранее
    # ------------------------------------------------------------------------

    @allure.title(f"$top={TOP} ограничивает число записей")
    def test_top(self, app_api, own_orders):
        prefix, orders = own_orders

        response = app_api.get_response(ENDPOINT, {"$filter": only(prefix), "$top": str(TOP), "$count": "true"})

        with OdataChecker() as checker:
            checker.check_count(response)
            # @odata.count больше лимита: иначе проверка $top ничего не доказывает.
            checker.check_equal(response.get("@odata.count"), len(orders), "Заказов теста по @odata.count")
            checker.check_equal(len(response["value"]), TOP, f"Записей в ответе с $top={TOP}")

    @allure.title(f"$skip={SKIP} сдвигает страницу")
    def test_skip(self, app_api, own_orders):
        prefix, _ = own_orders
        params = {"$filter": only(prefix), "$orderby": STABLE_ORDER}

        first_page = app_api.get_items(ENDPOINT, params)
        skipped_page = app_api.get_items(ENDPOINT, {**params, "$skip": str(SKIP)})

        with OdataChecker() as checker:
            checker.check_skip(first_page, skipped_page, skip=SKIP)
            checker.check_equal(len(skipped_page), OWN_ORDERS - SKIP, f"Записей после $skip={SKIP}")

    @allure.title("$orderby сортирует по названию")
    def test_orderby(self, app_api, own_orders):
        prefix, orders = own_orders

        items = app_api.get_items(ENDPOINT, {"$filter": only(prefix), "$orderby": "Title desc"})

        with OdataChecker() as checker:
            checker.check_equal(len(items), len(orders), "Заказов теста в ответе")
            checker.check_orderby(items, "Title", reverse=True)
