"""Страница «Проекты»."""

import allure

from clients.browser import BasePage

PAGE_TITLE = "//h1[contains(text(), 'Проекты')]"
PROJECT_ROW = "//tr[contains(., '{title}')]"  # строка таблицы проектов с этим названием


class ProjectsPage(BasePage):
    @allure.step("Перейти в раздел «Проекты»")
    def open_section(self):
        # Локатор по роли и тексту — устойчивее к вёрстке, чем XPath.
        self.element("Пункт меню «Проекты»", self.page.get_by_role("link", name="Проекты")).click()

    @allure.step("Страница «Проекты» загрузилась")
    def check_page_loaded(self):
        self.element("Заголовок «Проекты»", PAGE_TITLE).check_visible()

    @allure.step("Проект {title} есть в списке")
    def check_project_in_list(self, title: str):
        self.element(f"Строка проекта «{title}»", PROJECT_ROW.format(title=title)).check_visible()
