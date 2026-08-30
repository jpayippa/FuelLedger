import re
import zipfile

import export


def test_build_workbook_has_expected_sheets_and_totals(fresh_db, vehicle_id):
    fresh_db.insert_fuel_log(
        vehicle_id, None, "2026-06-01", 5510, 1000.0, "Shell", 35.0, "L", 1.575, None, "", None,
    )
    fresh_db.insert_maintenance_log(
        vehicle_id, None, "2026-06-15", 12000, 1200.0, "Canadian Tire", "Oil Change", None, None, None,
    )
    fresh_db.insert_odometer_log(vehicle_id, "2026-08-01", 2200.0, "checkpoint")

    buf = export.build_workbook(
        fuel_logs=fresh_db.list_fuel_logs(),
        maintenance_logs=fresh_db.list_maintenance_logs(),
        odometer_logs=fresh_db.list_odometer_logs(),
        monthly_totals=fresh_db.get_monthly_totals(months=999),
        yearly_totals=fresh_db.get_yearly_totals(),
        per_vehicle_summary=fresh_db.get_per_vehicle_summary(),
    )

    with zipfile.ZipFile(buf) as z:
        workbook_xml = z.read("xl/workbook.xml").decode()
        sheet_names = re.findall(r'<sheet name="([^"]+)"', workbook_xml)
        assert sheet_names == [
            "Fuel Logs", "Maintenance Logs", "Odometer Logs",
            "Monthly Summary", "Yearly Summary", "Summary",
        ]

        fuel_sheet = z.read("xl/worksheets/sheet1.xml").decode()
        assert "55.1" in fuel_sheet  # amount_cents 5510 / 100
        assert "Shell" in fuel_sheet

        summary_sheet = z.read("xl/worksheets/sheet6.xml").decode()
        assert "Test Car" in summary_sheet


def test_build_csv_contains_rows_and_total(fresh_db, vehicle_id):
    fresh_db.insert_fuel_log(
        vehicle_id, None, "2026-06-01", 5510, None, "Shell", None, None, None, None, "", None,
    )
    fresh_db.insert_fuel_log(
        vehicle_id, None, "2026-07-01", 6020, None, "Esso", None, None, None, None, "", None,
    )

    buf = export.build_csv(fresh_db.list_fuel_logs())
    text = buf.getvalue().decode("utf-8")

    assert "Shell" in text
    assert "Esso" in text
    assert "55.10" in text
    assert "60.20" in text
    assert "115.30" in text  # total
