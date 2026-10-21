"""Новый тест из заготовки: ``python -m core.new <слой> <тема>`` в корне рабочего проекта.

    python -m core.new api clients       → tests/api/test_api_clients.py
    python -m core.new odata orders      → tests/api/test_api_orders.py
    python -m core.new ui orders         → tests/ui/test_ui_orders.py и tests/ui/pages/orders_page.py
    python -m core.new db orders         → tests/db/test_db_orders.py
    python -m core.new dq sales_report   → tests/dq/test_dq_sales_report.py

В рабочем проекте harness лежит в harness/: ``PYTHONPATH=harness python -m core.new api clients``.
Заготовки — в templates/; места, которые нужно заменить, помечены TODO.
Имя файла теста должно быть уникальным во всём проекте: если такое уже есть, файл не создаётся.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
LAYERS = {  # слой → (заготовка теста, папка в tests/)
    "api": ("api.py", "api"),
    "odata": ("odata.py", "api"),
    "db": ("db.py", "db"),
    "ui": ("ui.py", "ui"),
    "dq": ("dq.py", "dq"),
}
# Не ищем повторы в служебных папках и в harness/ рабочего проекта: его examples/ не собираются с tests/.
SKIPPED_DIRS = {"artifacts", "harness", "node_modules", "venv", "__pycache__"}  # и все скрытые: .venv, .git


def create(layer: str, topic: str, root: Path | None = None) -> list[Path]:
    """Создать файлы теста ``layer``/``topic`` в ``root`` (по умолчанию — текущий каталог)."""
    if layer not in LAYERS:
        raise ValueError(f"Слой должен быть одним из: {', '.join(LAYERS)}. Получено: {layer}")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", topic):
        raise ValueError(f"Тема — латиница в нижнем регистре, цифры и _: orders, sales_report. Получено: {topic}")

    root = (root or Path.cwd()).resolve()
    template, folder = LAYERS[layer]
    test_file = root / "tests" / folder / f"test_{folder}_{topic}.py"
    files = {test_file: template}
    if layer == "ui":
        files[root / "tests" / "ui" / "pages" / f"{topic}_page.py"] = "ui_page.py"

    existing = next((path for path in files if path.exists()), None) or _find(root, test_file.name)
    if existing:
        raise FileExistsError(f"Файл {existing.name} уже есть: {existing}. Выберите другую тему")

    camel = "".join(part.capitalize() for part in topic.split("_"))
    for path, template in files.items():
        text = (TEMPLATES_DIR / template).read_text(encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace("__Topic__", camel).replace("__topic__", topic), encoding="utf-8")
    return list(files)


def _find(root: Path, name: str) -> Path | None:
    """Тест с таким именем где-нибудь в проекте, кроме скрытых и служебных папок."""
    for path in root.rglob(name):
        parts = path.relative_to(root).parts[:-1]
        if not any(part.startswith(".") or part in SKIPPED_DIRS for part in parts):
            return path
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        created = create(*argv)
    except (ValueError, FileExistsError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    for path in created:
        print(f"Создан {path.relative_to(Path.cwd().resolve())}: замените места с пометкой TODO")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
