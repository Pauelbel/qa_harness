"""Страница входа."""

import allure

from clients.browser import BasePage

USERNAME = "#username"
PASSWORD = "#password"
SIGN_IN_BTN = "button[type='submit']"


class LoginPage(BasePage):
    @allure.step("Авторизация пользователя {username}")
    def login_user(self, username: str, password: str):
        self.element("Поле «Логин»", USERNAME).fill(username)
        self.element("Поле «Пароль»", PASSWORD).fill(password)
        self.element("Кнопка «Войти»", SIGN_IN_BTN).click()

    @allure.step("Пользователь вошёл: форма входа закрылась")
    def check_logged_in(self):
        # При ошибке входа форма показывается снова, кнопка не пропадает.
        self.element("Кнопка «Войти»", SIGN_IN_BTN).check_hidden()
