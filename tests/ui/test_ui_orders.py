"""Когда брать: UI-тест с предусловием через API — запись создана фабрикой и должна быть видна на странице.

auth_page — страница вошедшего пользователя (плагин ui), create_order — фабрика заказов через API
(tests/conftest.py): заказ удаляется после теста, даже если тест упал.
"""

import allure

from tests.ui.pages.orders_page import OrdersPage


# ------------------------------------------------------------------------
# Заказы: запись создаёт API, страница показывает её пользователю
# ------------------------------------------------------------------------

@allure.epic("Фронтенд")
@allure.feature("Заказы")
class TestOrdersPage:

    @allure.title("Заказ, созданный через API, виден в списке со своим статусом")
    def test_created_order_in_list(self, auth_page, create_order):
        order = create_order(Status="Draft")
        orders_page = OrdersPage(auth_page)

        orders_page.open_orders()

        orders_page.check_order_status(order["Title"], "Черновик")  # подпись статуса Draft во фронтенде
