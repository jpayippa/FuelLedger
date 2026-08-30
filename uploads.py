import os
import warnings

from PIL import Image, ImageOps

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "15"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_IMAGE_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", "40000000"))  # ~40 megapixels
PREPROCESS_MAX_DIMENSION = int(os.environ.get("PREPROCESS_MAX_DIMENSION", "3000"))
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Process-wide Pillow settings: turn the "maybe a decompression bomb" warning
# band (1x-2x MAX_IMAGE_PIXELS) into a hard rejection at exactly our
# configured threshold, instead of silently decoding an oversized image.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
warnings.filterwarnings("error", category=Image.DecompressionBombWarning)


class ImageValidationError(Exception):
    pass


def load_validated_image(file_storage):
    """Opens, decodes, and validates an uploaded image. Returns an
    EXIF-corrected, size-capped PIL Image, or None if no file was given.
    Raises ImageValidationError with a user-facing message on any problem -
    never silently swallowed.
    """
    if not file_storage:
        return None

    try:
        image = Image.open(file_storage.stream)
        image.load()
    except Image.DecompressionBombError:
        raise ImageValidationError("Image is too large (exceeds the maximum pixel dimensions).")
    except Warning:
        raise ImageValidationError("Image is too large (exceeds the maximum pixel dimensions).")
    except Exception:
        raise ImageValidationError("Could not read that image file.")

    if image.format not in ALLOWED_FORMATS:
        raise ImageValidationError(
            f"Unsupported image format ({image.format or 'unknown'}). Use JPEG, PNG, or WEBP."
        )

    image = ImageOps.exif_transpose(image)

    w, h = image.size
    max_dim = max(w, h)
    if max_dim > PREPROCESS_MAX_DIMENSION:
        scale = PREPROCESS_MAX_DIMENSION / max_dim
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    return image
