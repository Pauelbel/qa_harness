"""Проверки качества данных Excel-отчёта.

    with ExcelChecker(read_excel("report.xlsx"), name="report.xlsx") as checker:
        checker.check_date("Дата")
        checker.check_enum("Статус", ("Да", "Нет"))

Ошибка — одна на правило: сколько строк из скольких его нарушают, номера строк и примеры значений.
Пустые ячейки проверки значений пропускают; заполненность проверяет ``check_required``.
Числовые проверки (целое, знаки после запятой, диапазон, расчёт стоимости) сами считают
ошибкой заполненную ячейку, которая не является числом: ``check_is_numeric`` перед ними не нужен.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from checks.base import Checker
from report import step

MAX_EXAMPLES = 3  # сколько номеров строк и значений показать в ошибке


# ------------------------------------------------------------------------
# Чтение листа: пробелы обрезаются, пустые ячейки становятся pd.NA
# ------------------------------------------------------------------------

def read_excel(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    """Читает xlsx: обрезает пробелы у текста, пустые ячейки → ``pd.NA``.

    Типы ячеек сохраняются: в смешанной колонке число 123 остаётся числом, а не текстом "123".
    Текст "None", "nan", "NA" остаётся значением, а не пропуском.
    """
    df = pd.read_excel(path, engine="openpyxl", keep_default_na=False, na_values=[""], sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        if _is_text(df[col]):
            df[col] = df[col].map(_clean_cell).astype(object)
        else:
            df[col] = df[col].replace(float("nan"), pd.NA)
    return df


def _clean_cell(value: Any) -> Any:
    """Текст — без пробелов по краям, пустой текст и NaN — ``pd.NA``, остальные типы как есть."""
    if isinstance(value, str):
        value = value.strip()
        return value if value else pd.NA
    return pd.NA if _is_na(value) else value


# ------------------------------------------------------------------------
# ExcelChecker: таблица и имя файла, накопление ошибок — в общем Checker
# ------------------------------------------------------------------------

class ExcelChecker(Checker):
    def __init__(self, df: pd.DataFrame, name: str = "", filename: str | None = None) -> None:
        super().__init__(title=f"Отчёт: {name}" if name else "")
        self.df = df
        self.filename = filename  # имя файла от сервера, для check_filename

    # ------------------------------------------------------------------------
    # Структура: колонки, имя файла, дубликаты и заполненность отчёта
    # ------------------------------------------------------------------------

    @step("Структура: состав и порядок колонок")
    def check_columns(self, expected: Sequence[str], strict_order: bool = False) -> ExcelChecker:
        """Все ожидаемые колонки на месте, лишних нет; при ``strict_order`` — и порядок совпадает."""
        actual = list(self.df.columns)
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        if missing:
            self.fail(f"Структура: отсутствуют столбцы {missing}")
        if extra:
            self.fail(f"Структура: лишние столбцы {extra}")
        if strict_order and list(expected) != [c for c in actual if c in expected]:
            self.fail("Структура: порядок столбцов не совпадает с ожидаемым")
        return self

    @step("Имя файла соответствует шаблону")
    def check_filename(self, pattern: str) -> ExcelChecker:
        """Имя файла от сервера (Content-Disposition) соответствует регулярному выражению."""
        if self.filename is None:
            self.fail("Имя файла: сервер не передал имя файла")
        elif not re.search(pattern, self.filename):
            self.fail(f"Имя файла: «{self.filename}» не соответствует шаблону «{pattern}»")
        return self

    @step("Нет полностью пустых колонок")
    def check_no_fully_empty_columns(self, columns: Sequence[str] | None = None) -> ExcelChecker:
        """Ни одна колонка не пуста целиком."""
        if self.df.empty:
            return self.fail("Отчёт не содержит строк")
        for col in columns or self.df.columns:
            if not self._missing(col) and self._empty(col).all():
                self.fail(f'"{col}" → колонка полностью пуста: 0% заполненности')
        return self

    @step("Нет дубликатов строк")
    def check_no_duplicate_rows(
        self, columns: Sequence[str] | None = None, message: str = "полный дубликат строки"
    ) -> ExcelChecker:
        """Нет строк, совпадающих по всем ``columns`` (по умолчанию — по всем колонкам)."""
        columns = list(columns) if columns is not None else list(self.df.columns)
        if self._missing(*columns):
            return self
        rows = [index + 2 for index in self.df.index[self.df.duplicated(subset=columns, keep=False)]]
        if rows:
            self.fail(f"Правило: {message}. Дубликатов: {len(rows)}. Строки: {_rows_text(rows)}")
        return self

    @step("Статистика заполненности колонок")
    def get_fill_statistics(self, columns: Sequence[str] | None = None) -> pd.DataFrame:
        """Таблица заполненности; пустой отчёт и отсутствующие колонки — ошибка."""
        total = len(self.df)
        if not total:
            raise AssertionError("Нельзя собрать статистику: отчёт не содержит строк")
        selected = list(columns) if columns is not None else list(self.df.columns)
        missing = [column for column in selected if column not in self.df.columns]
        if missing:
            raise AssertionError(f"Нельзя собрать статистику: отсутствуют столбцы {missing}")
        rows = []
        for col in selected:
            empty = int(self._empty(col).sum())
            rows.append((col, total - empty, empty, round((total - empty) / total * 100, 2)))
        return pd.DataFrame(rows, columns=["Колонка", "Заполнено", "Пусто", "Заполненность, %"])

    def get_row_count(self) -> int:
        """Количество строк данных в отчёте (без заголовка)."""
        return len(self.df)

    # ------------------------------------------------------------------------
    # Значения: пустые ячейки пропускаются, обязательность задаёт check_required
    # ------------------------------------------------------------------------

    @step("Обязательные колонки заполнены")
    def check_required(self, columns: Sequence[str]) -> ExcelChecker:
        """Колонки заполнены во всех строках."""
        for col in columns:
            if not self._missing(col):
                self._add(self._empty(col), col, "обязательное поле должно быть заполнено")
        return self

    @step("{column}: текст")
    def check_text(self, column: str) -> ExcelChecker:
        if not self._missing(column):
            is_text = self.df[column].map(lambda value: isinstance(value, str))
            self._add(~self._empty(column) & ~is_text, column, "должно быть текстовым значением")
        return self

    @step("{column}: {description}")
    def check_regex(self, column: str, pattern: str, description: str) -> ExcelChecker:
        """Значение целиком соответствует ``pattern``; ``description`` попадает в текст ошибки."""
        if not self._missing(column):
            matches = self.df[column].astype(str).str.strip().str.fullmatch(pattern, na=False)
            self._add(~self._empty(column) & ~matches, column, description)
        return self

    @step("{column}: значение из допустимого списка")
    def check_enum(self, column: str, allowed: Iterable[str]) -> ExcelChecker:
        if not self._missing(column):
            allowed = list(allowed)
            bad = self.df[column].notna() & ~self.df[column].isin(allowed)
            self._add(bad, column, f"значение должно входить в допустимый список: {allowed}")
        return self

    @step("{column}: дата в формате {fmt}")
    def check_date(self, column: str, fmt: str = "%d.%m.%Y") -> ExcelChecker:
        if not self._missing(column):
            parsed = pd.to_datetime(self.df[column], format=fmt, errors="coerce")
            self._add(self.df[column].notna() & parsed.isna(), column, f"дата должна соответствовать формату {fmt}")
        return self

    @step("{column}: период из двух дат")
    def check_date_period(self, column: str, fmt: str = "%d.%m.%Y") -> ExcelChecker:
        """Период вида ``01.01.2026 - 31.01.2026`` с началом не позже окончания."""
        if not self._missing(column):
            parts = self.df[column].astype(str).str.extract(r"^\s*(.+?)\s*[-–—]\s*(.+?)\s*$")
            start = pd.to_datetime(parts[0], format=fmt, errors="coerce")
            end = pd.to_datetime(parts[1], format=fmt, errors="coerce")
            bad = ~self._empty(column) & (start.isna() | end.isna())
            self._add(bad, column, f"должно содержать две корректные даты формата {fmt}, разделённые дефисом")
            self._add(
                start.notna() & end.notna() & (start > end),
                column,
                "дата начала периода не должна быть позже даты окончания",
            )
        return self

    # ------------------------------------------------------------------------
    # Числа: заполненные нечисловые ячейки считаются нарушением
    # ------------------------------------------------------------------------

    @step("{column}: число")
    def check_is_numeric(self, column: str) -> ExcelChecker:
        """Заполненные ячейки — числа (или текст, который читается как число: "12.5")."""
        if not self._missing(column):
            self._numbers(column)
        return self

    @step("{column}: целое число")
    def check_integer(self, column: str) -> ExcelChecker:
        if not self._missing(column):
            numeric = self._numbers(column)
            self._add(numeric.notna() & (numeric != numeric.round()), column, "должно быть целым числом")
        return self

    @step("{column}: не более {max_decimal_places} знаков после запятой")
    def check_decimal_places(self, column: str, max_decimal_places: int) -> ExcelChecker:
        if not self._missing(column):
            numeric = self._numbers(column)
            bad = numeric.notna() & ((numeric - numeric.round(max_decimal_places)).abs() > 1e-9)
            self._add(bad, column, f"число должно содержать не более {max_decimal_places} знаков после запятой")
        return self

    @step("{column}: число в допустимом диапазоне")
    def check_range(
        self,
        column: str,
        min_value: float | None = None,
        min_inclusive: bool = True,
        max_value: float | None = None,
        max_inclusive: bool = True,
    ) -> ExcelChecker:
        """Число в границах; ``min_inclusive=False`` — строго больше ``min_value``.

        Заполненная ячейка, которая не является числом, — тоже ошибка.
        """
        if min_value is None and max_value is None:
            raise ValueError("Для проверки диапазона нужна хотя бы одна граница")
        if not self._missing(column):
            numeric = self._numbers(column)
            valid, rule = _in_range(numeric, min_value, min_inclusive, max_value, max_inclusive)
            self._add(numeric.notna() & ~valid, column, rule)
        return self

    @step("{column}: процент")
    def check_percentage(
        self,
        column: str,
        max_decimal_places: int = 2,
        min_value: float | None = 0,
        min_inclusive: bool = True,
        max_value: float | None = None,
        max_inclusive: bool = True,
    ) -> ExcelChecker:
        """Процент вида ``25,5%``: знак %, не больше ``max_decimal_places`` знаков, в границах."""
        if self._missing(column):
            return self
        text = self.df[column].astype(str)
        sign = "-?" if min_value is None or min_value < 0 else ""
        matches = text.str.fullmatch(rf"{sign}(?:0|[1-9]\d*)(?:[.,]\d{{1,{max_decimal_places}}})?%", na=False)
        numeric = pd.to_numeric(text.str.rstrip("%").str.replace(",", ".", regex=False), errors="coerce")
        valid, rule = _in_range(numeric, min_value, min_inclusive, max_value, max_inclusive)
        self._add(
            ~self._empty(column) & ~(matches & valid),
            column,
            f"процент должен иметь символ % и не более {max_decimal_places} знаков после разделителя; "
            f"{rule or 'значение может быть любого знака'}",
        )
        return self

    @step("{cost_col} = {hours_col} × {rate_col}")
    def check_cost_calculation(
        self, hours_col: str, rate_col: str, cost_col: str, tolerance: float = 0.01
    ) -> ExcelChecker:
        """Стоимость = часы × ставка (округлено до копеек) с погрешностью ``tolerance``.

        Заполненная ячейка любой из трёх колонок, которая не является числом, — тоже ошибка.
        """
        if self._missing(hours_col, rate_col, cost_col):
            return self
        hours, rate, cost = self._numbers(hours_col), self._numbers(rate_col), self._numbers(cost_col)
        bad = hours.notna() & rate.notna() & cost.notna() & ((cost - (hours * rate).round(2)).abs() > tolerance)
        self._add(
            bad,
            cost_col,
            f"стоимость должна быть равна «{hours_col}» × «{rate_col}» с погрешностью не более {tolerance}",
        )
        return self

    # ------------------------------------------------------------------------
    # Диагностика: одна ошибка на правило, номера строк учитывают заголовок Excel
    # ------------------------------------------------------------------------

    def _add(self, mask: pd.Series, column: str, rule: str) -> None:
        """Одна ошибка на правило: сколько строк нарушают, номера строк и примеры значений."""
        bad = self.df.index[mask.fillna(False).astype(bool)]
        if bad.empty:
            return
        rows = [index + 2 for index in bad]  # строка в Excel: заголовок — 1, данные — с 2
        examples = "; ".join(f"строка {index + 2}: {_show(self.df.at[index, column])}" for index in bad[:MAX_EXAMPLES])
        self.fail(
            f'"{column}" → Правило: {rule}. Ошибок: {len(rows)} из {len(self.df)}. Строки: {_rows_text(rows)}\n'
            f"Примеры значений: {examples}"
        )

    def _missing(self, *columns: str) -> bool:
        """Пишет ошибку про отсутствующие колонки и возвращает True, если таких колонок нет в отчёте."""
        missing = [c for c in columns if c not in self.df.columns]
        for col in missing:
            self.fail(f'"{col}" → столбец не найден')
        return bool(missing)

    def _empty(self, column: str) -> pd.Series:
        series = self.df[column]
        if _is_text(series):
            return series.isna() | (series.astype(str).str.strip() == "")
        return series.isna()

    def _numeric(self, column: str) -> pd.Series:
        """Числа колонки; не число (и True/False) — ``NaN``."""
        values = self.df[column].map(lambda value: pd.NA if isinstance(value, bool) else value)
        return pd.to_numeric(values, errors="coerce").astype(float)

    def _numbers(self, column: str) -> pd.Series:
        """Числа колонки; заполненные ячейки, которые не являются числом, — ошибка правила."""
        numeric = self._numeric(column)
        self._add(~self._empty(column) & numeric.isna(), column, "значение должно быть числом")
        return numeric


# ------------------------------------------------------------------------
# Вспомогательные функции: типы ячеек, границы чисел и короткие сообщения
# ------------------------------------------------------------------------

def _is_na(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):  # списки и прочие не-скаляры
        return False


def _is_text(series: pd.Series) -> bool:
    """pandas 3 читает текст как ``str``, смешанные колонки — как ``object``."""
    return series.dtype == "object" or isinstance(series.dtype, pd.StringDtype)


def _in_range(
    numeric: pd.Series, min_value, min_inclusive: bool, max_value, max_inclusive: bool
) -> tuple[pd.Series, str]:
    """Маска «в границах» и текст правила для сообщения."""
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError("Минимальная граница не может быть больше максимальной")
    valid = pd.Series(True, index=numeric.index)
    rules = []
    if min_value is not None:
        valid &= numeric >= min_value if min_inclusive else numeric > min_value
        rules.append(f"значение должно быть {'не меньше' if min_inclusive else 'строго больше'} {min_value}")
    if max_value is not None:
        valid &= numeric <= max_value if max_inclusive else numeric < max_value
        rules.append(f"значение должно быть {'не больше' if max_inclusive else 'строго меньше'} {max_value}")
    return valid, " и ".join(rules)


def _rows_text(rows: list[int]) -> str:
    """«2, 5, 9 ... и ещё 12» — первые номера строк Excel."""
    text = ", ".join(map(str, rows[:MAX_EXAMPLES]))
    return text + (f" ... и ещё {len(rows) - MAX_EXAMPLES}" if len(rows) > MAX_EXAMPLES else "")


def _show(value: Any, max_length: int = 120) -> str:
    """Короткое представление значения ячейки для сообщения об ошибке."""
    if _is_na(value):
        return "<пусто>"
    text = str(value).replace("\n", " ").replace("\r", " ")
    return f"«{text[:max_length]}…»" if len(text) > max_length else f"«{text}»"
