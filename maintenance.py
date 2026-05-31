import argparse
from pathlib import Path

from config import BASE_DIR, DATABASE_PATH, UPLOAD_FOLDER
from db import get_db_connection


def byte_label(size):
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def upload_files():
    if not UPLOAD_FOLDER.exists():
        return []
    return [path for path in UPLOAD_FOLDER.iterdir() if path.is_file()]


def used_upload_names():
    if not DATABASE_PATH.exists():
        return set()

    with get_db_connection() as conn:
        post_urls = conn.execute("SELECT image_url FROM posts").fetchall()
        avatar_urls = conn.execute("SELECT avatar_url FROM users").fetchall()

    names = set()
    for row in [*post_urls, *avatar_urls]:
        value = row[0] or ""
        if value.startswith("/static/uploads/"):
            names.add(Path(value).name)
    return names


def report_uploads(delete_orphans=False):
    files = upload_files()
    used_names = used_upload_names()
    orphan_files = [path for path in files if path.name not in used_names]

    print(f"uploads: {len(files)} files, {byte_label(sum(path.stat().st_size for path in files))}")
    print(f"referenced: {len(used_names)} names")
    print(f"orphans: {len(orphan_files)} files, {byte_label(sum(path.stat().st_size for path in orphan_files))}")

    for path in orphan_files[:20]:
        print(f"  orphan: {path.name} ({byte_label(path.stat().st_size)})")
    if len(orphan_files) > 20:
        print(f"  ... and {len(orphan_files) - 20} more")

    if delete_orphans:
        for path in orphan_files:
            path.unlink(missing_ok=True)
        print(f"deleted {len(orphan_files)} orphan upload files")


def report_logs():
    logs = sorted(BASE_DIR.glob("*.log"))
    print(f"logs: {len(logs)} files")
    for path in logs:
        print(f"  {path.name}: {byte_label(path.stat().st_size)}")


def main():
    parser = argparse.ArgumentParser(description="Inspect project storage and optionally remove orphan uploads.")
    parser.add_argument("--delete-orphans", action="store_true", help="Delete upload files not referenced by posts or users.")
    args = parser.parse_args()

    report_logs()
    report_uploads(delete_orphans=args.delete_orphans)


if __name__ == "__main__":
    main()
