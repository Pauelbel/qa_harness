"""Клиент PostgreSQL: соединение открывается на время одного запроса.

    db = PostgresClient(host=..., port=..., dbname=..., user=..., password=...)
    rows = db.fetch_all("SELECT id, title FROM projects WHERE title = %s", [title])
    rows[0]["title"]
    db.execute("DELETE FROM projects WHERE id = %s", [project_id])

Значения передавайте вторым аргументом (``%s``), а не f-строкой: так psycopg2 сам их экранирует.
Каждый запрос — шаг Allure с вложением: текст запроса, параметры, число строк и первые строки.
"""

from __future__ import annotations

import pprint
import textwrap
from collections.abc import Sequence
from contextlib import closing
from typing import Any

import allure
import psycopg2
from psycopg2.extras import RealDictCursor

MAX_ATTACHED_ROWS = 20  # сколько строк результата приложить к шагу


# ------------------------------------------------------------------------
# PostgreSQL: соединение на один запрос, значения передаются через %s
# ------------------------------------------------------------------------

class PostgresClient:
    def __init__(self, **connection_params: Any) -> None:
        self.connection_params = connection_params

    # ------------------------------------------------------------------------
    # Чтение: SELECT возвращает список словарей, соединение закрывается после запроса
    # ------------------------------------------------------------------------

    def fetch_all(self, query: str, params: Sequence[Any] | None = None) -> list[dict]:
        """SELECT: все строки, каждая — словарь «колонка → значение»."""
        with allure.step("SQL: выборка"):
            # with connection только завершает транзакцию, закрывает соединение closing().
            with closing(psycopg2.connect(**self.connection_params)) as connection, connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    rows = [dict(row) for row in cursor.fetchall()]
            more = f"\n... и ещё {len(rows) - MAX_ATTACHED_ROWS}" if len(rows) > MAX_ATTACHED_ROWS else ""
            _attach(query, params, f"Строк: {len(rows)}\n{pprint.pformat(rows[:MAX_ATTACHED_ROWS], width=120)}{more}")
            return rows

    # ------------------------------------------------------------------------
    # Изменения: commit при успехе, rollback при исключении
    # ------------------------------------------------------------------------

    def execute(self, query: str, params: Sequence[Any] | None = None) -> None:
        """INSERT, UPDATE, DELETE: выполняет запрос и сохраняет изменения (commit)."""
        with allure.step("SQL: изменение"):
            with closing(psycopg2.connect(**self.connection_params)) as connection, connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    affected = cursor.rowcount
            _attach(query, params, f"Затронуто строк: {affected}")


# ------------------------------------------------------------------------
# Отчёт SQL: текст запроса, параметры и результат прикладываются к шагу
# ------------------------------------------------------------------------

def _attach(query: str, params: Sequence[Any] | None, result: str) -> None:
    text = f"{textwrap.dedent(query).strip()}\n\nПараметры: {list(params or [])!r}\n\n{result}"
    allure.attach(text, name="Запрос и результат", attachment_type=allure.attachment_type.TEXT)
