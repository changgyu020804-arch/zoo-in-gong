import argparse
from pathlib import Path

from config import BASE_DIR, DATABASE_PATH, UPLOAD_FOLDER
from db import get_db_connection
from upload_utils import remove_upload_file_if_unused


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


def upload_still_used(conn, image_url):
    if not image_url:
        return False
    post_row = conn.execute("SELECT 1 FROM posts WHERE image_url = ? LIMIT 1", (image_url,)).fetchone()
    avatar_row = conn.execute("SELECT 1 FROM users WHERE avatar_url = ? LIMIT 1", (image_url,)).fetchone()
    return bool(post_row or avatar_row)


def delete_user(username, confirm=False):
    if not username:
        raise ValueError("username is required")

    with get_db_connection() as conn:
        user = conn.execute("SELECT username, pet_name, avatar_url FROM users WHERE username = ?", (username,)).fetchone()
        post_rows = conn.execute("SELECT id, image_url FROM posts WHERE username = ? ORDER BY id", (username,)).fetchall()
        post_ids = [row["id"] for row in post_rows]
        upload_urls = [row["image_url"] for row in post_rows if row["image_url"]]
        if user and user["avatar_url"]:
            upload_urls.append(user["avatar_url"])

        counts = {
            "user": 1 if user else 0,
            "posts": len(post_ids),
            "comments_by_user": conn.execute("SELECT COUNT(*) FROM comments WHERE username = ?", (username,)).fetchone()[0],
            "likes_by_user": conn.execute("SELECT COUNT(*) FROM post_likes WHERE username = ?", (username,)).fetchone()[0],
            "reactions_by_user": conn.execute(
                "SELECT COUNT(*) FROM post_reactions WHERE username = ?",
                (username,),
            ).fetchone()[0],
            "bookmarks_by_user": conn.execute("SELECT COUNT(*) FROM post_bookmarks WHERE username = ?", (username,)).fetchone()[0],
            "follows": conn.execute(
                "SELECT COUNT(*) FROM follows WHERE follower_username = ? OR followed_username = ?",
                (username, username),
            ).fetchone()[0],
            "messages": conn.execute(
                "SELECT COUNT(*) FROM messages WHERE sender_username = ? OR receiver_username = ?",
                (username, username),
            ).fetchone()[0],
            "notifications": conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE recipient_username = ? OR actor_username = ?",
                (username, username),
            ).fetchone()[0],
            "upload_urls": len(set(upload_urls)),
        }
        if post_ids:
            placeholders = ",".join("?" for _ in post_ids)
            counts["comments_on_posts"] = conn.execute(
                f"SELECT COUNT(*) FROM comments WHERE post_id IN ({placeholders})",
                post_ids,
            ).fetchone()[0]
            counts["likes_on_posts"] = conn.execute(
                f"SELECT COUNT(*) FROM post_likes WHERE post_id IN ({placeholders})",
                post_ids,
            ).fetchone()[0]
            counts["reactions_on_posts"] = conn.execute(
                f"SELECT COUNT(*) FROM post_reactions WHERE post_id IN ({placeholders})",
                post_ids,
            ).fetchone()[0]
            counts["bookmarks_on_posts"] = conn.execute(
                f"SELECT COUNT(*) FROM post_bookmarks WHERE post_id IN ({placeholders})",
                post_ids,
            ).fetchone()[0]
        else:
            counts["comments_on_posts"] = 0
            counts["likes_on_posts"] = 0
            counts["reactions_on_posts"] = 0
            counts["bookmarks_on_posts"] = 0

        print(f"target username: {username}")
        if user:
            print(f"target pet: {user['pet_name'] or '(empty)'}")
        for key, value in counts.items():
            print(f"{key}: {value}")

        if not confirm:
            print("dry run only. Add --confirm to delete this account and related data.")
            return

        if post_ids:
            placeholders = ",".join("?" for _ in post_ids)
            conn.execute(f"DELETE FROM comments WHERE post_id IN ({placeholders})", post_ids)
            conn.execute(f"DELETE FROM post_likes WHERE post_id IN ({placeholders})", post_ids)
            conn.execute(f"DELETE FROM post_reactions WHERE post_id IN ({placeholders})", post_ids)
            conn.execute(f"DELETE FROM post_bookmarks WHERE post_id IN ({placeholders})", post_ids)

        conn.execute("DELETE FROM comments WHERE username = ?", (username,))
        conn.execute("DELETE FROM post_likes WHERE username = ?", (username,))
        conn.execute("DELETE FROM post_reactions WHERE username = ?", (username,))
        conn.execute("DELETE FROM post_bookmarks WHERE username = ?", (username,))
        conn.execute("DELETE FROM follows WHERE follower_username = ? OR followed_username = ?", (username, username))
        conn.execute("DELETE FROM messages WHERE sender_username = ? OR receiver_username = ?", (username, username))
        conn.execute("DELETE FROM notifications WHERE recipient_username = ? OR actor_username = ?", (username, username))
        conn.execute("DELETE FROM posts WHERE username = ?", (username,))
        conn.execute("DELETE FROM users WHERE username = ?", (username,))

        removable_urls = []
        for url in dict.fromkeys(upload_urls):
            if not upload_still_used(conn, url):
                removable_urls.append(url)

    deleted_files = 0
    for url in removable_urls:
        if remove_upload_file_if_unused(url):
            deleted_files += 1

    print(f"deleted account data for {username}")
    print(f"deleted upload files: {deleted_files}")


def main():
    parser = argparse.ArgumentParser(description="Inspect project storage and optionally remove orphan uploads.")
    parser.add_argument("--delete-orphans", action="store_true", help="Delete upload files not referenced by posts or users.")
    parser.add_argument("--delete-user", help="Delete one user and all related posts, social data, messages, notifications, and uploads.")
    parser.add_argument("--confirm", action="store_true", help="Actually perform destructive maintenance actions.")
    args = parser.parse_args()

    if args.delete_user:
        delete_user(args.delete_user, confirm=args.confirm)
        return

    report_logs()
    report_uploads(delete_orphans=args.delete_orphans)


if __name__ == "__main__":
    main()
