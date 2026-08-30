import io

import PIL.Image
import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

import uploads


def make_file_storage(pil_image, fmt="JPEG", **save_kwargs):
    buf = io.BytesIO()
    pil_image.save(buf, format=fmt, **save_kwargs)
    buf.seek(0)
    return FileStorage(stream=buf, filename=f"test.{fmt.lower()}", content_type=f"image/{fmt.lower()}")


def test_none_file_returns_none():
    assert uploads.load_validated_image(None) is None


def test_accepts_valid_jpeg():
    fs = make_file_storage(Image.new("RGB", (100, 80), "red"))
    result = uploads.load_validated_image(fs)
    assert result.size == (100, 80)


def test_accepts_valid_png():
    fs = make_file_storage(Image.new("RGB", (60, 40), "blue"), fmt="PNG")
    result = uploads.load_validated_image(fs)
    assert result.size == (60, 40)


def test_rejects_non_image_bytes():
    fs = FileStorage(stream=io.BytesIO(b"this is not an image"), filename="fake.jpg")
    with pytest.raises(uploads.ImageValidationError):
        uploads.load_validated_image(fs)


def test_rejects_disallowed_format():
    # BMP decodes fine in Pillow but isn't in our allowlist
    fs = make_file_storage(Image.new("RGB", (40, 40), "green"), fmt="BMP")
    with pytest.raises(uploads.ImageValidationError, match="Unsupported image format"):
        uploads.load_validated_image(fs)


def test_rejects_oversized_pixel_count(monkeypatch):
    # Patch Pillow's own threshold down so a tiny image trips the same
    # code path a real decompression bomb would, without building one.
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", 100)
    fs = make_file_storage(Image.new("RGB", (50, 50), "red"))  # 2500px > 100
    with pytest.raises(uploads.ImageValidationError, match="too large"):
        uploads.load_validated_image(fs)


def test_applies_exif_orientation():
    # A wide (100x50) image tagged as needing a 90-degree correction should
    # come back with swapped dimensions (tall 50x100) once corrected.
    img = Image.new("RGB", (100, 50), "red")
    exif = img.getexif()
    exif[274] = 6  # EXIF Orientation tag: rotate 90 CW to display correctly
    fs = make_file_storage(img, exif=exif)
    result = uploads.load_validated_image(fs)
    assert result.size == (50, 100)


def test_downsamples_oversized_dimension(monkeypatch):
    monkeypatch.setattr(uploads, "PREPROCESS_MAX_DIMENSION", 200)
    fs = make_file_storage(Image.new("RGB", (1000, 500), "red"))
    result = uploads.load_validated_image(fs)
    assert max(result.size) == 200
    assert result.size == (200, 100)  # aspect ratio preserved


def test_small_image_not_upscaled():
    fs = make_file_storage(Image.new("RGB", (100, 80), "red"))
    result = uploads.load_validated_image(fs)
    assert result.size == (100, 80)
