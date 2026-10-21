"""Подключённые слои: одна строка — один модуль qa. В рабочем проекте этот файл выглядит так же.

Не нужен слой — закомментируйте его строку: папки этого слоя (ui/, db/, dq/) перестанут собираться.
Для каждого слоя нужен свой профиль зависимостей: таблица — в README.md, раздел «Слои».
Фикстуры систем (клиенты, тестовые данные, вход во фронтенд) — в conftest.py рядом с тестами.
"""

pytest_plugins = [
    "qa.hooks.common",  # обязательно: артефакты, лог шагов, итог Checker, маркеры по папке
    "qa.layers.api",    # HTTP и OData              requirements/base.txt
    "qa.layers.db",     # PostgreSQL                requirements/db.txt
    "qa.layers.ui",     # браузер, Page Object      requirements/ui.txt
    "qa.layers.dq",     # Excel-отчёты              requirements/dq.txt
    "qa.layers.vault",  # секреты из Vault          requirements/vault.txt
]
