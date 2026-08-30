"""Fast, deterministic tests against ocr.py's pure text-extraction functions.
No Tesseract, no image decoding - see test_ocr_integration.py for the real-OCR
end-to-end tests. Several of these are regression tests for bugs found and
fixed against a real receipt photo during development (see git history for
`ocr.py` around the same dates as this file)."""

from datetime import date

import ocr


class TestExtractAmount:
    def test_keyworded_total_wins_high_confidence(self):
        assert ocr.extract_amount("TOTAL $31.94") == (31.94, "high")

    def test_no_keyword_picks_largest_low_confidence(self):
        assert ocr.extract_amount("SUBTOTAL $10.00\nMISC $5.00") == (10.00, "low")

    def test_no_candidates(self):
        assert ocr.extract_amount("THANK YOU") == (None, "none")

    def test_gallon_line_excluded_from_candidates(self):
        # regression: a $ figure on a line naming gallons/price-per-gallon must
        # never be picked up as the amount
        assert ocr.extract_amount("21.742 GAL\nTOTAL $43.75") == (43.75, "high")


class TestExtractDate:
    TODAY = date(2026, 8, 29)

    def test_single_format(self):
        assert ocr.extract_date("DATE: 08/15/2026", today=self.TODAY) == (date(2026, 8, 15), "high")

    def test_two_formats_agreeing_is_still_high_confidence(self):
        # regression: two different date formats on one receipt that parse to
        # the SAME date must not be marked low-confidence just because there
        # were two regex matches
        text = "2026-08-20\nDATE 20 Aug 2026"
        assert ocr.extract_date(text, today=self.TODAY) == (date(2026, 8, 20), "high")

    def test_future_date_rejected(self):
        assert ocr.extract_date("DATE: 08/15/2099", today=self.TODAY) == (None, "none")

    def test_too_old_date_rejected(self):
        assert ocr.extract_date("DATE: 08/15/2020", today=self.TODAY) == (None, "none")

    def test_no_candidates(self):
        assert ocr.extract_date("THANK YOU", today=self.TODAY) == (None, "none")


class TestExtractStation:
    def test_known_brand_high_confidence(self):
        assert ocr.extract_station("SHELL GAS STATION\n123 MAIN ST") == ("Shell", "high")

    def test_hyphenated_brand_survives_ocr_space_artifact(self):
        # regression: OCR sometimes inserts a space around a hyphen ("PETRO- CANADA")
        assert ocr.extract_station("PETRO- CANADA\n456 KING ST") == ("Petro-Canada", "high")

    def test_boilerplate_header_skipped_for_fallback(self):
        # regression: the fallback heuristic must not pick "Transaction Record"
        # (a generic receipt header) over the actual business name below it
        text = "TRANSACTION RECORD\nMORAVIAN STORE & GAS\n14787 SELTON LINE"
        assert ocr.extract_station(text) == ("Moravian Store & Gas", "low")

    def test_no_candidate_when_only_address_like_lines(self):
        text = "123 MAIN STREET\n555-1234\n1234567890"
        assert ocr.extract_station(text) == (None, "none")


class TestExtractVolumeAndUnit:
    def test_litres_with_price_on_same_line(self):
        # regression: must extract only the volume, not the trailing price-per-litre
        assert ocr.extract_volume_and_unit("21.742L AT $1.469/L") == (21.742, "L", "high")

    def test_gallons(self):
        assert ocr.extract_volume_and_unit("12.503 GAL") == (12.503, "gal", "high")

    def test_no_match(self):
        assert ocr.extract_volume_and_unit("TOTAL $31.94") == (None, None, "none")

    def test_multiple_candidates_low_confidence(self):
        value, unit, confidence = ocr.extract_volume_and_unit("12.503 GAL\n45.600 L")
        assert (value, unit) == (12.503, "gal")
        assert confidence == "low"


class TestExtractPricePerUnit:
    def test_keyworded_high_confidence(self):
        assert ocr.extract_price_per_unit("PRICE/GAL 3.499") == (3.499, "high")

    def test_substring_of_larger_number_not_matched(self):
        # regression: this exact line previously yielded 1.742 (a substring of
        # 21.742) instead of the real price-per-litre, 1.469
        assert ocr.extract_price_per_unit("21.742L AT $1.469/L") == (1.469, "low")

    def test_no_match(self):
        assert ocr.extract_price_per_unit("TOTAL $31.94") == (None, "none")


class TestExtractPaymentHint:
    def test_card_with_brand(self):
        assert ocr.extract_payment_hint("VISA ****1234") == {
            "method": "card", "card_last4": "1234", "brand": "Visa",
        }

    def test_terminal_id_not_mistaken_for_card_number(self):
        # regression: a garbled real receipt where the actual masked card number
        # OCR'd unreadably, but a TERMINAL id (also ****NNNN-shaped) appeared
        # earlier in the text - must not be reported as the card
        text = "TERMINAL: ****4723\nMASTERCARD\nBRRERER ERE EEO GQ]"
        assert ocr.extract_payment_hint(text) == {"method": None, "card_last4": None, "brand": None}

    def test_terminal_excluded_but_real_card_still_found(self):
        text = "TERMINAL: ****9999\nTOTAL $45.00\nVISA ****1234\nAPPROVED"
        assert ocr.extract_payment_hint(text) == {
            "method": "card", "card_last4": "1234", "brand": "Visa",
        }

    def test_cash_tender_detected(self):
        assert ocr.extract_payment_hint("TENDER: CASH") == {
            "method": "cash", "card_last4": None, "brand": None,
        }

    def test_cash_price_not_mistaken_for_cash_tender(self):
        # regression: US-style dual pricing ("cash price" vs "credit price")
        # must not be read as "the customer paid cash"
        text = "CASH PRICE $3.29\nCREDIT PRICE $3.49"
        assert ocr.extract_payment_hint(text) == {"method": None, "card_last4": None, "brand": None}

    def test_no_payment_info(self):
        assert ocr.extract_payment_hint("THANK YOU") == {"method": None, "card_last4": None, "brand": None}
