"""Клиент OData API: ``HttpClient``, который достаёт записи из массива ``value``.

    items = api.get_items("/api/v1/orders", {"$top": "5"})    # записи
    data = api.get_json("/api/v1/orders", {"$count": "true"})  # весь ответ, с @odata.count
"""

from __future__ import annotations

from clients.http import HttpClient


class OdataClient(HttpClient):
    def get_items(self, url: str, params: dict | None = None) -> list[dict]:
        """Записи ответа — массив ``value``. Статус не 200 — тест падает сразу."""
        return self.get_json(url, params).get("value", [])
