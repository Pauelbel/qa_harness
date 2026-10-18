"""Клиент OData API: ``HttpClient``, который проверяет структуру ответа и достаёт записи из ``value``.

    items = api.get_items("/api/v1/orders", {"$top": "5"})        # записи
    data = api.get_response("/api/v1/orders", {"$count": "true"})  # весь ответ, с @odata.count

Ответ без массива ``value`` (например, ``{"error": ...}`` со статусом 200) — тест падает сразу.
Пустой ``value`` — корректный ответ: подходит ли он, решает тест (``check_not_empty``).
"""

from __future__ import annotations

from clients.http import HttpClient


class OdataClient(HttpClient):
    def get_response(self, url: str, params: dict | None = None) -> dict:
        """Ответ целиком: объект с массивом ``value``. Статус не 200 или другая структура — тест падает."""
        __tracebackhide__ = True  # URL и параметры могут содержать секреты.
        data = self.get_json(url, params)
        if not isinstance(data, dict):
            raise AssertionError(f"Ожидался JSON-объект OData, получен {type(data).__name__}. См. HTTP-шаг.")
        if "value" not in data:
            raise AssertionError("В ответе OData нет массива value. См. HTTP-шаг.")
        if not isinstance(data["value"], list):
            raise AssertionError(
                f"В ответе OData value должен быть массивом, получен {type(data['value']).__name__}. См. HTTP-шаг."
            )
        return data

    def get_items(self, url: str, params: dict | None = None) -> list[dict]:
        """Записи ответа — массив ``value``. Статус не 200 или другая структура — тест падает."""
        __tracebackhide__ = True
        return self.get_response(url, params)["value"]
