"""HTTP-клиент с логом каждого запроса: общий для всех систем.

    api = HttpClient("https://api.example.com", headers={"Authorization": "Bearer ..."})
    data = api.get_json("/api/v1/orders", {"status": "draft"})   # JSON ответа, статус 200
    response = api.post("/api/v1/orders", json={"title": "..."})  # обычный requests.Response
    filename = api.download("/api/v1/reports", path, method="POST", json=payload)

Адрес, начинающийся с «/», дописывается к ``base_url``. Секретные параметры адреса
в логе заменяются на ``***``. Тело ответа пишется в лог на уровне DEBUG, при ошибке — ERROR.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # секунд; для долгих запросов передайте свой timeout
HIDDEN_QUERY_PARAMS = {"token", "access_token", "api_key", "key", "password"}
MAX_LOGGED_BODY = 2000


class HttpClient(requests.Session):
    """``requests.Session`` с адресом системы, заголовками, таймаутом по умолчанию и логом.

    ``verify=False`` — не проверять HTTPS-сертификат (тестовые стенды).
    """

    def __init__(self, base_url: str = "", headers: dict | None = None, verify: bool | str = True) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.headers.update(headers or {})
        self.verify = verify

    def request(self, method, url, *args, **kwargs) -> requests.Response:
        if url.startswith("/"):
            url = self.base_url + url
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        try:
            response = super().request(method, url, *args, **kwargs)
        except requests.RequestException:
            logger.exception("%s %s → ошибка подключения", method.upper(), _hide_secrets(url))
            raise

        # response.url — итоговый адрес вместе с параметрами из params=...
        line = f"{method.upper()} {_hide_secrets(response.url)} → {response.status_code} за {response.elapsed.total_seconds():.3f} сек."
        if response.ok:
            logger.info(line)
        else:
            logger.error(line)
            logger.error("Ответ сервиса: %s", response.text[:MAX_LOGGED_BODY])
        return response

    def get_json(self, url: str, params: dict | None = None, **kwargs) -> Any:
        """GET и JSON ответа. Статус не 200 — тест падает сразу: проверять дальше нечего."""
        response = self.get(url, params=params, **kwargs)
        _expect_ok(response)
        logger.debug("Ответ: %s", response.text[:MAX_LOGGED_BODY])
        return response.json()

    def download(self, url: str, path: Path, method: str = "GET", **kwargs) -> str | None:
        """Сохраняет ответ в ``path`` по частям; возвращает имя файла от сервера (Content-Disposition)."""
        response = self.request(method, url, stream=True, **kwargs)
        _expect_ok(response)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                file.write(chunk)
        return _filename(response.headers.get("Content-Disposition", ""))


def _expect_ok(response: requests.Response) -> None:
    assert response.status_code == 200, (
        f"{response.request.method} {_hide_secrets(response.url)}: ожидался статус 200, "
        f"получен {response.status_code}. Ответ: {response.text[:500]}"
    )


def _hide_secrets(url: str) -> str:
    """Заменяет значения секретных query-параметров на ``***`` для лога."""
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, "***" if key.lower() in HIDDEN_QUERY_PARAMS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ],
        safe="*$'(),:/",
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _filename(content_disposition: str) -> str | None:
    """Имя файла из заголовка ``Content-Disposition``."""
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
    if encoded:
        return unquote(encoded.group(1).strip())
    plain = re.search(r'filename=["\']?([^"\';]+)', content_disposition, re.IGNORECASE)
    return plain.group(1).strip() if plain else None
