from datetime import datetime, timezone
from html import unescape
import re

from db import get_db_connection
from persona import PERSONA_KEYS, row_to_profile


USER_PROFILE_COLUMNS = [
    "pet_name",
    "pet_species",
    "pet_age",
    "persona",
    "activity_level",
    "pet_likes",
    "pet_dislikes",
    "avatar_url",
    "bio",
    "status_message",
    "favorite_place",
    "personality",
    "owner_persona_note",
    *PERSONA_KEYS,
]


def user_profile_select(alias="u", username_expr=None):
    username_expr = username_expr or f"{alias}.username"
    columns = [f"{username_expr} AS username"]
    columns.extend(f"{alias}.{column}" for column in USER_PROFILE_COLUMNS)
    return ",\n            ".join(columns)


def parse_utc_datetime(value):
    if not value:
        return None

    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]

    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def format_post_time(created_at):
    posted_at = parse_utc_datetime(created_at)
    if not posted_at:
        return "방금 전"

    now = datetime.now(timezone.utc)
    seconds = max(0, int((now - posted_at).total_seconds()))
    if seconds < 60:
        return "방금 전"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전"

    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"

    days = hours // 24
    if days == 1:
        return "어제"
    if days < 7:
        return f"{days}일 전"

    local_time = posted_at.astimezone()
    if local_time.year == now.astimezone().year:
        return local_time.strftime("%m월 %d일")
    return local_time.strftime("%Y년 %m월 %d일")


def caption_html_to_text(caption):
    text = re.sub(r"<br\s*/?>", "\n", str(caption or ""), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def comment_body_html_to_text(content):
    text = re.sub(r"^\s*<b>.*?</b>\s*", "", str(content or ""), flags=re.IGNORECASE | re.DOTALL)
    return caption_html_to_text(text)


def build_comment_item(row, viewer_username=None):
    created_at = row["created_at"] or ""
    username = row["username"] or ""
    return {
        "id": row["id"],
        "post_id": row["post_id"],
        "username": username,
        "content": row["content"] or "",
        "content_text": comment_body_html_to_text(row["content"]),
        "created_at": created_at,
        "time_label": format_post_time(created_at),
        "can_edit": bool(viewer_username and username and username == viewer_username),
    }


def fetch_comments_by_post(conn, post_ids, viewer_username=None, limit_per_post=None):
    if not post_ids:
        return {}

    comments_by_post = {post_id: [] for post_id in post_ids}
    if limit_per_post is not None and int(limit_per_post) <= 0:
        return comments_by_post

    placeholders = ",".join("?" for _ in post_ids)
    if limit_per_post is not None:
        rows = conn.execute(
            f"""
            SELECT id, post_id, content, username, created_at
            FROM (
                SELECT
                    id,
                    post_id,
                    content,
                    username,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY id DESC) AS row_number
                FROM comments
                WHERE post_id IN ({placeholders})
            )
            WHERE row_number <= ?
            ORDER BY post_id ASC, id ASC
            """,
            [*post_ids, max(1, int(limit_per_post))],
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT id, post_id, content, username, created_at
            FROM comments
            WHERE post_id IN ({placeholders})
            ORDER BY id ASC
            """,
            post_ids,
        ).fetchall()

    for row in rows:
        comments_by_post.setdefault(row["post_id"], []).append(build_comment_item(row, viewer_username))
    return comments_by_post


def get_posts(
    username=None,
    viewer_username=None,
    post_ids=None,
    limit=None,
    before_created_at=None,
    before_id=None,
    comment_limit=None,
):
    from .profiles import get_following_usernames

    if post_ids is not None:
        post_ids = list(dict.fromkeys(post_ids))
        if not post_ids:
            return []

    profile_columns = user_profile_select("u", "COALESCE(u.username, p.username)")
    query = f"""
        SELECT
            p.id,
            p.image_url,
            p.caption,
            p.caption_status,
            p.activity_text,
            p.created_at,
            p.taken_on,
            p.weight_kg,
            p.growth_milestone,
            p.pet_age_at_post,
            p.likes,
            (SELECT COUNT(*) FROM comments comment_count WHERE comment_count.post_id = p.id) AS comment_count,
            (
                SELECT COUNT(*)
                FROM post_reactions cute_reaction
                WHERE cute_reaction.post_id = p.id AND cute_reaction.reaction_type = 'cute'
            ) AS cute_count,
            (
                SELECT COUNT(*)
                FROM post_reactions funny_reaction
                WHERE funny_reaction.post_id = p.id AND funny_reaction.reaction_type = 'funny'
            ) AS funny_count,
            p.username AS post_username,
            {profile_columns}
        FROM posts p
        LEFT JOIN users u ON p.username = u.username
    """
    params = []
    conditions = []
    if username:
        conditions.append("p.username = ?")
        params.append(username)
    if post_ids is not None:
        placeholders = ",".join("?" for _ in post_ids)
        conditions.append(f"p.id IN ({placeholders})")
        params.extend(post_ids)
    if before_created_at and before_id:
        conditions.append("(p.created_at < ? OR (p.created_at = ? AND p.id < ?))")
        params.extend([before_created_at, before_created_at, before_id])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY p.created_at DESC, p.id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(max(1, int(limit)))

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        row_ids = [row["id"] for row in rows]
        comments_by_post = fetch_comments_by_post(
            conn,
            row_ids,
            viewer_username,
            limit_per_post=comment_limit,
        )
        following_usernames = get_following_usernames(conn, viewer_username) if viewer_username else set()
        liked_post_ids = set()
        cute_post_ids = set()
        funny_post_ids = set()
        bookmarked_post_ids = set()
        if viewer_username and rows:
            placeholders = ",".join("?" for _ in row_ids)
            like_rows = conn.execute(
                f"""
                SELECT post_id
                FROM post_likes
                WHERE username = ?
                  AND post_id IN ({placeholders})
                """,
                [viewer_username, *row_ids],
            ).fetchall()
            liked_post_ids = {row["post_id"] for row in like_rows}
            reaction_rows = conn.execute(
                f"""
                SELECT post_id, reaction_type
                FROM post_reactions
                WHERE username = ?
                  AND post_id IN ({placeholders})
                """,
                [viewer_username, *row_ids],
            ).fetchall()
            cute_post_ids = {
                row["post_id"] for row in reaction_rows if row["reaction_type"] == "cute"
            }
            funny_post_ids = {
                row["post_id"] for row in reaction_rows if row["reaction_type"] == "funny"
            }
            bookmark_rows = conn.execute(
                f"""
                SELECT post_id
                FROM post_bookmarks
                WHERE username = ?
                  AND post_id IN ({placeholders})
                """,
                [viewer_username, *row_ids],
            ).fetchall()
            bookmarked_post_ids = {row["post_id"] for row in bookmark_rows}
        posts = []
        for row in rows:
            author = row_to_profile(row, row["post_username"])
            post_username = row["post_username"] or author["username"] or ""
            pet_name = author["pet_name"] or post_username or "이름 없는 멍스타"
            caption = row["caption"] or ""
            caption_status = row["caption_status"] or "ready"
            activity_text = row["activity_text"] or ""
            post = {
                "id": row["id"],
                "image_url": row["image_url"],
                "caption": caption,
                "caption_status": caption_status,
                "caption_pending": caption_status == "pending",
                "caption_text": caption_html_to_text(caption),
                "activity_text": activity_text,
                "created_at": row["created_at"] or "",
                "taken_on": row["taken_on"] or "",
                "weight_kg": row["weight_kg"],
                "growth_milestone": row["growth_milestone"] or "",
                "pet_age_at_post": row["pet_age_at_post"],
                "likes": row["likes"] or 0,
                "comment_count": row["comment_count"] or 0,
                "cute_count": row["cute_count"] or 0,
                "funny_count": row["funny_count"] or 0,
                "liked_by_viewer": row["id"] in liked_post_ids,
                "cute_by_viewer": row["id"] in cute_post_ids,
                "funny_by_viewer": row["id"] in funny_post_ids,
                "bookmarked_by_viewer": row["id"] in bookmarked_post_ids,
                "username": post_username,
                "is_owner": bool(viewer_username and post_username == viewer_username),
                "is_following": bool(post_username in following_usernames),
                "pet_name": pet_name,
                "pet_species": author["pet_species"],
                "persona": author["persona"],
                "avatar_url": author["avatar_url"],
                "display_avatar_url": author["display_avatar_url"],
                "initial": pet_name[0].upper(),
                "time_label": format_post_time(row["created_at"]),
                "comments": comments_by_post.get(row["id"], []),
            }
            post["search_text"] = " ".join(
                [post["pet_name"], post["persona"], post["pet_species"], post["caption"], activity_text]
            ).lower()
            posts.append(post)
    return posts


def get_feed_page(viewer_username, limit=20, before_created_at=None, before_id=None):
    page_size = min(30, max(1, int(limit or 20)))
    posts = get_posts(
        viewer_username=viewer_username,
        limit=page_size + 1,
        before_created_at=before_created_at,
        before_id=before_id,
        comment_limit=3,
    )
    has_more = len(posts) > page_size
    page_posts = posts[:page_size]
    last_post = page_posts[-1] if page_posts else None
    next_cursor = (
        {"created_at": last_post["created_at"], "id": last_post["id"]}
        if has_more and last_post
        else None
    )
    return {"posts": page_posts, "has_more": has_more, "next_cursor": next_cursor}


def get_growth_album(username, viewer_username=None):
    posts = get_posts(username, comment_limit=0)
    posts.sort(
        key=lambda post: (
            post.get("taken_on") or (post.get("created_at") or "")[:10],
            post.get("created_at") or "",
            post.get("id") or 0,
        ),
        reverse=True,
    )
    groups = []
    groups_by_month = {}

    for post in posts:
        album_date = (post.get("taken_on") or post.get("created_at") or "")[:10]
        try:
            parsed_date = datetime.strptime(album_date, "%Y-%m-%d")
            month_key = parsed_date.strftime("%Y-%m")
            month_label = parsed_date.strftime("%Y년 %m월")
            date_label = parsed_date.strftime("%m월 %d일")
        except ValueError:
            month_key = "unknown"
            month_label = "날짜를 기록하지 않은 순간"
            date_label = "기록일 없음"

        post["album_date"] = album_date
        post["album_date_label"] = date_label
        post["age_label"] = (
            f"{post['pet_age_at_post']}살"
            if post.get("pet_age_at_post") is not None
            else ""
        )
        post["weight_label"] = (
            f"{float(post['weight_kg']):g}kg"
            if post.get("weight_kg") is not None
            else ""
        )

        if month_key not in groups_by_month:
            group = {"key": month_key, "label": month_label, "posts": []}
            groups_by_month[month_key] = group
            groups.append(group)
        groups_by_month[month_key]["posts"].append(post)

    return {
        "groups": groups,
        "post_count": len(posts),
        "milestone_count": sum(bool(post.get("growth_milestone")) for post in posts),
        "weight_count": sum(post.get("weight_kg") is not None for post in posts),
    }


def get_post(post_id, viewer_username=None):
    posts = get_posts(viewer_username=viewer_username, post_ids=[post_id])
    return posts[0] if posts else None


def get_bookmarked_posts(username):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT post_id
            FROM post_bookmarks
            WHERE username = ?
            ORDER BY created_at DESC
            """,
            (username,),
        ).fetchall()
    bookmarked_ids = [row["post_id"] for row in rows]
    if not bookmarked_ids:
        return []
    posts_by_id = {
        post["id"]: post
        for post in get_posts(post_ids=bookmarked_ids, comment_limit=0)
    }
    return [posts_by_id[post_id] for post_id in bookmarked_ids if post_id in posts_by_id]
