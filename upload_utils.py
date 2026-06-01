from datetime import datetime
import os
from pathlib import Path

from werkzeug.utils import secure_filename

from config import BASE_DIR, UPLOAD_FOLDER

STATIC_UPLOAD_FOLDER = (BASE_DIR / "static" / "uploads").resolve()


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
