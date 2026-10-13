"""Клиенты систем и тестовые данные: тест просит их по имени фикстуры.

    def test_orders(app_api, app_db, created_project): ...

Новая система — фикстура «<система>_<клиент>» по образцу app_api: адрес и секреты
из ACTIVE_CONFIG, клиент из clients/. Один клиент на весь запуск; секреты читаются,
только когда клиент понадобился тесту.
"""

import uuid
from collections.abc import Iterator

import allure
import pytest

from clients.db import PostgresClient
from clients.http import HttpClient
from clients.odata import OdataClient
from config import ACTIVE_CONFIG


# ============================================================================
# Клиенты систем
# ============================================================================

@pytest.fixture(scope="session")
def app_api() -> Iterator[OdataClient]:
    """OData API бэкенда тестируемого приложения."""
    headers = {"Authorization": f"Bearer {ACTIVE_CONFIG['app_api_token']}", "Accept": "application/json"}
    with OdataClient(ACTIVE_CONFIG["app_api_url"], headers=headers) as client:
        yield client


@pytest.fixture(scope="session")
def app_db() -> PostgresClient:
    """База данных тестируемого приложения."""
    return PostgresClient(
        host=ACTIVE_CONFIG["app_db_host"],
        port=ACTIVE_CONFIG["app_db_port"],
        dbname=ACTIVE_CONFIG["app_db_name"],
        user=ACTIVE_CONFIG["app_db_user"],
        password=ACTIVE_CONFIG["app_db_password"],
    )


@pytest.fixture(scope="session")
def crm_api() -> Iterator[HttpClient]:
    """REST API второй системы: токен в заголовке, тестовый HTTPS-сертификат."""
    headers = {"Authorization": ACTIVE_CONFIG["crm_token"]}
    with HttpClient(ACTIVE_CONFIG["crm_url"], headers=headers, verify=False) as client:
        yield client


# ============================================================================
# Тестовые данные
#   фикстура создаёт запись до теста и удаляет после — даже если тест упал
#   (код после yield pytest выполняет всегда)
# ============================================================================

def unique_title() -> str:
    """Название тестовых данных: qa_autotest- видно в БД, хвост не пересекается с другими запусками."""
    return f"qa_autotest-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def created_project(app_db) -> Iterator[dict]:
    """Проект в БД на время теста: ``{"id": ..., "title": ...}``."""
    project = {"id": str(uuid.uuid4()), "title": unique_title()}

    with allure.step(f"Предусловие: создать в БД проект «{project['title']}»"):
        app_db.execute(
            "INSERT INTO projects (id, title, status) VALUES (%s, %s, 'draft')",
            [project["id"], project["title"]],
        )

    yield project

    with allure.step(f"Постусловие: удалить из БД проект «{project['title']}»"):
        app_db.execute("DELETE FROM projects WHERE id = %s", [project["id"]])


@pytest.fixture
def created_order(app_db, created_project) -> Iterator[dict]:
    """Заказ в проекте на время теста: ``{"id": ..., "title": ..., "project": {...}}``.

    Фикстура просит created_project: pytest создаёт сначала проект, потом заказ,
    а удаляет в обратном порядке.
    """
    order = {"id": str(uuid.uuid4()), "title": unique_title(), "project": created_project}

    with allure.step(f"Предусловие: создать в БД заказ «{order['title']}»"):
        app_db.execute(
            "INSERT INTO orders (id, title, project_id, status) VALUES (%s, %s, %s, 'draft')",
            [order["id"], order["title"], created_project["id"]],
        )

    yield order

    with allure.step(f"Постусловие: удалить из БД заказ «{order['title']}»"):
        app_db.execute("DELETE FROM orders WHERE id = %s", [order["id"]])
