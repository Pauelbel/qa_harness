# Правила для AI-агентов и новых участников

Короткая памятка: как писать тесты в этом репозитории. Подробности — README.md, описание проверок — докстринги в `checks/`.

## Новый тест

1. **Возьмите ближайший пример** и копируйте его оформление:
   - OData API — `examples/api/test_api_odata_orders.py`; обычный REST — `examples/api/test_api_crm_clients.py`;
   - БД — `examples/db/test_db_orders.py`;
   - Excel-отчёт — `examples/dq_reports/test_dq_orders_report.py`;
   - UI — `examples/ui/test_ui_projects.py` (вошедший пользователь), `test_ui_login.py` (без входа).
2. **Файл** `test_<слой>_<тема>.py`, имя уникально во всём репозитории. Один файл — одна тема.
3. **Allure-метки обязательны**: класс `Test<Тема>` с `@allure.epic` и `@allure.feature`, у каждого теста `@allure.title`.
4. **Проверки** — внутри `with Checker() as checker:` (`OdataChecker`, в DQ — `with checker:`), одна `check_*` на строку.
   Сначала структура (`check_not_empty`, `check_schema`, `check_columns`), потом содержимое.
   Проверки содержимого на пустых данных проходят — нужен ли перед ними `check_not_empty`, решает тест.

## Куда класть значения

| Что | Куда |
|---|---|
| Адреса, токены, логины, пароли | `.env` с префиксом окружения (`STAGE_APP_API_TOKEN`) и строка в `.env.example`; в коде — `ACTIVE_CONFIG["app_api_token"]` |
| Эндпоинт, ожидаемые колонки, статусы, SQL | константы в начале тестового файла (`ENDPOINT`, `EXPECTED_COLUMNS`) |
| Локаторы | константы в начале модуля страницы `examples/ui/pages/<страница>_page.py` |
| Клиент новой системы | фикстура `<система>_<клиент>` в `conftest.py` рядом с тестами |
| Транспорт (websocket, kafka…) | `clients/<клиент>.py`, без адресов и секретов внутри |
| Новая проверка | `check_<что>` с `@step(...)` в `checks/<тема>.py` + тест в `tests/` |

## Фикстуры

- `app_api` (OData), `crm_api` (REST), `app_db` (PostgreSQL) — `examples/conftest.py`.
- `create_order(**поля)` — заказ через API, удаляется после теста — `examples/api/conftest.py`.
- `created_project`, `created_order` — записи в БД на время теста — `examples/conftest.py`.
- `page` — браузер **без входа**; `auth_page` — пользователь уже вошёл — `examples/ui/conftest.py`.
- `checker` — ExcelChecker отчёта файла — `examples/dq_reports/conftest.py`.

## Тестовые данные

- **Тест проверяет то, что создал сам**, а не случайное содержимое стенда.
  - `$filter`: создайте подходящую и неподходящую запись; проверьте `check_has_record` и `check_no_record`.
  - `$top=N`: сначала убедитесь, что записей больше N (`@odata.count`), потом что вернулось ровно N.
  - Пагинация: однозначный порядок — `$orderby=Title asc, Id asc`, а не одно `Title`.
  - Фиксированные даты — только у записей, созданных тестом.
- Создание и удаление — в фикстуре с `yield`: код после `yield` выполняется, даже если тест упал.
- Названия тестовых данных — `unique_title()`: `qa_autotest-<хвост>`.
- Не меняйте и не удаляйте данные, которые создал не тест.

## Секреты и отчёт

- Шаг-метод (проверка, действие страницы, хелпер) — декоратор `@step("Заголовок {аргумент}")` из `report.py`.
  **`@allure.step` не используем**: он сохраняет все аргументы (пароли, ответы, таблицы) в файлы allure-results.
  Для блока внутри метода или фикстуры — `with allure.step("..."):`, он аргументов не сохраняет.
- В заголовки шагов и сообщения ошибок не передавайте целые ответы, таблицы и секреты.
- HTTP-клиент сам маскирует `password`, `token`, `secret` в отчёте и логе; заголовки туда не попадают.

## Перед тем как закончить

- Изменили `checks/`, `clients/`, корневой `conftest.py` — прогоните `python -m pytest` (тесты harness, стенд не нужен)
  и добавьте тест в `tests/`: корректные данные проходят, нарушение находится.
- Новый тест примера должен хотя бы собираться: `python -m pytest examples --collect-only -q`.
- Новая зависимость — в профиль `requirements/<слой>.txt` и версия в `requirements/constraints.txt`.
