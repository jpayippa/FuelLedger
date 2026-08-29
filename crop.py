import cv2
import numpy as np
from PIL import Image


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
    """Detect a receipt's quadrilateral against its background and perspective-warp it flat.
    Falls back to the original image untouched if no confident quadrilateral is found.
    """
    try:
        rgb = np.array(pil_image.convert("RGB"))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        corners = find_receipt_corners(bgr)
        if corners is None:
            return pil_image

        ordered = _order_corners(corners)
        warped = _warp(bgr, ordered)
        if warped is None:
            return pil_image

        warped_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
        return Image.fromarray(warped_rgb)
    except Exception:
        return pil_image


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
