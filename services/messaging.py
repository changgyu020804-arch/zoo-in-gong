from datetime import datetime, timezone

from db import get_db_connection
from persona import row_to_profile


def get_message_partner_usernames(conn, username):
    rows = conn.execute(
        """
        SELECT followed_username AS username
        FROM follows
        WHERE follower_username = ?
        UNION
        SELECT sender_username AS username
        FROM messages
        WHERE receiver_username = ?
        UNION
        SELECT receiver_username AS username
        FROM messages
        WHERE sender_username = ?
        """,
        (username, username, username),
    ).fetchall()
    return [row["username"] for row in rows if row["username"] != username]


def can_message_user(conn, sender_username, receiver_username):
    if not sender_username or not receiver_username or sender_username == receiver_username:
        return False

    target = conn.execute(
        "SELECT username FROM users WHERE username = ?",
        (receiver_username,),
    ).fetchone()
    if not target:
        return False

    allowed = conn.execute(
        """
        SELECT 1
        FROM follows
        WHERE follower_username = ? AND followed_username = ?
        """,
        (sender_username, receiver_username),
    ).fetchone()
    if allowed:
        return True

    existing_thread = conn.execute(
        """
        SELECT 1
        FROM messages
        WHERE (sender_username = ? AND receiver_username = ?)
           OR (sender_username = ? AND receiver_username = ?)
        LIMIT 1
        """,
        (sender_username, receiver_username, receiver_username, sender_username),
    ).fetchone()
    return existing_thread is not None


def get_unread_message_count(username):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM messages
            WHERE receiver_username = ?
              AND (read_at IS NULL OR read_at = '')
            """,
            (username,),
        ).fetchone()
    return row["count"] if row else 0


def mark_messages_read(conn, username, partner_username=None):
    params = [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), username]
    query = """
        UPDATE messages
        SET read_at = ?
        WHERE receiver_username = ?
          AND (read_at IS NULL OR read_at = '')
    """
    if partner_username:
        query += " AND sender_username = ?"
        params.append(partner_username)
    conn.execute(query, params)


def build_message_threads(profile, mark_read=False, partner_to_mark=None):
    username = profile["username"]
    with get_db_connection() as conn:
        if mark_read:
            mark_messages_read(conn, username, partner_to_mark)
            conn.commit()

        partner_usernames = get_message_partner_usernames(conn, username)
        if not partner_usernames:
            return []

        placeholders = ",".join("?" for _ in partner_usernames)
        partner_rows = conn.execute(
            f"SELECT * FROM users WHERE username IN ({placeholders})",
            partner_usernames,
        ).fetchall()
        profiles_by_username = {
            row["username"]: row_to_profile(row)
            for row in partner_rows
        }

        unread_rows = conn.execute(
            f"""
            SELECT sender_username, COUNT(*) AS count
            FROM messages
            WHERE receiver_username = ?
              AND sender_username IN ({placeholders})
              AND (read_at IS NULL OR read_at = '')
            GROUP BY sender_username
            """,
            [username, *partner_usernames],
        ).fetchall()
        unread_counts = {
            row["sender_username"]: row["count"]
            for row in unread_rows
        }

        message_rows = conn.execute(
            f"""
            WITH scoped_messages AS (
                SELECT
                    CASE
                        WHEN sender_username = ? THEN receiver_username
                        ELSE sender_username
                    END AS partner_username,
                    id,
                    sender_username,
                    receiver_username,
                    body,
                    read_at,
                    created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY CASE
                            WHEN sender_username = ? THEN receiver_username
                            ELSE sender_username
                        END
                        ORDER BY created_at DESC, id DESC
                    ) AS row_number
                FROM messages
                WHERE (sender_username = ? AND receiver_username IN ({placeholders}))
                   OR (receiver_username = ? AND sender_username IN ({placeholders}))
            )
            SELECT partner_username, id, sender_username, receiver_username, body, read_at, created_at
            FROM scoped_messages
            WHERE row_number = 1
            ORDER BY partner_username ASC, created_at ASC, id ASC
            """,
            [username, username, username, *partner_usernames, username, *partner_usernames],
        ).fetchall()

        messages_by_partner = {partner_username: [] for partner_username in partner_usernames}
        for row in message_rows:
            messages_by_partner.setdefault(row["partner_username"], []).append(
                {
                    "id": row["id"],
                    "sender": row["sender_username"],
                    "receiver": row["receiver_username"],
                    "body": row["body"],
                    "created_at": row["created_at"],
                    "read_at": row["read_at"] or "",
                    "is_me": row["sender_username"] == username,
                }
            )

        threads = []
        for partner_username in partner_usernames:
            profile_data = profiles_by_username.get(partner_username)
            if not profile_data:
                continue

            message_items = messages_by_partner.get(partner_username, [])
            last_message = message_items[-1]["body"] if message_items else "아직 대화가 없습니다."
            last_time = message_items[-1]["created_at"] if message_items else ""

            threads.append(
                {
                "username": profile_data["username"],
                "name": profile_data["pet_name"],
                "handle": profile_data["handle"],
                "avatar_url": profile_data["avatar_url"],
                "display_avatar_url": profile_data["display_avatar_url"],
                "initial": profile_data["initial"],
                "last_message": last_message,
                    "last_time": last_time,
                    "messages": [],
                    "messages_loaded": False,
                    "unread_count": unread_counts.get(partner_username, 0),
                    "can_message": True,
                }
            )

    threads.sort(key=lambda thread: thread["last_time"] or "", reverse=True)
    return threads


def get_conversation_messages(username, partner_username, limit=20, mark_read=False):
    page_size = min(50, max(1, int(limit or 20)))
    with get_db_connection() as conn:
        if not can_message_user(conn, username, partner_username):
            return None
        if mark_read:
            mark_messages_read(conn, username, partner_username)
            conn.commit()

        rows = conn.execute(
            """
            SELECT id, sender_username, receiver_username, body, read_at, created_at
            FROM messages
            WHERE (sender_username = ? AND receiver_username = ?)
               OR (sender_username = ? AND receiver_username = ?)
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (username, partner_username, partner_username, username, page_size),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "sender": row["sender_username"],
            "receiver": row["receiver_username"],
            "body": row["body"],
            "created_at": row["created_at"],
            "read_at": row["read_at"] or "",
            "is_me": row["sender_username"] == username,
        }
        for row in reversed(rows)
    ]
