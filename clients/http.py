"""HTTP-клиент с логом каждого запроса: общий для всех систем.

    api = HttpClient("https://api.example.com", headers={"Authorization": "Bearer ..."})
    data = api.get_json("/api/v1/orders", {"status": "draft"})   # JSON ответа, статус 200
    response = api.post("/api/v1/orders", json={"title": "..."})  # обычный requests.Response
    filename = api.download("/api/v1/reports", path, method="POST", json=payload)

Адрес, начинающийся с «/», дописывается к ``base_url``. Каждый запрос — шаг Allure «GET /путь»
с вложением: адрес, тело запроса, статус, длительность и ответ. Секретные параметры адреса
и поля JSON/форм (password, token, secret...) в логе и отчёте заменяются на ``***``.
Заголовки и тела неизвестного формата не сохраняются. Ошибки транспорта записываются
без исходного текста исключения, который может содержать адрес с секретами.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import allure
import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # секунд; для долгих запросов передайте свой timeout
HIDDEN_QUERY_PARAMS = {"token", "access_token", "api_key", "key", "password"}
SECRET_WORDS = ("password", "token", "secret", "authorization", "api_key", "apikey")  # части имён полей
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
        with allure.step(f"{method.upper()} {urlsplit(url).path}"):
            try:
                response = super().request(method, url, *args, **kwargs)
            except requests.RequestException as error:
                # В исходном исключении requests бывают URL, заголовки и тело запроса.
                # Не логируем traceback и не передаём его контекст в Allure.
                message = f"{method.upper()} {_hide_secrets(url)} → {type(error).__name__}"
                logger.error("%s", message)
                try:
                    safe_error = type(error)(message)
                except (TypeError, ValueError):
                    # Например, JSONDecodeError требует несколько аргументов конструктора.
                    safe_error = requests.RequestException(message)
                # Pytest включает аргументы последнего кадра в traceback/Allure.
                # Перепривязываем локальные значения, не меняя данные вызывающего кода.
                url, args, kwargs = _hide_secrets(url), (), {}
                raise safe_error from None

            # response.url — итоговый адрес вместе с параметрами из params=...
            line = (
                f"{response_summary(response)} "
                f"за {response.elapsed.total_seconds():.3f} сек."
            )
            # Потоковый ответ (download) не читаем: тело нужно файлу, а не отчёту.
            body = "<файл, не показывается>" if kwargs.get("stream") else _body_text(response)
            request_body = _request_body_text(response, kwargs, self.headers)
            allure.attach(
                line
                + (f"\n\nТело запроса:\n{request_body}" if request_body is not None else "")
                + f"\n\nОтвет:\n{body}",
                name=f"{method.upper()} → {response.status_code}",
                attachment_type=allure.attachment_type.TEXT,
            )
        if response.ok:
            logger.info(line)
        else:
            logger.error(line)
            logger.error("Ответ сервиса: %s", body)
        return response

    # Обёртки Session показывают исходные аргументы при pytest --tb=long.
    # Сохраняем семантику requests, но скрываем кадры с URL, заголовками и телом.
    def get(self, url, params=None, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        kwargs.setdefault("allow_redirects", True)
        return self.request("GET", url, params=params, **kwargs)

    def options(self, url, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        kwargs.setdefault("allow_redirects", True)
        return self.request("OPTIONS", url, **kwargs)

    def head(self, url, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        kwargs.setdefault("allow_redirects", False)
        return self.request("HEAD", url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        return self.request("POST", url, data=data, json=json, **kwargs)

    def put(self, url, data=None, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        return self.request("PUT", url, data=data, **kwargs)

    def patch(self, url, data=None, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        return self.request("PATCH", url, data=data, **kwargs)

    def delete(self, url, **kwargs) -> requests.Response:
        __tracebackhide__ = True
        return self.request("DELETE", url, **kwargs)

    def get_json(self, url: str, params: dict | None = None, **kwargs) -> Any:
        """GET и JSON ответа. Статус не 200 — тест падает сразу: проверять дальше нечего."""
        __tracebackhide__ = True
        response = self.get(url, params=params, **kwargs)
        _expect_ok(response)
        logger.debug("Ответ: %s", _body_text(response))
        return response_json(response)

    def download(self, url: str, path: Path, method: str = "GET", **kwargs) -> str | None:
        """Сохраняет ответ в ``path`` по частям; возвращает имя файла от сервера (Content-Disposition)."""
        __tracebackhide__ = True
        response = self.request(method, url, stream=True, **kwargs)
        _expect_ok(response)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                file.write(chunk)
        return _filename(response.headers.get("Content-Disposition", ""))


def response_summary(response: requests.Response) -> str:
    """Метод, адрес без секретов и статус: безопасная диагностика HTTP-ошибки."""
    method = response.request.method if response.request is not None else "HTTP"
    return f"{method} {_hide_secrets(response.url or '')} → {response.status_code}"


def response_json(response: requests.Response) -> Any:
    """JSON ответа; ошибка декодирования не содержит исходного тела или URL с секретами."""
    try:
        return response.json()
    except ValueError:
        # JSON-декодер держит исходное тело в аргументах своего traceback.
        raise requests.exceptions.JSONDecodeError(
            f"{response_summary(response)}: ответ не является корректным JSON", "", 0
        ) from None


def _expect_ok(response: requests.Response) -> None:
    assert response.status_code == 200, (
        f"{response_summary(response)}: ожидался статус 200. Ответ: {_body_text(response)[:500]}"
    )


def _is_secret(key: str) -> bool:
    key = key.lower()
    return key in HIDDEN_QUERY_PARAMS or any(word in key for word in SECRET_WORDS)


def _mask(data: Any) -> Any:
    """Копия JSON, где значения секретных полей заменены на ``***``."""
    if isinstance(data, dict):
        return {key: "***" if _is_secret(str(key)) else _mask(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_mask(value) for value in data]
    return data


def _masked_json(data: Any) -> str:
    """JSON без секретов, обрезанный до ``MAX_LOGGED_BODY``."""
    text = json.dumps(_mask(data), ensure_ascii=False, indent=2, default=str)
    return text[:MAX_LOGGED_BODY] + ("…" if len(text) > MAX_LOGGED_BODY else "")


def _formatted_body(data: Any, content_type: str = "") -> str:
    """Маскирует JSON/URL-encoded форму. Неизвестное тело не сохраняется."""
    omitted = "<тело не показано: формат не поддерживает безопасное маскирование>"
    if isinstance(data, (dict, list)):
        return _masked_json(data)
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8")
        except UnicodeDecodeError:
            return omitted
    if not isinstance(data, str):
        return omitted
    if not data:
        return ""

    if isinstance(content_type, bytes):
        content_type = content_type.decode("ascii", errors="replace")
    media_type = content_type.split(";", 1)[0].strip().lower()
    is_json = media_type == "application/json" or media_type.endswith("+json")
    is_form = media_type == "application/x-www-form-urlencoded"
    if media_type and not (is_json or is_form):
        return omitted
    if is_json or not media_type:
        try:
            parsed = json.loads(data)
        except ValueError:
            pass
        else:
            return _masked_json(parsed) if isinstance(parsed, (dict, list)) else omitted
    if is_form or not media_type:
        try:
            pairs = parse_qsl(data, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            pass
        else:
            if pairs:
                # Список объектов сохраняет повторяющиеся имена параметров формы.
                return _masked_json([{key: value} for key, value in pairs])
    return omitted


def _request_body_text(response: requests.Response, kwargs: dict, headers: dict) -> str | None:
    """Использует фактически отправленное тело, включая data при json=None."""
    if response.request is not None:
        body = response.request.body
        content_type = response.request.headers.get("Content-Type", "")
    else:
        # Полезно для пользовательских адаптеров, не заполняющих response.request.
        body = kwargs.get("data")
        if not body and kwargs.get("json") is not None:
            body = kwargs["json"]
            content_type = "application/json"
        else:
            request_headers = requests.structures.CaseInsensitiveDict(headers)
            request_headers.update(kwargs.get("headers") or {})
            content_type = request_headers.get("Content-Type", "")
            if isinstance(body, (dict, list, tuple)):
                body = urlencode(body, doseq=True)
                content_type = "application/x-www-form-urlencoded"
    return None if body is None else _formatted_body(body, content_type)


def _body_text(response: requests.Response) -> str:
    """Безопасное тело ответа для лога и отчёта; неизвестный формат опускается."""
    try:
        data = response.json()
    except ValueError:
        return _formatted_body(response.text, response.headers.get("Content-Type", ""))
    return _formatted_body(data)


def _hide_secrets(url: str) -> str:
    """Заменяет значения секретных query-параметров на ``***`` для лога."""
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, "***" if _is_secret(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ],
        safe="*$'(),:/",
    )
    netloc = "***@" + parts.netloc.rsplit("@", 1)[1] if "@" in parts.netloc else parts.netloc
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def _filename(content_disposition: str) -> str | None:
    """Имя файла из заголовка ``Content-Disposition``."""
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
    if encoded:
        return unquote(encoded.group(1).strip())
    plain = re.search(r'filename=["\']?([^"\';]+)', content_disposition, re.IGNORECASE)
    return plain.group(1).strip() if plain else None
