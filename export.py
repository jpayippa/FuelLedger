import io

from openpyxl import Workbook
from openpyxl.styles import Font


def build_workbook(receipts, total_cents):
    wb = Workbook()
    ws = wb.active
    ws.title = "Gas Receipts"

    headers = ["Date", "Amount"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in receipts:
        ws.append([r["date"], r["amount_cents"] / 100])

    ws.append([])
    total_row = ws.max_row + 1
    ws.cell(row=total_row, column=1, value="Total").font = Font(bold=True)
    ws.cell(row=total_row, column=2, value=total_cents / 100).font = Font(bold=True)

    for col, width in zip("AB", (14, 12)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = "$#,##0.00"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
