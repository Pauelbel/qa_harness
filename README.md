# qa-harness

Набор скриптов для автотестов на pytest: клиенты систем, проверки и примеры тестов каждого слоя.
Ядро ничего не знает о конкретной системе: адреса, токены, SQL и локаторы живут в тестах и их `conftest.py`.

## Быстрый старт

Нужны Python 3.11+ и Git.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env             # заполните адреса и секреты
python -m pytest examples/api
```

## Что где лежит

```text
config.py               окружение (TEST_ENV) и секреты: ACTIVE_CONFIG["app_api_token"] из env или Vault
conftest.py             общее для всех тестов: логи, маркеры по папке
pytest.ini              маркеры, форматы логов
clients/                транспорт, по файлу на клиент
  http.py               HttpClient: base_url, заголовки, лог запросов, get_json(), download()
  odata.py              OdataClient: HttpClient + get_items() — записи из value
  db.py                 PostgresClient: fetch_all() — строки словарями, execute()
  browser.py            BasePage и BaseElement для Page Object: каждое действие — шаг Allure
checks/                 проверки, по файлу на тему
  base.py               Checker: копит ошибки, assert_valid() в конце; check_true, check_equal,
                        check_not_empty, check_schema (pydantic), check_no_rows (SQL-нарушения)
  odata.py              OdataChecker: $select, $filter, $top, $skip, $count, $expand, $orderby
  excel.py              ExcelChecker: колонки, даты, числа, проценты, списки, дубликаты, расчёт стоимости
examples/               примеры: копируйте и меняйте под свою систему
  conftest.py           клиенты систем (app_api, app_db, crm_api) и тестовые данные (created_project)
  api/                  OData API и обычный REST API
  db/                   запрос ищет нарушения, тест проверяет, что их нет; тест с тестовыми данными
  dq_reports/           Excel-отчёт: скачать один раз на файл, проверить колонки и бизнес-правила
  ui/                   Page Object, вход один раз на запуск, тест без входа, тест с данными из БД
```

## Как устроен тест

1. **Клиент — фикстура по имени.** Тест не создаёт клиентов и не читает секреты, он просит фикстуру:
   `def test_orders(self, app_api, app_db):`. Фикстуры систем — в `examples/conftest.py`.
2. **Проверки копятся.** В начале проверок — `checker = Checker()` (или `OdataChecker()`), дальше
   `checker.check_...()` по одной на строку, в конце `checker.assert_valid()`: тест падает один раз
   и показывает все ошибки сразу. В DQ-тестах `checker` — фикстура: отчёт общий на файл.
3. **Один файл — одна тема** (эндпоинт, таблицы, отчёт, страница). Внутри класс `Test<Тема>` с метками
   `@allure.epic` и `@allure.feature`, у каждого теста `@allure.title`. Имя файла — `test_<слой>_<тема>.py`:
   имена файлов не должны повторяться в разных папках.
4. **Подготовка — в фикстуре.** Создать данные до теста и удалить после — фикстура с `yield`
   (`created_project` в `examples/conftest.py`). Тестовые данные называются `qa_autotest-...`.

```python
@allure.epic("API")
@allure.feature("/api/v1/orders")
class TestOrders:

    @allure.title("$top ограничивает число записей")
    def test_top(self, app_api):
        items = app_api.get_items("/api/v1/orders", {"$top": "5"})

        checker = OdataChecker()
        checker.check_not_empty(items)
        checker.check_top_limit(items, 5)
        checker.assert_valid()
```

## Как расширять

- **Новая система** — фикстура `<система>_<клиент>` в `conftest.py` рядом с тестами по образцу `app_api`,
  секреты — в `.env` с префиксом окружения (`STAGE_<СИСТЕМА>_URL`) и в `.env.example`.
- **Новый клиент** (websocket, kafka, s3…) — файл в `clients/`: класс с понятными методами, без адресов
  и секретов внутри — их передаёт фикстура.
- **Новая проверка** — метод `check_<что>` в классе своей темы: при ошибке `self.fail("текст")`,
  в конце `return self`, сверху `@allure.step("...")`.
- **Новая тема проверок** — файл `checks/<тема>.py` с классом `<Тема>Checker(Checker)`.

## Запуск

```bash
python -m pytest examples                          # всё
python -m pytest -m "api or db"                    # по маркерам: api, db, ui, dq (ставятся по папке)
TEST_ENV=dev python -m pytest examples/db          # другое окружение
python -m pytest examples/ui --headed              # UI с окном браузера; в CI — HEADLESS=true
python -m pytest --alluredir allure-results        # отчёт Allure: allure serve allure-results
```

Логи: в консоли — INFO, в файле `logs/pytest_<окружение>.log` — DEBUG, вместе с телами ответов
и строками `STEP: ...` шагов Allure.

DQ-отчёты сохраняются в `examples/dq_reports/reports` (в git не попадают).
`KEEP_DQ_REPORTS=false` — удалять после тестов, `DQ_REPORTS_OUTPUT_DIR` — другая папка.
