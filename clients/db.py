"""Клиент PostgreSQL: соединение открывается на время одного запроса.

    db = PostgresClient(host=..., port=..., dbname=..., user=..., password=...)
    rows = db.fetch_all("SELECT id, title FROM projects WHERE title = %s", [title])
    rows[0]["title"]
    db.execute("DELETE FROM projects WHERE id = %s", [project_id])

Значения передавайте вторым аргументом (``%s``), а не f-строкой: так psycopg2 сам их экранирует.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import closing
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


class PostgresClient:
    def __init__(self, **connection_params: Any) -> None:
        self.connection_params = connection_params

    def fetch_all(self, query: str, params: Sequence[Any] | None = None) -> list[dict]:
        """SELECT: все строки, каждая — словарь «колонка → значение»."""
        # with connection только завершает транзакцию, закрывает соединение closing().
        with closing(psycopg2.connect(**self.connection_params)) as connection, connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]

    def execute(self, query: str, params: Sequence[Any] | None = None) -> None:
        """INSERT, UPDATE, DELETE: выполняет запрос и сохраняет изменения (commit)."""
        with closing(psycopg2.connect(**self.connection_params)) as connection, connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
