from datetime import datetime
import logging
import os
from pathlib import Path

from werkzeug.utils import secure_filename

from config import BASE_DIR, UPLOAD_FOLDER

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - Pillow is installed in production.
    Image = None
    ImageOps = None
    UnidentifiedImageError = OSError

STATIC_UPLOAD_FOLDER = (BASE_DIR / "static" / "uploads").resolve()
logger = logging.getLogger(__name__)

COMPRESS_UPLOAD_IMAGES = os.environ.get("COMPRESS_UPLOAD_IMAGES", "1") != "0"
UPLOAD_IMAGE_MAX_DIMENSION = max(480, int(os.environ.get("UPLOAD_IMAGE_MAX_DIMENSION", "1600")))
UPLOAD_IMAGE_JPEG_QUALITY = min(95, max(50, int(os.environ.get("UPLOAD_IMAGE_JPEG_QUALITY", "82"))))


def _jpg_path_for(filepath):
    return filepath.with_suffix(".jpg")


def _image_to_rgb(image):
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.convert("RGBA").getchannel("A")
        background.paste(image.convert("RGBA"), mask=alpha)
        return background
    return image.convert("RGB") if image.mode != "RGB" else image


def compress_uploaded_image(filepath):
    if not COMPRESS_UPLOAD_IMAGES or Image is None:
        return filepath

    original_size = filepath.stat().st_size if filepath.exists() else 0
    output_path = _jpg_path_for(filepath)
    temp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")

    try:
        with Image.open(filepath) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((UPLOAD_IMAGE_MAX_DIMENSION, UPLOAD_IMAGE_MAX_DIMENSION), Image.Resampling.LANCZOS)
            image = _image_to_rgb(image)
            image.save(
                temp_path,
                "JPEG",
                quality=UPLOAD_IMAGE_JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )

        compressed_size = temp_path.stat().st_size
        resized = filepath.suffix.lower() != ".jpg" and filepath.suffix.lower() != ".jpeg"
        if original_size and compressed_size >= original_size and not resized:
            temp_path.unlink(missing_ok=True)
            return filepath

        if output_path != filepath:
            filepath.unlink(missing_ok=True)
        temp_path.replace(output_path)
        logger.info(
            "compressed_upload path=%s original_kb=%.1f compressed_kb=%.1f",
            output_path.name,
            original_size / 1024 if original_size else 0,
            compressed_size / 1024,
        )
        return output_path
    except (OSError, UnidentifiedImageError, ValueError) as error:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        logger.info("compress_upload_skipped path=%s reason=%s", filepath.name, type(error).__name__)
        return filepath


def store_uploaded_file(file, prefix=""):
    safe_name = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    name_prefix = f"{prefix}_" if prefix else ""
    filename = f"{name_prefix}{timestamp}_{safe_name}" if safe_name else f"{name_prefix}{timestamp}.jpg"
    filepath = UPLOAD_FOLDER / filename
    try:
        file.save(filepath)
    finally:
        close = getattr(file, "close", None)
        if callable(close):
            close()
    filepath = compress_uploaded_image(filepath)
    filename = filepath.name
    url_prefix = "/static/uploads" if UPLOAD_FOLDER.resolve() == STATIC_UPLOAD_FOLDER else "/uploads"
    return filepath, f"{url_prefix}/{filename}"


def upload_path_from_url(image_url):
    if image_url.startswith("/uploads/"):
        return (UPLOAD_FOLDER / Path(image_url).name).resolve()
    if image_url.startswith("/static/uploads/"):
        return (BASE_DIR / image_url.lstrip("/").replace("/", os.sep)).resolve()
    return None


def remove_upload_file_if_unused(image_url, still_used=False):
    if still_used or not image_url:
        return False

    upload_path = upload_path_from_url(image_url)
    if upload_path is None:
        return False

    try:
        if upload_path.parent in {UPLOAD_FOLDER.resolve(), STATIC_UPLOAD_FOLDER}:
            upload_path.unlink(missing_ok=True)
            return True
    except OSError:
        return False
    return False
