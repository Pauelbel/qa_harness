"""Фикстуры систем-примеров: клиенты, тестовые данные, вход во фронтенд, скачивание отчёта.

Тест просит фикстуру по имени, слои связываются сами:
    def test_orders(self, app_api, app_db, created_project): ...
    def test_order_in_list(self, auth_page, create_order): ...       # UI-тест, заказ создан через API

В рабочем проекте такой же файл лежит в tests/conftest.py: скопируйте этот и поменяйте под свои системы.

    клиенты систем     app_api (OData), crm_api (REST), app_db (PostgreSQL)
    тестовые данные    create_order (через API), created_project, created_order (через БД)
    для слоёв qa       ui_base_url, ui_login (qa.layers.ui), dq_client (qa.layers.dq)

Новая система — фикстура «<система>_<клиент>» по образцу app_api: адрес и секреты
из ACTIVE_CONFIG, клиент из qa/. Один клиент на весь запуск; секреты читаются,
только когда клиент понадобился тесту. Клиенты необязательных слоёв (БД, браузер)
импортируются внутри фикстур: файл загружается и без их зависимостей.
"""

import uuid
from collections.abc import Callable, Iterator

import allure
import pytest

from qa.base.config import ACTIVE_CONFIG
from qa.base.data import unique_title
from qa.layers.api import HttpClient, response_json
from qa.layers.odata import OdataClient

ORDERS_URL = "/api/v1/orders"
REPORT_URL = "/api/v1/reports/generate"
REPORT_TIMEOUT = 300  # секунд: формирование отчёта на бэкенде бывает долгим
MAX_CLEANUP_ERRORS = 20


# ------------------------------------------------------------------------
# Клиенты систем: одна сессия на запуск, адреса и секреты — из ACTIVE_CONFIG
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app_api() -> Iterator[OdataClient]:
    """OData API бэкенда тестируемого приложения."""
    headers = {"Authorization": f"Bearer {ACTIVE_CONFIG['app_api_token']}", "Accept": "application/json"}
    with OdataClient(ACTIVE_CONFIG["app_api_url"], headers=headers) as client:
        yield client


@pytest.fixture(scope="session")
def app_db():
    """База данных тестируемого приложения (плагин db, профиль requirements/db.txt)."""
    from qa.layers.db import PostgresClient

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


# ------------------------------------------------------------------------
# Фронтенд (плагин ui): адрес и вход — плагин сам решает, когда их вызвать
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ui_base_url() -> str:
    """Адрес фронтенда: от него считаются пути page.goto("/orders") и BasePage.open()."""
    return ACTIVE_CONFIG["app_frontend_url"]


@pytest.fixture(scope="session")
def ui_login() -> Callable:
    """Как войти: плагин ui вызывает login(page) один раз на запуск, auth_page получает cookies."""
    from tests.ui.pages.login_page import LoginPage

    def login(page) -> None:
        login_page = LoginPage(page)
        login_page.open()
        login_page.login_user(ACTIVE_CONFIG["app_frontend_login"], ACTIVE_CONFIG["app_frontend_password"])
        login_page.check_logged_in()

    return login


# ------------------------------------------------------------------------
# DQ-отчёты (плагин dq): как сформировать и скачать отчёт
# ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def dq_client(app_api) -> Callable:
    """Как скачать отчёт: плагин dq вызывает download(path, PAYLOAD) один раз на файл тестов."""

    def download(path, payload) -> str | None:
        return app_api.download(
            REPORT_URL, path, method="POST", json=payload, headers={"Accept": "*/*"}, timeout=REPORT_TIMEOUT
        )

    return download


# ------------------------------------------------------------------------
# Тестовые данные в БД: фикстуры создают записи до yield и удаляют после теста
# Зависимые записи удаляются в обратном порядке, в том числе при падении теста
# ------------------------------------------------------------------------

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


# ------------------------------------------------------------------------
# Тестовые данные через API: фабрика создаёт записи, код после yield удаляет их
# Тест проверяет то, что создал сам: для $filter — подходящую и неподходящую запись
# ------------------------------------------------------------------------

@pytest.fixture
def create_order(app_api) -> Iterator[Callable[..., dict]]:
    """Фабрика заказов: ``create_order(Status="Draft")`` → созданная запись из ответа API.

    Обязательные поля вашей системы добавьте в ``payload``. Все созданные заказы
    удаляются после теста, даже если он упал.
    Удаление подтверждают статусы 200/204; 404 тоже допустим — записи уже нет.
    Остальные статусы (включая 202) и ошибки запроса отмечаются после попытки
    удалить все созданные заказы.
    """
    created: list[dict] = []

    def create(**fields) -> dict:
        payload = {"Title": unique_title(), **fields}
        with allure.step(f"Предусловие: создать заказ «{payload['Title']}» через API"):
            response = app_api.post(ORDERS_URL, json=payload)
            if response.status_code != 201:
                raise AssertionError(
                    f"Заказ не создан: ожидался статус 201, получен {response.status_code}. См. HTTP-шаг."
                )
            order = response_json(response)
        created.append(order.copy())
        return order

    yield create

    # ------------------------------------------------------------------------
    # Очистка: пробуем удалить все заказы, затем сообщаем о неподтверждённом удалении
    # ------------------------------------------------------------------------

    errors: list[str] = []
    for number, order in reversed(list(enumerate(created, start=1))):
        failure = None
        try:
            with allure.step(f"Постусловие: удалить тестовый заказ #{number}"):
                try:
                    response = app_api.delete(f"{ORDERS_URL}({order['Id']})")
                except Exception as error:
                    # Не передаём текст исключения в Allure: в нём может быть URL с токеном.
                    failure = f"Заказ #{number}: ошибка DELETE ({type(error).__name__}). См. HTTP-шаг."
                else:
                    if response.status_code not in (200, 204, 404):
                        failure = (
                            f"Заказ #{number}: DELETE вернул статус {response.status_code}, "
                            "ожидался 200, 204 или 404. См. HTTP-шаг."
                        )
                if failure:
                    # Вне except: в traceback шага нет исходного исключения с секретами.
                    raise AssertionError(failure)
        except AssertionError:
            if failure is None:
                raise
        if failure:
            errors.append(failure)

    if errors:
        details = "\n".join(errors[:MAX_CLEANUP_ERRORS])
        if len(errors) > MAX_CLEANUP_ERRORS:
            details += f"\n... и ещё {len(errors) - MAX_CLEANUP_ERRORS}; подробности — в шагах удаления."
        raise AssertionError(
            f"Не удалось подтвердить удаление {len(errors)} из {len(created)} заказов:\n{details}"
        )
