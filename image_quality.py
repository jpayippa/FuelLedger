import os

import cv2
import numpy as np

BLUR_VARIANCE_THRESHOLD = float(os.environ.get("BLUR_VARIANCE_THRESHOLD", "80"))
DARK_MEAN_THRESHOLD = float(os.environ.get("DARK_MEAN_THRESHOLD", "60"))
# Deliberately high: once cropped tight to just the receipt, the image is
# dominated by the paper itself, which is legitimately very bright even in a
# correctly-exposed photo (measured ~230-235 mean for a normal synthetic test
# photo cropped to the receipt). A lower threshold would flag nearly every
# receipt as "overexposed" and train users to ignore the warning.
BRIGHT_MEAN_THRESHOLD = float(os.environ.get("BRIGHT_MEAN_THRESHOLD", "245"))


def assess_quality(gray_pil_image, was_cropped):
    """Returns a list of short, human-readable warnings about the photo's
    suitability for OCR. Empty list means no concerns - a normal photo never
    shows a warning. `gray_pil_image` should be assessed before any deliberate
    smoothing (denoise/median filter), since that would artificially trip the
    blur check."""
    arr = np.array(gray_pil_image)
    warnings = []

    if cv2.Laplacian(arr, cv2.CV_64F).var() < BLUR_VARIANCE_THRESHOLD:
        warnings.append("Photo appears blurry - try holding the camera steady and retaking it.")

    mean_brightness = arr.astype("float32").mean()
    if mean_brightness < DARK_MEAN_THRESHOLD:
        warnings.append("Photo appears very dark - try retaking it with more light.")
    elif mean_brightness > BRIGHT_MEAN_THRESHOLD:
        warnings.append("Photo appears overexposed - try reducing glare or bright light.")

    if not was_cropped:
        warnings.append(
            "Couldn't automatically detect the receipt's edges - if part of it was cut off, "
            "try retaking with some background visible around it."
        )

    return warnings
