"""API-тесты: тестовые данные создаются через API и удаляются после теста.

Тест проверяет то, что создал сам, а не то, что случайно лежит на стенде:
для $filter — запись, которая подходит, и запись, которая не подходит.

    def test_filter(self, app_api, create_order):
        draft = create_order(Status="Draft")
        closed = create_order(Status="Closed")
"""

from collections.abc import Callable, Iterator

import allure
import pytest

from clients.http import response_json
from examples.conftest import unique_title

ORDERS_URL = "/api/v1/orders"
MAX_CLEANUP_ERRORS = 20


@pytest.fixture
def create_order(app_api) -> Iterator[Callable[..., dict]]:
    """Фабрика заказов: ``create_order(Status="Draft")`` → созданная запись из ответа API.

    Обязательные поля вашей системы добавьте в ``payload``. Все созданные заказы
    удаляются после теста, даже если он упал.
    Удаление подтверждают статусы 200/204; 404 тоже допустим — записи уже нет.
    Остальные статусы (включая 202) и ошибки запроса отмечаются после попытки
    удалить все созданные заказы.
    """
    created: list[dict] = []

    def create(**fields) -> dict:
        payload = {"Title": unique_title(), **fields}
        with allure.step(f"Предусловие: создать заказ «{payload['Title']}» через API"):
            response = app_api.post(ORDERS_URL, json=payload)
            if response.status_code != 201:
                raise AssertionError(
                    f"Заказ не создан: ожидался статус 201, получен {response.status_code}. См. HTTP-шаг."
                )
            order = response_json(response)
        created.append(order.copy())
        return order

    yield create

    errors: list[str] = []
    for number, order in reversed(list(enumerate(created, start=1))):
        failure = None
        try:
            with allure.step(f"Постусловие: удалить тестовый заказ #{number}"):
                try:
                    response = app_api.delete(f"{ORDERS_URL}({order['Id']})")
                except Exception as error:
                    # Не передаём текст исключения в Allure: в нём может быть URL с токеном.
                    failure = f"Заказ #{number}: ошибка DELETE ({type(error).__name__}). См. HTTP-шаг."
                else:
                    if response.status_code not in (200, 204, 404):
                        failure = (
                            f"Заказ #{number}: DELETE вернул статус {response.status_code}, "
                            "ожидался 200, 204 или 404. См. HTTP-шаг."
                        )
                if failure:
                    # Вне except: в traceback шага нет исходного исключения с секретами.
                    raise AssertionError(failure)
        except AssertionError:
            if failure is None:
                raise
        if failure:
            errors.append(failure)

    if errors:
        details = "\n".join(errors[:MAX_CLEANUP_ERRORS])
        if len(errors) > MAX_CLEANUP_ERRORS:
            details += f"\n... и ещё {len(errors) - MAX_CLEANUP_ERRORS}; подробности — в шагах удаления."
        raise AssertionError(
            f"Не удалось подтвердить удаление {len(errors)} из {len(created)} заказов:\n{details}"
        )
