from datetime import date, timedelta

import pytest

import app as flask_app_module

cents_from_amount = flask_app_module.cents_from_amount
validate_date = flask_app_module.validate_date
optional_float = flask_app_module.optional_float
optional_int = flask_app_module.optional_int


class TestCentsFromAmount:
    def test_normal_amount(self):
        assert cents_from_amount("31.94") == 3194

    def test_rounds_to_nearest_cent(self):
        assert cents_from_amount("10.005") == 1001  # banker's/float rounding, documented as-is

    def test_zero_rejected(self):
        with pytest.raises(ValueError):
            cents_from_amount("0")

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            cents_from_amount("-5.00")

    def test_over_default_max_rejected(self):
        with pytest.raises(ValueError):
            cents_from_amount("1000.00")

    def test_custom_max_allows_larger_amount(self):
        assert cents_from_amount("5000.00", max_amount=99999.99) == 500000

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            cents_from_amount("abc")


class TestValidateDate:
    def test_valid_past_date(self):
        assert validate_date("2026-01-01") == "2026-01-01"

    def test_today_is_valid(self):
        today_str = date.today().isoformat()
        assert validate_date(today_str) == today_str

    def test_future_date_rejected(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        with pytest.raises(ValueError):
            validate_date(future)

    def test_malformed_date_rejected(self):
        with pytest.raises(ValueError):
            validate_date("not-a-date")

    def test_wrong_format_rejected(self):
        with pytest.raises(ValueError):
            validate_date("01/01/2026")


class TestOptionalFloat:
    def test_none_returns_none(self):
        assert optional_float(None) is None

    def test_empty_string_returns_none(self):
        assert optional_float("") is None

    def test_valid_value(self):
        assert optional_float("12.5") == 12.5

    def test_out_of_range_returns_none(self):
        assert optional_float("-1", min_val=0, max_val=100) is None
        assert optional_float("101", min_val=0, max_val=100) is None


class TestOptionalInt:
    def test_none_returns_none(self):
        assert optional_int(None) is None

    def test_empty_string_returns_none(self):
        assert optional_int("") is None

    def test_valid_value(self):
        assert optional_int("42") == 42

    def test_non_numeric_returns_none(self):
        assert optional_int("abc") is None
