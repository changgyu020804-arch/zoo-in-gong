from db import get_db_connection


def create_notification(conn, recipient_username, actor_username, notification_type, title, body, link=""):
    if not recipient_username or recipient_username == actor_username:
        return None

    cursor = conn.execute(
        """
        INSERT INTO notifications
            (recipient_username, actor_username, type, title, body, link)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (recipient_username, actor_username, notification_type, title, body, link or ""),
    )
    return cursor.lastrowid


def row_to_notification(row):
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "link": row["link"] or "",
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"],
        "actor_username": row["actor_username"] or "",
    }


def build_notifications(username, limit=20, since_id=None):
    query = """
        SELECT id, actor_username, type, title, body, link, is_read, created_at
        FROM notifications
        WHERE recipient_username = ?
    """
    params = [username]
    if since_id is not None:
        query += " AND id > ?"
        params.append(since_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    notifications = [row_to_notification(row) for row in rows]
    if notifications or since_id is not None:
        return notifications

    return [
        {
            "id": 0,
            "type": "welcome",
            "title": "알림이 여기에 표시돼요",
            "body": "좋아요, 팔로우, 댓글, 메시지가 오면 바로 알려드릴게요.",
            "link": "",
            "is_read": True,
            "created_at": "",
            "actor_username": "",
        }
    ]


def get_unread_notification_count(username):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM notifications
            WHERE recipient_username = ? AND is_read = 0
            """,
            (username,),
        ).fetchone()
    return row["count"] if row else 0


def mark_notifications_read(username):
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE recipient_username = ? AND is_read = 0
            """,
            (username,),
        )
        conn.commit()
