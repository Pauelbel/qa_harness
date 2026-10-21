"""Когда брать: Excel-отчёт — структура (колонки, имя файла), значения колонок и бизнес-правила.

checker — ExcelChecker отчёта этого файла (фикстура плагина dq; как скачать отчёт — dq_client
в tests/conftest.py). Проверки идут внутри ``with checker:``: на выходе тест падает
одним сообщением обо всех ошибках. Числовые проверки сами ловят текст вместо числа,
check_is_numeric перед ними не нужен.
Отчёт скачивается один раз на файл: FILE — куда сохранить, PAYLOAD — параметры формирования.
"""

import logging

import allure

FILE = "Отчёт_по_заказам.xlsx"
PAYLOAD = {"reportType": "Orders", "startDate": "2026-09-01", "endDate": "2026-09-30"}

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------
# Ожидаемые данные: структура отчёта, допустимые статусы и формат ФИО
# ------------------------------------------------------------------------

EXPECTED_COLUMNS = [
    "Дата", "ФИО", "Подразделение", "Заказ", "Номер заказа", "Статус",
    "Часы", "Ставка", "Стоимость", "Загрузка", "Период",
]
STATUSES = ("Черновик", "В работе", "Закрыт")
FULL_NAME = r"[А-Яа-яЁё-]+\s+[А-Яа-яЁё-]+\s+[А-Яа-яЁё-]+"


# ------------------------------------------------------------------------
# Структура и значения: каждый тест получает отдельный checker одного отчёта
# ------------------------------------------------------------------------

@allure.epic("Качество данных")
@allure.feature("Отчёт по заказам")
class TestOrdersReport:

    @allure.title("Имя файла соответствует шаблону")
    def test_filename(self, checker):
        with checker:
            checker.check_filename(r"orders_report_\d{2}\.\d{2}\.\d{4}\.xlsx$")

    @allure.title("Колонки: состав, порядок, нет пустых")
    def test_structure(self, checker):
        with checker:
            checker.check_columns(EXPECTED_COLUMNS, strict_order=True)
            checker.check_no_fully_empty_columns(EXPECTED_COLUMNS)

    @allure.title("«Дата»: заполнена, формат ДД.ММ.ГГГГ")
    def test_date(self, checker):
        with checker:
            checker.check_required(["Дата"])
            checker.check_date("Дата")

    @allure.title("«ФИО»: фамилия, имя и отчество")
    def test_full_name(self, checker):
        with checker:
            checker.check_required(["ФИО"])
            checker.check_regex("ФИО", FULL_NAME, "должно содержать фамилию, имя и отчество")

    @allure.title("«Подразделение» и «Заказ»: текст")
    def test_text_columns(self, checker):
        with checker:
            checker.check_text("Подразделение")
            checker.check_text("Заказ")

    @allure.title("«Номер заказа»: целое положительное число")
    def test_order_number(self, checker):
        with checker:
            checker.check_required(["Номер заказа"])
            checker.check_integer("Номер заказа")
            checker.check_range("Номер заказа", min_value=0, min_inclusive=False)

    @allure.title("«Статус»: значение из списка")
    def test_status(self, checker):
        with checker:
            checker.check_enum("Статус", STATUSES)

    @allure.title("«Часы», «Ставка», «Стоимость»: заполнены, числа в допустимых границах")
    def test_hours_and_rate(self, checker):
        with checker:
            checker.check_required(["Часы", "Ставка", "Стоимость"])
            checker.check_range("Часы", min_value=0, min_inclusive=False, max_value=24)
            checker.check_range("Ставка", min_value=0, min_inclusive=False)
            checker.check_decimal_places("Ставка", 2)
            checker.check_decimal_places("Стоимость", 2)

    @allure.title("«Загрузка»: процент от 0 до 100")
    def test_load(self, checker):
        with checker:
            checker.check_percentage("Загрузка", max_value=100)

    @allure.title("«Период»: две даты через дефис")
    def test_period(self, checker):
        with checker:
            checker.check_date_period("Период")


# ------------------------------------------------------------------------
# Бизнес-правила: расчёт стоимости, дубликаты строк и статистика заполненности
# ------------------------------------------------------------------------

@allure.epic("Качество данных")
@allure.feature("Отчёт по заказам: бизнес-правила")
class TestOrdersReportRules:

    @allure.title("«Стоимость» = «Часы» × «Ставка»")
    def test_cost(self, checker):
        with checker:
            checker.check_cost_calculation("Часы", "Ставка", "Стоимость")

    @allure.title("Нет повторяющихся строк")
    def test_no_duplicates(self, checker):
        with checker:
            checker.check_no_duplicate_rows(EXPECTED_COLUMNS, message="полное совпадение строк по всем ячейкам")

    @allure.title("Статистика заполненности колонок (информационный тест)")
    def test_fill_statistics(self, checker):
        statistics = checker.get_fill_statistics(EXPECTED_COLUMNS)
        logger.info("Строк в отчёте: %s\n%s", checker.get_row_count(), statistics.to_string(index=False))
