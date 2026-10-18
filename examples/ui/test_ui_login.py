"""Пример UI-теста без предварительного входа: стандартная page анонимна, тест логинится сам."""

import allure

from config import ACTIVE_CONFIG
from examples.ui.pages.login_page import LoginPage


@allure.epic("Фронтенд")
@allure.feature("Авторизация")
class TestLogin:

    @allure.title("Вход с корректными учётными данными")
    def test_successful_login(self, page):
        login_page = LoginPage(page)

        login_page.open()  # главная страница фронтенда (общий метод из BasePage)
        login_page.login_user(ACTIVE_CONFIG["app_frontend_login"], ACTIVE_CONFIG["app_frontend_password"])

        login_page.check_logged_in()
