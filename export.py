import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _bold_row(ws, row_idx):
    for cell in ws[row_idx]:
        cell.font = Font(bold=True)


def build_workbook(receipts, total_cents, monthly_totals, yearly_totals):
    wb = Workbook()

    ws = wb.active
    ws.title = "Receipts"
    ws.append(["Date", "Station", "Amount", "Volume", "Unit", "Price/Unit"])
    _bold_row(ws, 1)
    for r in receipts:
        ws.append([
            r["date"],
            r.get("station") or "",
            r["amount_cents"] / 100,
            r.get("volume"),
            r.get("volume_unit") or "",
            r.get("price_per_unit"),
        ])
    ws.append([])
    total_row = ws.max_row + 1
    ws.cell(row=total_row, column=1, value="Total").font = Font(bold=True)
    ws.cell(row=total_row, column=3, value=total_cents / 100).font = Font(bold=True)
    for col, width in zip("ABCDEF", (14, 18, 12, 10, 8, 12)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = "$#,##0.00"

    ws2 = wb.create_sheet("Monthly Summary")
    ws2.append(["Month", "Total", "Fill-ups", "Avg Price/Unit"])
    _bold_row(ws2, 1)
    for m in monthly_totals:
        ws2.append([
            m["period"],
            m["total_cents"] / 100,
            m["count"],
            round(m["avg_price_per_unit"], 3) if m.get("avg_price_per_unit") else None,
        ])
    for col, width in zip("ABCD", (12, 12, 10, 14)):
        ws2.column_dimensions[col].width = width
    for row in ws2.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = "$#,##0.00"

    ws3 = wb.create_sheet("Yearly Summary")
    ws3.append(["Year", "Total", "Fill-ups"])
    _bold_row(ws3, 1)
    for y in yearly_totals:
        ws3.append([y["year"], y["total_cents"] / 100, y["count"]])
    for col, width in zip("ABC", (10, 12, 10)):
        ws3.column_dimensions[col].width = width
    for row in ws3.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = "$#,##0.00"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_csv(receipts, total_cents):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Station", "Amount", "Volume", "Unit", "Price/Unit"])
    for r in receipts:
        writer.writerow([
            r["date"],
            r.get("station") or "",
            f'{r["amount_cents"] / 100:.2f}',
            r.get("volume") or "",
            r.get("volume_unit") or "",
            r.get("price_per_unit") or "",
        ])
    writer.writerow([])
    writer.writerow(["Total", "", f"{total_cents / 100:.2f}"])
    return io.BytesIO(buf.getvalue().encode("utf-8"))
