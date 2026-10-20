"""Пример UI-тестов с Page Object: пользователь уже вошёл (фикстура auth_page из examples/ui/conftest.py)."""

import allure

from examples.ui.pages.projects_page import ProjectsPage


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
