"""Тестовые данные: общие помощники для фикстур, которые создают записи.

    from core.data import unique_title
    project = {"id": str(uuid.uuid4()), "title": unique_title()}
"""

import uuid


def unique_title() -> str:
    """Название тестовых данных: qa_autotest- видно в БД, хвост не пересекается с другими запусками."""
    return f"qa_autotest-{uuid.uuid4().hex[:8]}"
