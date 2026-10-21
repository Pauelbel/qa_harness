"""Когда брать: проверка данных в БД — запрос ищет нарушения, тест проверяет, что их нет;
запись создана фикстурой в БД (created_order) или через API (create_order) и проверяется запросом.

app_db — клиент базы (фикстура из tests/conftest.py): fetch_all() возвращает строки словарями.
Значения в запрос передаются вторым аргументом (%s), а не f-строкой.
"""

import allure

from qa.base.checks import Checker


# ------------------------------------------------------------------------
# DB-проверки: запрос выбирает нарушения, Checker проверяет их отсутствие
# ------------------------------------------------------------------------

@allure.epic("База данных")
@allure.feature("Проекты и заказы")
class TestOrdersConsistency:

    @allure.title("Заказы закрытых проектов в том же статусе, что и проект")
    @allure.issue("TASK-101")
    @allure.description(
        "Если проект в финальном статусе (finished, canceled), "
        "его заказы должны быть в том же статусе."
    )
    def test_orders_status_match_project(self, app_db):
        rows = app_db.fetch_all("""
            SELECT p.id AS project_id, p.status AS project_status,
                   o.id AS order_id, o.status AS order_status
            FROM projects p
            JOIN orders o ON o.project_id = p.id
            WHERE p.status IN ('finished', 'canceled')
              AND o.status != p.status
              AND NOT p.is_deleted
              AND NOT o.is_deleted
            ORDER BY p.id, o.id
        """)

        with Checker() as checker:
            checker.check_no_rows(rows, "Заказы в другом статусе, чем их закрытый проект")


    @allure.title("Внешний идентификатор услуги не повторяется")
    @allure.description("Среди неудалённых услуг каждый external_id встречается один раз.")
    def test_external_id_unique(self, app_db):
        rows = app_db.fetch_all("""
            SELECT external_id, COUNT(*) AS duplicates
            FROM services
            WHERE NOT is_deleted
            GROUP BY external_id
            HAVING COUNT(*) > 1
        """)

        with Checker() as checker:
            checker.check_no_rows(rows, "Повторяющиеся external_id")


    # ------------------------------------------------------------------------
    # Тестовые данные: созданы в БД (created_order) или через API (create_order)
    # ------------------------------------------------------------------------

    @allure.title("Заказ, созданный тестом, привязан к своему проекту")
    @allure.description("Пример с тестовыми данными: фикстура created_order создаёт проект и заказ и удаляет их после теста.")
    def test_created_order_in_project(self, app_db, created_order):
        rows = app_db.fetch_all(
            "SELECT id, status FROM orders WHERE project_id = %s",
            [created_order["project"]["id"]],
        )

        with Checker() as checker:
            checker.check_equal([row["id"] for row in rows], [created_order["id"]], "Заказы проекта")
            checker.check_equal(rows[0]["status"] if rows else None, "draft", "Статус нового заказа")

    @allure.title("Заказ, созданный через API, сохранён в БД")
    @allure.description("Предусловие через API: фабрика create_order создаёт заказ и удаляет его после теста.")
    def test_api_order_saved(self, app_db, create_order):
        order = create_order()

        rows = app_db.fetch_all("SELECT title FROM orders WHERE id = %s", [order["Id"]])

        with Checker() as checker:
            checker.check_equal(len(rows), 1, "Строк заказа в БД")
            checker.check_equal(rows[0]["title"] if rows else None, order["Title"], "Название в БД")
