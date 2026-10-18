# qa-harness

Набор скриптов для автотестов на pytest: клиенты систем, проверки и примеры тестов каждого слоя.
Ядро ничего не знает о конкретной системе: адреса, токены, SQL и локаторы живут в тестах и их `conftest.py`.

Правила для AI-агентов и новых участников — [AGENTS.md](AGENTS.md).

## Быстрый старт

Нужны Python 3.12+ и Git. Ставьте только нужные слои: базовый профиль — это API-тесты.

```bash
python -m venv .venv
source .venv/bin/activate                    # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements/base.txt         # + профили нужных слоёв, таблица ниже
cp .env.example .env                         # заполните адреса и секреты
python -m pytest                             # тесты самого harness: стенд не нужен
python -m pytest examples/api                # примеры API на вашем стенде
```

## Слои: что установить и что можно удалить

Профили лежат в `requirements/`, каждый включает базовый. Версии зафиксированы в
`requirements/constraints.txt`: на них проходят тесты harness, повторная установка даёт то же окружение.
Для всех профилей используйте Python 3.12+: закреплённые NumPy 2.5.4 и pyee 14.0.0 требуют
как минимум эту версию. Так слои можно добавлять в существующее окружение без смены Python.
Слои без установленных зависимостей при запуске `examples` не собираются — это видно в шапке вывода pytest.

| Нужен слой | Что установить | Если слой не нужен, можно удалить |
|---|---|---|
| API (всегда) | `pip install -r requirements/base.txt` | — |
| БД (PostgreSQL) | `pip install -r requirements/db.txt` | `clients/db.py`, `examples/db/`, фикстуры `app_db`, `created_project`, `created_order` в `examples/conftest.py` |
| UI (браузер) | `pip install -r requirements/ui.txt`, затем `python -m playwright install chromium` | `clients/browser.py`, `examples/ui/` |
| DQ (Excel-отчёты) | `pip install -r requirements/dq.txt` | `checks/excel.py`, `examples/dq_reports/`, `tests/test_excel.py` |
| Vault (секреты) | `pip install -r requirements/vault.txt`, `SECRETS_SOURCE=vault` | `_read_vault` в `config.py`, блок Vault в `.env.example` |
| Всё сразу, разработка harness | `pip install -r requirements/dev.txt` (или `requirements.txt`) | — |

Профили складываются: `pip install -r requirements/db.txt -r requirements/ui.txt`.
UI-пример «проект из БД виден в списке» использует фикстуру `created_project` — ему нужен и профиль БД.

**UI на Linux.** Браузеру нужны системные библиотеки. На чистой машине или в CI ставьте браузер вместе с ними:
`python -m playwright install --with-deps chromium` (нужны права root/sudo; поддерживаются Debian и Ubuntu).
В Docker проще взять готовый образ `mcr.microsoft.com/playwright/python` той же версии, что в constraints.

## Что где лежит

```text
AGENTS.md               правила написания тестов: примеры, значения, фикстуры, тестовые данные
config.py               окружение (TEST_ENV), секреты (ACTIVE_CONFIG), папка артефактов запуска (RUN_DIR)
conftest.py             общее для всех тестов: артефакты, логи, маркеры по папке, обязательный итог проверок
pytest.ini              маркеры, форматы логов; без пути pytest запускает tests/
report.py               @step — шаг Allure для проверок и страниц: не сохраняет аргументы, красит проваленную проверку
requirements/           профили зависимостей по слоям и constraints.txt с проверенными версиями
clients/                транспорт, по файлу на клиент; каждый запрос — шаг Allure с вложением
  http.py               HttpClient: base_url, заголовки, лог и шаг запроса без секретов, get_json(), download()
  odata.py              OdataClient: get_response() проверяет структуру ответа, get_items() — записи из value
  db.py                 PostgresClient: fetch_all() — строки словарями, execute()
  browser.py            BasePage и BaseElement для Page Object: каждое действие — шаг Allure
checks/                 проверки, по файлу на тему
  base.py               Checker: копит ошибки, красный шаг на каждую ошибку, итог в with/assert_valid()
  odata.py              OdataChecker: $select, $filter, $top, $skip, $count, $expand, $orderby, записи теста
  excel.py              ExcelChecker: колонки, даты, числа, проценты, списки, дубликаты, расчёт стоимости
examples/               примеры: копируйте и меняйте под свою систему
  conftest.py           клиенты систем (app_api, app_db, crm_api) и тестовые данные в БД
  api/                  OData API и обычный REST API; create_order — тестовые заказы через API
  db/                   запрос ищет нарушения, тест проверяет, что их нет; тест с тестовыми данными
  dq_reports/           Excel-отчёт: скачать один раз на файл, проверить колонки и бизнес-правила
  ui/                   Page Object; page — без входа, auth_page — вход один раз на запуск
tests/                  тесты самого harness: корректные данные проходят, нарушения находятся
```

## Как устроен тест

1. **Клиент — фикстура по имени.** Тест не создаёт клиентов и не читает секреты, он просит фикстуру:
   `def test_orders(self, app_api, app_db):`. Фикстуры систем — в `examples/conftest.py`.
2. **Проверки копятся.** Проверки идут внутри `with OdataChecker() as checker:`, по одной на строку.
   Проваленная проверка — красный шаг в Allure, следующие выполняются; на выходе из `with` тест падает
   одним сообщением обо всех ошибках. Если `with` (или `checker.assert_valid()`) забыли, тест всё равно
   упадёт — это проверяет корневой `conftest.py`. В DQ-тестах `checker` — фикстура: `with checker:`.
3. **Один файл — одна тема** (эндпоинт, таблицы, отчёт, страница). Внутри класс `Test<Тема>` с метками
   `@allure.epic` и `@allure.feature`, у каждого теста `@allure.title`. Имя файла — `test_<слой>_<тема>.py`:
   имена файлов не должны повторяться в разных папках.
4. **Данные создаёт тест.** Создать до теста и удалить после — фикстура с `yield` (`create_order`
   в `examples/api/conftest.py`, `created_project` в `examples/conftest.py`). Тестовые данные называются
   `qa_autotest-...`. Правила — в [AGENTS.md](AGENTS.md#тестовые-данные).

```python
@allure.epic("API")
@allure.feature("/api/v1/orders")
class TestOrders:

    @allure.title("$filter по статусу")
    def test_filter_by_status(self, app_api, create_order):
        draft = create_order(Status="Draft")
        closed = create_order(Status="Closed")

        items = app_api.get_items("/api/v1/orders", {"$filter": "Status eq 'Draft'"})

        with OdataChecker() as checker:
            checker.check_filter_eq(items, "Status", "Draft")
            checker.check_has_record(items, "Id", draft["Id"])
            checker.check_no_record(items, "Id", closed["Id"])
```

## Шаги отчёта

Методы-шаги (проверки, действия страниц) помечаются декоратором `@step("Заголовок {аргумент}")` из `report.py`,
а не `@allure.step`: `@allure.step` сохраняет все аргументы метода в файлы отчёта — пароль, целый ответ,
таблицу Excel. `@step` пишет только заголовок, а для проверок Checker'а ещё и отмечает шаг красным,
хотя ошибка копится, а не роняет тест сразу. Для блока внутри метода или фикстуры —
`with allure.step("..."):`, он аргументов не сохраняет.

## Как расширять

- **Новая система** — фикстура `<система>_<клиент>` в `conftest.py` рядом с тестами по образцу `app_api`,
  секреты — в `.env` с префиксом окружения (`STAGE_<СИСТЕМА>_URL`) и в `.env.example`.
- **Новый клиент** (websocket, kafka, s3…) — файл в `clients/`: класс с понятными методами, без адресов
  и секретов внутри — их передаёт фикстура. Клиент необязательного слоя импортируйте внутри фикстуры
  и добавьте папку слоя в `LAYER_REQUIREMENTS` в `examples/conftest.py`.
- **Новая проверка** — метод `check_<что>` в классе своей темы с декоратором `@step("Заголовок {аргумент}")`:
  при ошибке `self.fail("текст")`, в конце `return self`. Добавьте тест в `tests/`: корректные данные проходят, нарушение находится.
- **Новая тема проверок** — файл `checks/<тема>.py` с классом `<Тема>Checker(Checker)`.
- **Новая зависимость** — в профиль `requirements/<слой>.txt` и точная версия в `requirements/constraints.txt`.

## Запуск

```bash
python -m pytest                                   # тесты harness (стенд не нужен)
python -m pytest examples                          # все примеры
python -m pytest examples -m "api or db"           # по маркерам: api, db, ui, dq (ставятся по папке)
TEST_ENV=dev python -m pytest examples/db          # другое окружение
python -m pytest examples/ui --headed              # UI с окном браузера; в CI — HEADLESS=true
python -m pytest examples/ui --tracing retain-on-failure   # trace упавших UI-тестов
APP_VERSION=1.4.2 python -m pytest examples        # версия тестируемого приложения — в отчёт Allure
```

## Артефакты и отчёт

Всё, что создаёт запуск, складывается в отдельную папку `artifacts/<дата-время>_<окружение>/`
(в git не попадает; путь печатается в шапке вывода pytest):

```text
pytest.log          лог DEBUG: запросы, тела ответов без секретов, строки STEP: ... шагов Allure
allure-results/     результаты Allure: allure serve artifacts/<запуск>/allure-results
playwright/         скриншоты и trace упавших UI-тестов (--screenshot, --tracing)
dq_reports/         скачанные DQ-отчёты (KEEP_DQ_REPORTS=false — не хранить, DQ_REPORTS_OUTPUT_DIR — другая папка)
```

Очистка — `rm -rf artifacts`. Корень меняет `ARTIFACTS_DIR`, отдельные пути — ключи `--alluredir`,
`--log-file`, `--output`.

Что видно в отчёте Allure:

- **API** — шаг на каждый запрос: метод, адрес, статус, длительность, тело запроса и ответ (секреты — `***`);
- **БД** — шаг на каждый запрос: текст, параметры, число строк и первые 20 строк;
- **UI** — шаг на каждое действие; при падении — скриншот и адрес каждой страницы теста;
- **DQ** — шаг на правило: сколько строк из скольких нарушают, номера строк и примеры значений;
- **запуск** (вкладка Environment) — окружение, `APP_VERSION`, коммит harness, версия Python.

HTTP-вложения содержат очищенные JSON и URL-encoded формы. Тела остальных форматов
заменяются пояснением, чтобы не сохранять секреты из произвольного текста или файлов.
При ошибке запроса выводятся тип исключения и адрес с замаскированными секретами.
