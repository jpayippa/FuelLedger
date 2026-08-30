import os

import cv2
import numpy as np
from PIL import Image

CROP_MARGIN_RATIO = float(os.environ.get("CROP_MARGIN_RATIO", "0.04"))
MAX_DESKEW_ANGLE = float(os.environ.get("MAX_DESKEW_ANGLE", "15"))


def _order_corners(pts):
    pts = pts.reshape(4, 2)
    ordered = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    ordered[0] = pts[np.argmin(s)]  # top-left
    ordered[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    ordered[1] = pts[np.argmin(diff)]  # top-right
    ordered[3] = pts[np.argmax(diff)]  # bottom-left
    return ordered


def _expand_corners(corners, image_shape, margin_ratio=CROP_MARGIN_RATIO):
    """Pushes each corner outward from the quad's centroid by margin_ratio,
    clipped to the source image bounds, so a slightly-too-tight detected
    boundary doesn't permanently crop off edge characters."""
    h, w = image_shape[:2]
    center = corners.mean(axis=0)
    expanded = center + (corners - center) * (1 + margin_ratio)
    expanded[:, 0] = np.clip(expanded[:, 0], 0, w - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, h - 1)
    return expanded.astype("float32")


def _warp(image_bgr, corners):
    (tl, tr, br, bl) = corners
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = max(int(width_a), int(width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = max(int(height_a), int(height_b))

    if max_width < 50 or max_height < 50:
        return None

    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(image_bgr, matrix, (max_width, max_height))


def find_receipt_corners(image_bgr):
    h, w = image_bgr.shape[:2]
    scale = 800 / max(h, w)
    small = cv2.resize(image_bgr, (int(w * scale), int(h * scale)))

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    small_area = small.shape[0] * small.shape[1]
    best = None
    best_area = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area < small_area * 0.2 or area <= best_area:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            best = approx
            best_area = area

    if best is None:
        return None

    return (best.reshape(4, 2).astype("float32")) / scale


def auto_crop(pil_image):
    """Detect a receipt's quadrilateral against its background and perspective-warp it flat,
    with a small margin so a slightly-too-tight boundary doesn't crop off edge characters.
    Falls back to the original image untouched if no confident quadrilateral is found.

    Returns (image, was_cropped) - was_cropped tells the caller whether the perspective
    warp actually ran (and therefore already corrected any skew), so a fallback deskew
    step knows whether it's still needed.
    """
    try:
        rgb = np.array(pil_image.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        corners = find_receipt_corners(bgr)
        if corners is None:
            return pil_image, False

        ordered = _order_corners(corners)
        expanded = _expand_corners(ordered, bgr.shape)
        warped = _warp(bgr, expanded)
        if warped is None:
            return pil_image, False

        warped_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
        return Image.fromarray(warped_rgb), True
    except Exception:
        return pil_image, False


def estimate_skew_angle(gray_pil_image):
    """Estimates the rotation (degrees) needed to deskew an image that didn't go
    through the perspective warp, via the minAreaRect of thresholded foreground
    pixels - the standard lightweight deskew heuristic. Returns 0.0 if no
    reasonable estimate can be made, or if the estimate exceeds MAX_DESKEW_ANGLE
    (which more likely indicates noise than a genuinely rotated photo)."""
    arr = np.array(gray_pil_image)
    thresh = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = cv2.findNonZero(thresh)
    if coords is None or len(coords) < 100:
        return 0.0

    # cv2.minAreaRect (this OpenCV version) returns an angle in [0, 90) for an
    # axis-ish-aligned box; empirically, a small positive rotation applied to
    # the source shows up as an angle just under 90, and a small negative
    # rotation shows up as an angle just above 0. Map both back into a small
    # signed correction (e.g. a raw 82 -> a small POSITIVE source rotation of
    # 8, so we correct by rotating -8; a raw 8 -> a small NEGATIVE source
    # rotation, corrected by rotating +8).
    angle = cv2.minAreaRect(coords)[-1]
    if angle > 45:
        angle -= 90
    return angle if abs(angle) <= MAX_DESKEW_ANGLE else 0.0


def deskew(gray_pil_image):
    """Rotates the image to correct small residual skew. A no-op (returns the
    same image) if the estimated angle is negligible."""
    angle = estimate_skew_angle(gray_pil_image)
    if abs(angle) < 0.5:
        return gray_pil_image
    return gray_pil_image.rotate(angle, expand=True, fillcolor=255)


def normalize_illumination(gray_pil_image):
    """Flat-field correction: divide by a heavily blurred copy of itself to cancel
    shadows/glare gradients from phone photos, then renormalize to full contrast."""
    arr = np.array(gray_pil_image).astype("float32")
    blurred = cv2.GaussianBlur(arr, (0, 0), sigmaX=arr.shape[1] / 15)
    blurred[blurred == 0] = 1
    normalized = arr / blurred
    normalized = normalized * 255 / normalized.max()
    normalized = np.clip(normalized, 0, 255).astype("uint8")
    return Image.fromarray(normalized)
