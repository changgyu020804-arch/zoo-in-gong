from datetime import datetime
from contextlib import contextmanager
import re
import sqlite3
from zoneinfo import ZoneInfo

from config import DATABASE_PATH


PROFILE_COLUMNS = [
    ("phone_number", "TEXT DEFAULT ''"),
    ("avatar_url", "TEXT DEFAULT ''"),
    ("bio", "TEXT DEFAULT ''"),
    ("status_message", "TEXT DEFAULT ''"),
    ("favorite_place", "TEXT DEFAULT ''"),
    ("personality", "TEXT DEFAULT ''"),
    ("owner_persona_note", "TEXT DEFAULT ''"),
    ("persona_energy", "TEXT DEFAULT 'outdoor'"),
    ("persona_social", "TEXT DEFAULT 'social'"),
    ("persona_curiosity", "TEXT DEFAULT 'explorer'"),
    ("persona_expression", "TEXT DEFAULT 'affectionate'"),
    ("persona_focus", "TEXT DEFAULT 'snack'"),
    ("persona_reaction", "TEXT DEFAULT 'brave'"),
    ("persona_routine", "TEXT DEFAULT 'routine'"),
    ("persona_voice", "TEXT DEFAULT 'chatty'"),
    ("persona_cuddle", "TEXT DEFAULT 'cuddly'"),
    ("persona_style", "TEXT DEFAULT 'flashy'"),
]

POST_COLUMNS = [
    ("activity_text", "TEXT DEFAULT ''"),
    ("created_at", "TEXT DEFAULT ''"),
    ("caption_status", "TEXT DEFAULT 'ready'"),
    ("taken_on", "TEXT DEFAULT ''"),
    ("weight_kg", "REAL"),
    ("growth_milestone", "TEXT DEFAULT ''"),
    ("pet_age_at_post", "INTEGER"),
]

MESSAGE_COLUMNS = [
    ("read_at", "TEXT DEFAULT ''"),
]

COMMENT_COLUMNS = [
    ("username", "TEXT DEFAULT ''"),
    ("created_at", "TEXT DEFAULT ''"),
]



@contextmanager
def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_columns(cursor, table_name, columns):
    existing_columns = {
        row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, definition in columns:
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def timestamp_from_upload_url(image_url):
    match = re.search(r"(\d{14})_", image_url or "")
    if not match:
        return ""

    try:
        local_time = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except ValueError:
        return ""
    return local_time.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                pet_name TEXT,
                pet_species TEXT,
                pet_age INTEGER,
                persona TEXT,
                activity_level TEXT,
                pet_likes TEXT,
                pet_dislikes TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS posts
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url TEXT,
                caption TEXT,
                likes INTEGER DEFAULT 0,
                username TEXT,
                activity_text TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS comments
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                content TEXT,
                username TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(post_id) REFERENCES posts(id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS follows
            (
                follower_username TEXT NOT NULL,
                followed_username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (follower_username, followed_username)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_username TEXT NOT NULL,
                receiver_username TEXT NOT NULL,
                body TEXT NOT NULL,
                read_at TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_username) REFERENCES users(username),
                FOREIGN KEY(receiver_username) REFERENCES users(username)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_pair_created
            ON messages(sender_username, receiver_username, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_receiver_read
            ON messages(receiver_username, read_at, sender_username)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS post_likes
            (
                post_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (post_id, username),
                FOREIGN KEY(post_id) REFERENCES posts(id),
                FOREIGN KEY(username) REFERENCES users(username)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS post_bookmarks
            (
                post_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (post_id, username),
                FOREIGN KEY(post_id) REFERENCES posts(id),
                FOREIGN KEY(username) REFERENCES users(username)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_post_bookmarks_username
            ON post_bookmarks(username, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_posts_username_created
            ON posts(username, created_at, id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_posts_created
            ON posts(created_at, id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_comments_post_id
            ON comments(post_id, id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_follows_follower_created
            ON follows(follower_username, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_post_likes_username
            ON post_likes(username, post_id)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_username TEXT NOT NULL,
                actor_username TEXT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                link TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(recipient_username) REFERENCES users(username),
                FOREIGN KEY(actor_username) REFERENCES users(username)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notifications_recipient_created
            ON notifications(recipient_username, created_at, id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread
            ON notifications(recipient_username, is_read)
            """
        )

        ensure_columns(cursor, "users", PROFILE_COLUMNS)
        ensure_columns(cursor, "posts", POST_COLUMNS)
        ensure_columns(cursor, "messages", MESSAGE_COLUMNS)
        ensure_columns(cursor, "comments", COMMENT_COLUMNS)
        posts_without_created_at = cursor.execute(
            """
            SELECT id, image_url
            FROM posts
            WHERE created_at IS NULL OR created_at = ''
            """
        ).fetchall()
        for row in posts_without_created_at:
            upload_time = timestamp_from_upload_url(row["image_url"])
            if upload_time:
                cursor.execute(
                    "UPDATE posts SET created_at = ? WHERE id = ?",
                    (upload_time, row["id"]),
                )
        cursor.execute(
            """
            UPDATE posts
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL OR created_at = ''
            """
        )
        cursor.execute(
            """
            UPDATE comments
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL OR created_at = ''
            """
        )
        cursor.execute(
            """
            UPDATE posts
            SET caption_status = 'ready'
            WHERE caption_status IS NULL OR caption_status = ''
            """
        )
