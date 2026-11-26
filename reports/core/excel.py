"""Excel export that reproduces the layout of the reference workbook. Framework independent.

Reference facts (inspected from 25-11-2026_same_day_only.xlsx):
* one sheet "Sheet1", header in row 1, one row per district in a fixed order, no totals row
* columns: Sr, District, Date, then the category columns with their legacy spellings
* the Date column holds TEXT 'dd-mm-yyyy' (number format dd-mm-yyyy)
* header: bold white Calibri on green (228B22), centred, wrapped, thin borders
"""
from __future__ import annotations

import io
from datetime import date
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .constants import (COLUMN_WIDTHS, DATE_NUMBER_FORMAT, DATE_TEXT_FORMAT, FIXED_COLUMNS,
                        HEADER_FILL_RGB, REFERENCE_SHEET_NAME)

THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def build_workbook(report_date: date,
                   rows: Iterable[Tuple[str, Dict[str, int]]],
                   categories: Sequence[Tuple[str, str]],
                   include_totals_row: bool = False) -> Workbook:
    """rows: (district name, {category code: value}) in reference order.
    categories: (code, excel header) in column order.
    Refuses to export missing, negative or non-integer values."""
    date_text = report_date.strftime(DATE_TEXT_FORMAT)
    headers = [*FIXED_COLUMNS, *(h for _, h in categories)]
    records: List[list] = []
    for sr, (name, values) in enumerate(rows, 1):
        numbers = []
        for code, header in categories:
            v = values.get(code, 0)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"Cannot export {name} / {header}: {v!r} is not a non-negative whole number.")
            numbers.append(v)
        records.append([sr, name, date_text, *numbers])
    names = [r[1] for r in records]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate district rows - refusing to export.")
    frame = pd.DataFrame(records, columns=headers)

    wb = Workbook()
    ws = wb.active
    ws.title = REFERENCE_SHEET_NAME

    header_fill = PatternFill("solid", fgColor=HEADER_FILL_RGB)
    for col, title in enumerate(frame.columns, 1):
        c = ws.cell(row=1, column=col, value=title)
        c.font = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER

    body_font = Font(name="Calibri", size=11)
    for r, row in enumerate(frame.itertuples(index=False), 2):
        for col, value in enumerate(row, 1):
            c = ws.cell(row=r, column=col, value=value)
            c.font = body_font
            c.border = BORDER
            c.alignment = Alignment(horizontal="left" if col == 2 else "center", vertical="center")
            if col == 3:
                c.number_format = DATE_NUMBER_FORMAT

    last = len(frame) + 1
    if include_totals_row and len(frame):
        t = last + 1
        ws.cell(row=t, column=2, value="Total")
        for col in range(len(FIXED_COLUMNS) + 1, len(headers) + 1):
            L = get_column_letter(col)
            ws.cell(row=t, column=col, value=f"=SUM({L}2:{L}{last})")
        for col in range(1, len(headers) + 1):
            c = ws.cell(row=t, column=col)
            c.font = Font(name="Calibri", size=11, bold=True)
            c.border = BORDER
            c.alignment = Alignment(horizontal="left" if col == 2 else "center")

    for letter, width in COLUMN_WIDTHS.items():
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"
    return wb


def workbook_to_bytes(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def read_sheet_values(path_or_file) -> List[list]:
    """Plain cell values of the first sheet (used by tests / comparison with the reference)."""
    from openpyxl import load_workbook
    ws = load_workbook(path_or_file).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]
