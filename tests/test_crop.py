import numpy as np
from PIL import Image, ImageDraw

import crop
from tests.ocr_fixtures import _font


def _make_text_image():
    img = Image.new("L", (600, 800), color=255)
    d = ImageDraw.Draw(img)
    font = _font(24)
    lines = ["SHELL GAS STATION", "123 MAIN ST", "", "DATE: 08/15/2026", "TOTAL  $43.75", "THANK YOU"]
    y = 30
    for line in lines:
        d.text((30, y), line, fill=0, font=font)
        y += 36
    return img


class TestExpandCorners:
    def test_moves_corners_away_from_center(self):
        corners = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype="float32")
        expanded = crop._expand_corners(corners, image_shape=(200, 200), margin_ratio=0.1)
        center = corners.mean(axis=0)
        for orig, exp in zip(corners, expanded):
            assert np.linalg.norm(exp - center) > np.linalg.norm(orig - center)

    def test_clips_to_image_bounds(self):
        corners = np.array([[5, 5], [95, 5], [95, 95], [5, 95]], dtype="float32")
        expanded = crop._expand_corners(corners, image_shape=(100, 100), margin_ratio=0.5)
        assert expanded[:, 0].min() >= 0
        assert expanded[:, 1].min() >= 0
        assert expanded[:, 0].max() <= 99
        assert expanded[:, 1].max() <= 99

    def test_zero_margin_is_a_no_op(self):
        corners = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype="float32")
        expanded = crop._expand_corners(corners, image_shape=(200, 200), margin_ratio=0.0)
        assert np.allclose(expanded, corners)


class TestDeskew:
    def test_estimates_positive_rotation_as_negative_correction(self):
        img = _make_text_image().rotate(8, expand=True, fillcolor=255)
        angle = crop.estimate_skew_angle(img)
        assert -9 < angle < -7

    def test_estimates_negative_rotation_as_positive_correction(self):
        img = _make_text_image().rotate(-8, expand=True, fillcolor=255)
        angle = crop.estimate_skew_angle(img)
        assert 7 < angle < 9

    def test_unrotated_image_needs_no_correction(self):
        angle = crop.estimate_skew_angle(_make_text_image())
        assert abs(angle) < 1

    def test_deskew_corrects_rotated_image(self):
        img = _make_text_image().rotate(8, expand=True, fillcolor=255)
        corrected = crop.deskew(img)
        residual = crop.estimate_skew_angle(corrected)
        assert abs(residual) < 1

    def test_deskew_is_a_noop_below_half_a_degree(self):
        img = _make_text_image()
        result = crop.deskew(img)
        assert result is img

    def test_large_rotation_is_not_corrected(self):
        # beyond MAX_DESKEW_ANGLE (15 deg) - more likely a real orientation
        # difference than ordinary phone-tilt skew, so left alone
        img = _make_text_image().rotate(30, expand=True, fillcolor=255)
        angle = crop.estimate_skew_angle(img)
        assert angle == 0.0

    def test_blank_image_returns_zero(self):
        blank = Image.new("L", (200, 200), color=255)
        assert crop.estimate_skew_angle(blank) == 0.0


class TestAutoCropReturnsCroppedFlag:
    def test_no_quad_found_returns_false(self):
        # A plain image with no contrasting boundary - no quad to detect
        plain = Image.new("RGB", (400, 400), color=255)
        image, was_cropped = crop.auto_crop(plain)
        assert was_cropped is False
        assert image.size == plain.size
