# qa-harness

Набор готовых компонентов и примеров для API, PostgreSQL, UI и Excel-тестов на pytest.

## Установка

Нужен Python 3.12+.

Клонируйте репозиторий и перейдите в его папку:

```bash
git clone https://github.com/Pauelbel/qa_harness.git
cd qa_harness
```

Остальные команды выполняйте из этой папки: рядом лежит `pytest.ini`, и отсюда читается `.env`.

```bash
python -m venv .venv
source .venv/bin/activate                    # Windows: .venv\Scripts\activate
python -m pip install -r requirements/requirements.txt
python -m playwright install chromium       # только для UI
cp .env.example .env
```

Заполните `.env`. Секреты не добавляйте в Git.

## Настройка

Настройки разложены по назначению:

| Где | Что менять |
|---|---|
| `.env` | адреса, токены, логины, пароли, окружение |
| `conftest.py` | включённые слои `qa.layers.*` |
| `tests/conftest.py` | клиенты систем, авторизация, создание и удаление тестовых данных |
| `tests/<слой>/test_*.py` | URL методов, SQL, ожидаемые поля и бизнес-правила |
| `tests/ui/pages/` | локаторы и действия страниц |

Минимальный `.env`:

```dotenv
TEST_ENV=stage
SECRETS_SOURCE=env

STAGE_APP_API_URL=https://app-stage.example.com
STAGE_APP_API_TOKEN=
STAGE_APP_DB_HOST=
STAGE_APP_DB_PORT=5432
STAGE_APP_DB_NAME=
STAGE_APP_DB_USER=
STAGE_APP_DB_PASSWORD=
STAGE_APP_FRONTEND_URL=https://app-stage.example.com
STAGE_APP_FRONTEND_LOGIN=
STAGE_APP_FRONTEND_PASSWORD=
```

Полный список параметров находится в `.env.example`.

## Как всё связано

```mermaid
flowchart TD
    ENV[".env<br/>адреса и секреты"] --> FIX["tests/conftest.py<br/>клиенты и тестовые данные"]
    ROOT["conftest.py<br/>подключение слоёв"] --> LAYERS["qa/layers/<br/>API · DB · UI · DQ · Vault"]
    BASE["qa/base/<br/>config · checks · report · data"] --> LAYERS
    HOOKS["qa/hooks/<br/>pytest и Allure"] --> RUN["pytest"]
    LAYERS --> FIX
    FIX --> TESTS["tests/<br/>примеры и рабочие тесты"]
    BASE --> TESTS
    TESTS --> RUN
    RUN --> OUT["artifacts/<br/>лог и allure-results"]
```

Структура файлов:

```text
qa/
├── base/                 общие настройки, проверки, отчёт, данные
├── hooks/                pytest-хуки
└── layers/               API, OData, DB, UI, DQ, Vault

tests/
├── conftest.py           фикстуры систем и тестовых данных
├── api/                  REST и OData
├── db/                   PostgreSQL
├── ui/                   Playwright и pages/
└── dq/                   Excel-отчёты

requirements/             профили зависимостей
```

## Запуск

```bash
python -m pytest --collect-only -q             # проверить сборку
python -m pytest                               # все тесты
python -m pytest tests/api                     # один слой
python -m pytest tests/api/test_api_order_create.py
python -m pytest -m "api or db"                # несколько слоёв
TEST_ENV=dev python -m pytest tests/db          # другое окружение
python -m pytest tests/ui --headed              # UI с окном
```

Результаты сохраняются в `artifacts/<дата>_<окружение>/`.

## Отчёт Allure

Каждый запуск создаёт свою папку:

```text
artifacts/20261105-154119_stage/
├── pytest.log            лог запуска
└── allure-results/       сырые результаты для отчёта
```

`allure-results` — это JSON-файлы, а не готовый отчёт. Отчёт из них строит Allure CLI.
Для него нужна Java 8+; установка — `brew install allure`, `scoop install allure`
или архив со [страницы релизов](https://github.com/allure-framework/allure2/releases).
Проверка: `allure --version`.

Свою папку результатов можно задать при запуске:

```bash
python -m pytest --alluredir=allure-results
```

Ниже `RESULTS` — путь к папке `allure-results` нужного запуска:

```bash
RESULTS=artifacts/20261105-154119_stage/allure-results
```

Открыть отчёт сразу в браузере (временный, без сохранения):

```bash
allure serve $RESULTS
```

Сохранить отчёт в папку и открыть его:

```bash
allure generate $RESULTS -o allure-report --clean    # --clean перезаписывает старый отчёт
allure open allure-report
```

Папку `allure-report` нельзя открыть двойным щелчком по `index.html`: браузер не загрузит
данные с диска. Открывайте её через `allure open` или веб-сервер.

Отчёт одним HTML-файлом (удобно отправить или приложить к задаче):

```bash
allure generate $RESULTS -o allure-report --clean --single-file
```

Получится `allure-report/index.html`, который открывается в браузере без сервера.
Ключ `--single-file` есть в Allure 2.24 и новее.

## Примеры

| Задача | Файл |
|---|---|
| REST API | `tests/api/test_api_crm_clients.py` |
| OData | `tests/api/test_api_odata_orders.py` |
| Создание и удаление через API | `tests/api/test_api_order_create.py` |
| PostgreSQL | `tests/db/test_db_orders.py` |
| UI | `tests/ui/test_ui_login.py`, `tests/ui/test_ui_projects.py` |
| Excel | `tests/dq/test_dq_orders_report.py` |

Новый тест кладите в папку его слоя. Тест должен создавать свои данные и удалять их через
фикстуру с `yield`. Проверки пишите внутри `with Checker() as checker:`.
