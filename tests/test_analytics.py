def seed_fuel(db, vehicle_id, date_str, amount_cents, price_per_unit=None, odometer=None):
    return db.insert_fuel_log(
        vehicle_id, None, date_str, amount_cents, odometer, "Station",
        None, "L", price_per_unit, None, "", None,
    )


class TestPeriodTotals:
    def test_monthly_totals_group_and_sum_correctly(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2026-06-05", 5510, 1.575)
        seed_fuel(fresh_db, vehicle_id, "2026-06-20", 6000, 1.580)
        seed_fuel(fresh_db, vehicle_id, "2026-07-10", 6020, 1.584)

        monthly = fresh_db.get_monthly_totals(vehicle_id, months=12)
        by_period = {m["period"]: m for m in monthly}

        assert by_period["2026-06"]["total_cents"] == 11510
        assert by_period["2026-06"]["count"] == 2
        assert by_period["2026-07"]["total_cents"] == 6020
        assert by_period["2026-07"]["count"] == 1

    def test_yearly_totals(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2025-08-15", 5000)
        seed_fuel(fresh_db, vehicle_id, "2026-06-05", 5510)
        seed_fuel(fresh_db, vehicle_id, "2026-07-10", 6020)

        yearly = {y["year"]: y for y in fresh_db.get_yearly_totals(vehicle_id)}
        assert yearly["2025"]["total_cents"] == 5000
        assert yearly["2026"]["total_cents"] == 11530
        assert yearly["2026"]["count"] == 2

    def test_weekly_totals_sum_matches_seeded_amount(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2026-06-05", 5510)
        weekly = fresh_db.get_weekly_totals(vehicle_id, weeks=12)
        assert len(weekly) == 1
        assert weekly[0]["total_cents"] == 5510
        assert weekly[0]["period"].startswith("2026-W")

    def test_year_month_matrix_places_values_in_correct_month_slot(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2026-01-01", 1000)
        seed_fuel(fresh_db, vehicle_id, "2026-12-31", 2000)
        matrix = fresh_db.get_year_month_matrix(vehicle_id)
        assert matrix["2026"][0] == 1000  # January
        assert matrix["2026"][11] == 2000  # December
        assert all(v == 0 for v in matrix["2026"][1:11])

    def test_year_month_matrix_caps_at_max_years(self, fresh_db, vehicle_id):
        for year in ("2021", "2022", "2023", "2024", "2025"):
            seed_fuel(fresh_db, vehicle_id, f"{year}-01-01", 1000)
        matrix = fresh_db.get_year_month_matrix(vehicle_id, max_years=4)
        assert len(matrix) == 4
        assert "2021" not in matrix  # oldest year dropped
        assert "2025" in matrix

    def test_totals_scope_to_requested_vehicle_only(self, fresh_db):
        v1 = fresh_db.insert_vehicle("Car 1", None, None, None, None, None)
        v2 = fresh_db.insert_vehicle("Car 2", None, None, None, None, None)
        seed_fuel(fresh_db, v1, "2026-06-01", 1000)
        seed_fuel(fresh_db, v2, "2026-06-01", 2000)
        assert fresh_db.get_monthly_totals(v1)[0]["total_cents"] == 1000
        assert fresh_db.get_monthly_totals(v2)[0]["total_cents"] == 2000


class TestPriceTrendAndMaintenance:
    def test_price_trend_excludes_rows_without_price(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2026-06-01", 1000, price_per_unit=None)
        seed_fuel(fresh_db, vehicle_id, "2026-06-02", 1000, price_per_unit=1.5)
        trend = fresh_db.get_price_trend(vehicle_id)
        assert len(trend) == 1
        assert trend[0]["price_per_unit"] == 1.5

    def test_maintenance_by_category(self, fresh_db, vehicle_id):
        fresh_db.insert_maintenance_log(vehicle_id, None, "2026-01-01", 5000, None, "Shop", "Oil Change", None, None, None)
        fresh_db.insert_maintenance_log(vehicle_id, None, "2026-02-01", 3000, None, "Shop", "Oil Change", None, None, None)
        fresh_db.insert_maintenance_log(vehicle_id, None, "2026-03-01", 20000, None, "Shop", "Tires", None, None, None)

        by_category = {c["category"]: c for c in fresh_db.get_maintenance_by_category(vehicle_id)}
        assert by_category["Oil Change"]["total_cents"] == 8000
        assert by_category["Oil Change"]["count"] == 2
        assert by_category["Tires"]["total_cents"] == 20000


class TestCostPerKm:
    def test_cost_per_km_characterization_of_current_formula(self, fresh_db, vehicle_id):
        """Characterizes CURRENT behavior: (max odometer - min odometer across the
        vehicle's WHOLE history) divides (fuel + maintenance cost across the
        vehicle's WHOLE history) - not scoped to any reading window. This is a
        known simplification (a cost recorded before the first odometer reading,
        or after the last, still counts against the full-history distance). Phase
        7 replaces this with a properly windowed calculation and its own tests -
        this test's only job is to catch an ACCIDENTAL change to today's formula
        before that deliberate rework happens, not to endorse the formula itself.
        """
        fresh_db.insert_odometer_log(vehicle_id, "2026-01-01", 1000, None)
        fresh_db.insert_odometer_log(vehicle_id, "2026-06-01", 2000, None)
        seed_fuel(fresh_db, vehicle_id, "2026-03-01", 10000)  # $100, inside the window
        fresh_db.insert_maintenance_log(vehicle_id, None, "2026-04-01", 10000, None, "Shop", "Oil Change", None, None, None)

        # distance = 2000 - 1000 = 1000; cost = $100 + $100 = $200; $200 / 1000 = $0.20/unit
        assert fresh_db.get_cost_per_km(vehicle_id) == 0.2

    def test_cost_per_km_none_with_fewer_than_two_readings(self, fresh_db, vehicle_id):
        fresh_db.insert_odometer_log(vehicle_id, "2026-01-01", 1000, None)
        assert fresh_db.get_cost_per_km(vehicle_id) is None

    def test_cost_per_km_none_with_no_readings(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2026-01-01", 5000)
        assert fresh_db.get_cost_per_km(vehicle_id) is None

    def test_cost_per_km_none_when_readings_are_equal(self, fresh_db, vehicle_id):
        fresh_db.insert_odometer_log(vehicle_id, "2026-01-01", 1000, None)
        fresh_db.insert_odometer_log(vehicle_id, "2026-02-01", 1000, None)
        assert fresh_db.get_cost_per_km(vehicle_id) is None


class TestSummaryStats:
    def test_summary_stats_totals_and_average(self, fresh_db, vehicle_id):
        seed_fuel(fresh_db, vehicle_id, "2026-06-01", 5000)
        seed_fuel(fresh_db, vehicle_id, "2026-06-02", 7000)
        fresh_db.insert_maintenance_log(vehicle_id, None, "2026-06-03", 3000, None, "Shop", "Oil Change", None, None, None)

        stats = fresh_db.get_summary_stats(vehicle_id)
        assert stats["total_cents"] == 12000
        assert stats["count"] == 2
        assert stats["avg_cents"] == 6000
        assert stats["maintenance_total_cents"] == 3000

    def test_summary_stats_empty_vehicle(self, fresh_db, vehicle_id):
        stats = fresh_db.get_summary_stats(vehicle_id)
        assert stats["total_cents"] == 0
        assert stats["count"] == 0
        assert stats["cost_per_km"] is None


class TestPerVehicleSummary:
    def test_per_vehicle_summary_covers_every_vehicle(self, fresh_db):
        v1 = fresh_db.insert_vehicle("Car 1", None, None, None, None, None)
        v2 = fresh_db.insert_vehicle("Car 2", None, None, None, None, None)
        seed_fuel(fresh_db, v1, "2026-01-01", 5000)
        seed_fuel(fresh_db, v2, "2026-01-01", 7000)

        summary = {s["vehicle"]: s for s in fresh_db.get_per_vehicle_summary()}
        assert summary["Car 1"]["fuel_total_cents"] == 5000
        assert summary["Car 2"]["fuel_total_cents"] == 7000
