import numpy as np
from PIL import Image

import ocr


def _gray_image_with_text_like_noise():
    # A grayscale image with enough contrast/structure for Otsu to produce a
    # meaningful (non-trivial) threshold split.
    arr = np.zeros((200, 200), dtype="uint8")
    arr[:, :] = 255
    arr[50:150, 20:180] = 0
    return Image.fromarray(arr)


class TestGeneratePreprocessingVariants:
    def test_returns_normalized_adaptive_and_otsu_by_default(self):
        variants = ocr.generate_preprocessing_variants(_gray_image_with_text_like_noise())
        assert set(variants) >= {"normalized", "adaptive", "otsu"}

    def test_inverted_added_only_when_otsu_result_is_majority_black(self):
        # Mostly-black foreground on a small white patch - Otsu result should
        # come out majority black, triggering the inverted variant.
        arr = np.zeros((200, 200), dtype="uint8")
        arr[80:120, 80:120] = 255  # a small white square on an otherwise black image
        mostly_black_source = Image.fromarray(arr)
        variants = ocr.generate_preprocessing_variants(mostly_black_source)
        assert "inverted" in variants

    def test_inverted_absent_for_normal_receipt_style_image(self):
        # Mostly white background with a bit of black text/content - the
        # normal case - should NOT trigger the inverted variant.
        arr = np.full((200, 200), 255, dtype="uint8")
        arr[80:120, 80:120] = 0
        variants = ocr.generate_preprocessing_variants(Image.fromarray(arr))
        assert "inverted" not in variants

    def test_all_variants_are_same_size_as_input(self):
        source = _gray_image_with_text_like_noise()
        variants = ocr.generate_preprocessing_variants(source)
        for name, img in variants.items():
            assert img.size == source.size, f"{name} changed size"
