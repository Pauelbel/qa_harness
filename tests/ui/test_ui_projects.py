"""Когда брать: UI-тест, где пользователь уже вошёл, в том числе с предусловием в БД.

auth_page — страница вошедшего пользователя (плагин ui; вход — фикстура ui_login из tests/conftest.py).
created_project — проект в БД на время теста (tests/conftest.py, нужен и плагин db).
Проверки UI — методы check_* страницы: они ждут нужного состояния и сразу роняют тест, Checker не нужен.
"""

import allure

from tests.ui.pages.projects_page import ProjectsPage


# ------------------------------------------------------------------------
# Проекты: auth_page уже авторизована, тестовые записи создают фикстуры
# ------------------------------------------------------------------------

@allure.epic("Фронтенд")
@allure.feature("Проекты")
class TestProjectsPage:

    @allure.title("Раздел «Проекты» открывается из меню")
    def test_page_loaded(self, auth_page):
        projects_page = ProjectsPage(auth_page)

        projects_page.open()
        projects_page.open_section()  # клик по пункту меню «Проекты»

        projects_page.check_page_loaded()

    @allure.title("Проект, созданный в БД, виден в списке")
    def test_created_project_in_list(self, auth_page, created_project):
        projects_page = ProjectsPage(auth_page)

        projects_page.open()
        projects_page.open_section()

        projects_page.check_project_in_list(created_project["title"])  # проект создала фикстура
