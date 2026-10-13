"""DQ-отчёты: отчёт скачивается один раз на файл тестов, каждый тест получает свой checker.

В тестовом файле должны быть ``FILE`` (имя файла отчёта) и ``PAYLOAD`` (тело запроса на формирование).

Переменные окружения:
    KEEP_DQ_REPORTS=false   — удалить отчёт после тестов (по умолчанию отчёты остаются)
    DQ_REPORTS_OUTPUT_DIR   — куда сохранять отчёты (по умолчанию examples/dq_reports/reports)
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from checks.excel import ExcelChecker, read_excel

REPORT_URL = "/api/v1/reports/generate"
REPORT_TIMEOUT = 300  # секунд: формирование отчёта на бэкенде бывает долгим
KEEP_REPORTS = os.getenv("KEEP_DQ_REPORTS", "true").lower() in ("true", "1", "yes")
OUTPUT_DIR = Path(os.getenv("DQ_REPORTS_OUTPUT_DIR") or Path(__file__).parent / "reports")


@pytest.fixture(scope="module")
def dq_report(request, tmp_path_factory, app_api) -> Iterator[tuple[Path, str | None, pd.DataFrame]]:
    """Отчёт файла тестов: путь, имя файла от сервера и таблица."""
    folder = OUTPUT_DIR if KEEP_REPORTS else tmp_path_factory.mktemp("dq_reports")
    path = folder / request.module.FILE
    filename = app_api.download(
        REPORT_URL,
        path,
        method="POST",
        json=request.module.PAYLOAD,
        headers={"Accept": "*/*"},
        timeout=REPORT_TIMEOUT,
    )
    yield path, filename, read_excel(path)
    if not KEEP_REPORTS:
        path.unlink(missing_ok=True)


@pytest.fixture
def checker(dq_report) -> ExcelChecker:
    """Новый checker на каждый тест: ошибки одного теста не попадают в другой."""
    path, filename, df = dq_report
    return ExcelChecker(df, name=path.name, filename=filename)
