"""Когда брать: POST и DELETE — создать запись через фабрику, прочитать её по ключу, удалить.

app_api — клиент API, create_order — фабрика заказов (обе фикстуры из tests/conftest.py):
``create_order(Status="Draft")`` создаёт заказ через POST, а после теста удаляет все созданные,
даже если тест упал. Удалённый тестом заказ фабрика удалить не сможет — 404 для неё допустим.
"""

from uuid import UUID

import allure
from pydantic import BaseModel

from qa.base.checks import Checker

ENDPOINT = "/api/v1/orders"


# ------------------------------------------------------------------------
# Модель ответа: поля, которые тест задаёт при создании
# ------------------------------------------------------------------------

class CreatedOrderDto(BaseModel):
    Id: UUID
    Title: str
    Status: str


def order_url(order: dict) -> str:
    return f"{ENDPOINT}({order['Id']})"


# ------------------------------------------------------------------------
# Создание и удаление: фабрика создаёт заказ, тест проверяет его через GET
# ------------------------------------------------------------------------

@allure.epic("API")
@allure.feature(f"{ENDPOINT}: создание и удаление")
class TestOrderCreate:

    @allure.title("Созданный заказ читается по ключу с переданными полями")
    def test_created_order_readable(self, app_api, create_order):
        order = create_order(Status="Draft")

        data = app_api.get_json(order_url(order))

        with Checker() as checker:
            checker.check_schema(data, CreatedOrderDto)
            checker.check_equal(data.get("Title"), order["Title"], "Название заказа")
            checker.check_equal(data.get("Status"), "Draft", "Статус заказа")

    @allure.title("Удалённый заказ больше не читается")
    def test_deleted_order_not_found(self, app_api, create_order):
        order = create_order()

        deleted = app_api.delete(order_url(order))
        after = app_api.get(order_url(order))

        with Checker() as checker:
            checker.check_true(deleted.status_code in (200, 204), f"DELETE: статус 200 или 204, получен {deleted.status_code}")
            checker.check_equal(after.status_code, 404, "GET удалённого заказа: статус")
