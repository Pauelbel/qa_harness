"""Пример API-тестов обычного REST API: JSON-ответ и его схема.

crm_api — HttpClient второй системы (фикстура из examples/conftest.py).
Проверки идут внутри ``with Checker() as checker:``: на выходе тест падает одним сообщением обо всех ошибках.
"""

import allure
from pydantic import BaseModel

from checks.base import Checker

ENDPOINT = "/api/clients"


# ------------------------------------------------------------------------
# Модели ответа: Pydantic проверяет объект списка и каждого клиента
# ------------------------------------------------------------------------

class ClientDto(BaseModel):
    Id: int
    Name: str
    IsActive: bool


# ------------------------------------------------------------------------
# Список клиентов: число записей и вложенные объекты ClientDto
# ------------------------------------------------------------------------

class ClientListDto(BaseModel):
    Count: int
    Items: list[ClientDto]


# ------------------------------------------------------------------------
# REST-проверки: сначала схема ответа, затем содержимое списка
# ------------------------------------------------------------------------

@allure.epic("API")
@allure.feature(f"CRM: {ENDPOINT}")
class TestCrmClients:

    @allure.title("Список активных клиентов: схема и содержимое")
    def test_active_clients(self, crm_api):
        data = crm_api.get_json(ENDPOINT, {"active": "true"})

        with Checker() as checker:
            checker.check_schema(data, ClientListDto)
            checker.check_true(data.get("Count", 0) > 0, "Список клиентов не пустой")
            checker.check_true(
                all(item.get("IsActive") is True for item in data.get("Items", [])), "В списке только активные клиенты"
            )
