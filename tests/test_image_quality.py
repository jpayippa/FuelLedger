from PIL import Image, ImageDraw

import image_quality
from tests.ocr_fixtures import CLEAN_FUEL_RECEIPT, _font, make_blurry, make_dark, make_overexposed, make_synthetic_receipt


def _sharp_gray():
    return make_synthetic_receipt(CLEAN_FUEL_RECEIPT).convert("L")


def _moderate_brightness_gray():
    # make_synthetic_receipt's plain white (255) background is legitimately
    # very bright even before any "overexposure" is applied (measured mean
    # ~248/255) - fine for OCR-accuracy tests, but not a fair baseline for
    # "a normal, correctly-exposed photo produces no quality warnings". This
    # uses a moderate gray background instead, in the range a real cropped
    # receipt photo actually measures at.
    img = Image.new("L", (600, 800), color=190)
    draw = ImageDraw.Draw(img)
    font = _font(24)
    y = 30
    for line in CLEAN_FUEL_RECEIPT:
        draw.text((30, y), line, fill=10, font=font)
        y += 36
    return img


class TestAssessQuality:
    def test_clean_sharp_cropped_image_has_no_warnings(self):
        warnings = image_quality.assess_quality(_moderate_brightness_gray(), was_cropped=True)
        assert warnings == []

    def test_blurry_image_flagged(self):
        blurry = make_blurry(make_synthetic_receipt(CLEAN_FUEL_RECEIPT), radius=8).convert("L")
        warnings = image_quality.assess_quality(blurry, was_cropped=True)
        assert any("blurry" in w.lower() for w in warnings)

    def test_dark_image_flagged(self):
        dark = make_dark(make_synthetic_receipt(CLEAN_FUEL_RECEIPT), factor=0.15).convert("L")
        warnings = image_quality.assess_quality(dark, was_cropped=True)
        assert any("dark" in w.lower() for w in warnings)

    def test_overexposed_image_flagged(self):
        bright = make_overexposed(make_synthetic_receipt(CLEAN_FUEL_RECEIPT), factor=3.0, offset=150).convert("L")
        warnings = image_quality.assess_quality(bright, was_cropped=True)
        assert any("overexposed" in w.lower() for w in warnings)

    def test_uncropped_image_flagged(self):
        warnings = image_quality.assess_quality(_sharp_gray(), was_cropped=False)
        assert any("edges" in w.lower() for w in warnings)

    def test_cropped_clean_image_has_no_boundary_warning(self):
        warnings = image_quality.assess_quality(_moderate_brightness_gray(), was_cropped=True)
        assert not any("edges" in w.lower() for w in warnings)

    def test_multiple_problems_all_reported(self):
        dark_and_blurry = make_blurry(
            make_dark(make_synthetic_receipt(CLEAN_FUEL_RECEIPT), factor=0.15), radius=8
        ).convert("L")
        warnings = image_quality.assess_quality(dark_and_blurry, was_cropped=False)
        assert len(warnings) >= 3  # dark, blurry, and boundary-not-detected
