"""Страница входа."""

from clients.browser import BasePage
from report import step

USERNAME = "#username"
PASSWORD = "#password"
SIGN_IN_BTN = "button[type='submit']"
USER_MENU = "[data-testid='user-menu']"  # меню пользователя есть только у вошедшего
LOGIN_URL_PART = "/login"


class LoginPage(BasePage):
    @step("Авторизация пользователя {username}")  # @step не сохраняет аргументы: пароля в отчёте нет
    def login_user(self, username: str, password: str):
        self.element("Поле «Логин»", USERNAME).fill(username)
        self.element("Поле «Пароль»", PASSWORD).fill(password)
        self.element("Кнопка «Войти»", SIGN_IN_BTN).click()

    @step("Пользователь вошёл: видно меню пользователя, адрес не страницы входа")
    def check_logged_in(self):
        # Положительный признак: исчезновение кнопки «Войти» не отличает вход от пустой страницы или ошибки.
        self.element("Меню пользователя", USER_MENU).check_visible()
        self.check_url_not_contains(LOGIN_URL_PART)
