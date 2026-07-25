from db import get_db_connection
from persona import row_to_profile

from .feed import format_post_time, get_posts
from .matching import add_match_info
from .messaging import get_unread_message_count
from .notifications import get_unread_notification_count


def get_user_profile(username):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    profile = row_to_profile(row, username)
    if not row:
        profile["has_pet_profile"] = False
        return profile

    row_keys = set(row.keys())
    profile["account_email"] = row["account_email"] if "account_email" in row_keys else ""
    profile["account_name"] = row["account_name"] if "account_name" in row_keys else ""
    profile["account_avatar_url"] = row["account_avatar_url"] if "account_avatar_url" in row_keys else ""
    profile["has_pet_profile"] = bool(
        row["pet_profile_completed"] if "pet_profile_completed" in row_keys else True
    )
    if not profile["has_pet_profile"]:
        profile["pet_name"] = profile["account_name"] or "새로운 보호자"
        profile["avatar_url"] = profile["account_avatar_url"] or ""
        profile["display_avatar_url"] = profile["avatar_url"]
        profile["initial"] = profile["pet_name"][:1].upper()
        profile["pet_species"] = ""
        profile["pet_age"] = None
        profile["persona"] = ""
        profile["persona_summary"] = ""
        profile["persona_traits"] = []
        profile["activity_level"] = ""
        profile["pet_likes"] = ""
        profile["pet_dislikes"] = ""
        profile["status_message"] = ""
        profile["bio"] = ""
        profile["favorite_place"] = ""
        profile["personality"] = ""
    return profile


def get_account_profile(username):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT
                u.username,
                u.account_name,
                u.account_email,
                u.account_avatar_url,
                u.pet_name,
                u.avatar_url,
                o.provider,
                o.created_at
            FROM users u
            LEFT JOIN oauth_accounts o ON o.username = u.username
            WHERE u.username = ?
            ORDER BY o.id DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
    if not row:
        return None

    provider = row["provider"] or "password"
    provider_labels = {
        "google": "Google",
        "kakao": "카카오",
        "email": "이메일",
        "password": "기존 아이디",
    }
    return {
        "username": row["username"],
        "name": row["account_name"] or row["pet_name"] or row["username"],
        "email": row["account_email"] or "",
        "avatar_url": row["account_avatar_url"] or row["avatar_url"] or "",
        "provider": provider,
        "provider_label": provider_labels.get(provider, provider),
        "created_at": row["created_at"] or "",
    }


def get_following_usernames(conn, username):
    rows = conn.execute(
        "SELECT followed_username FROM follows WHERE follower_username = ?",
        (username,),
    ).fetchall()
    return {row["followed_username"] for row in rows}


def get_following_profiles(username):
    with get_db_connection() as conn:
        viewer_row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        rows = conn.execute(
            """
            SELECT
                u.*,
                COUNT(p.id) AS posts_count,
                COALESCE(SUM(p.likes), 0) AS total_likes,
                (
                    SELECT COUNT(*)
                    FROM follows ff
                    WHERE ff.follower_username = u.username
                ) AS friend_count
            FROM follows f
            JOIN users u ON u.username = f.followed_username
            LEFT JOIN posts p ON p.username = u.username
            WHERE f.follower_username = ?
            GROUP BY u.username
            ORDER BY f.created_at DESC, u.pet_name ASC
            """,
            (username,),
        ).fetchall()

    viewer_profile = row_to_profile(viewer_row, username)
    friends = []
    for row in rows:
        profile = row_to_profile(row)
        profile["posts_count"] = row["posts_count"] or 0
        profile["total_likes"] = row["total_likes"] or 0
        profile["friend_count"] = row["friend_count"] or 0
        profile["is_following"] = True
        add_match_info(viewer_profile, profile)
        profile["badges"] = build_profile_badges(profile)
        friends.append(profile)
    return friends


def get_friend_suggestions(username, limit=8):
    candidate_limit = max(limit * 5, 40)
    with get_db_connection() as conn:
        viewer_row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        rows = conn.execute(
            """
            SELECT
                u.*,
                COUNT(p.id) AS posts_count,
                COALESCE(SUM(p.likes), 0) AS total_likes,
                MAX(p.created_at) AS last_post_at,
                (
                    SELECT COUNT(*)
                    FROM follows ff
                    WHERE ff.follower_username = u.username
                ) AS friend_count
            FROM users u
            LEFT JOIN posts p ON p.username = u.username
            WHERE u.username != ?
              AND u.username NOT IN (
                  SELECT followed_username
                  FROM follows
                  WHERE follower_username = ?
              )
            GROUP BY u.username
            ORDER BY last_post_at DESC, posts_count DESC, total_likes DESC, u.pet_name ASC
            LIMIT ?
            """,
            (username, username, candidate_limit),
        ).fetchall()

    viewer_profile = row_to_profile(viewer_row, username)
    suggestions = []
    for row in rows:
        profile = row_to_profile(row)
        profile["posts_count"] = row["posts_count"] or 0
        profile["total_likes"] = row["total_likes"] or 0
        profile["friend_count"] = row["friend_count"] or 0
        profile["last_post_at"] = row["last_post_at"] or ""
        profile["last_post_label"] = format_post_time(row["last_post_at"]) if row["last_post_at"] else "아직 게시물 없음"
        profile["is_following"] = False
        add_match_info(viewer_profile, profile)
        profile["badges"] = build_profile_badges(profile)
        suggestions.append(profile)
    suggestions.sort(key=lambda item: (item["match_score"], item["posts_count"], item["total_likes"]), reverse=True)
    return suggestions[:limit]


def search_profiles(viewer_username, query="", persona="", sort="match", limit=24):
    query = (query or "").strip().lower()
    persona = (persona or "").strip()
    sort = (sort or "match").strip()

    with get_db_connection() as conn:
        viewer_row = conn.execute("SELECT * FROM users WHERE username = ?", (viewer_username,)).fetchone()
        following_usernames = get_following_usernames(conn, viewer_username)

        sql = """
            SELECT
                u.*,
                COUNT(p.id) AS posts_count,
                COALESCE(SUM(p.likes), 0) AS total_likes,
                MAX(p.created_at) AS last_post_at,
                (
                    SELECT COUNT(*)
                    FROM follows ff
                    WHERE ff.follower_username = u.username
                ) AS friend_count
            FROM users u
            LEFT JOIN posts p ON p.username = u.username
            WHERE u.username != ?
        """
        params = [viewer_username]

        if query:
            sql += """
              AND (
                  LOWER(u.username) LIKE ?
                  OR LOWER(u.pet_name) LIKE ?
                  OR LOWER(u.pet_species) LIKE ?
                  OR LOWER(u.persona) LIKE ?
                  OR LOWER(u.status_message) LIKE ?
                  OR LOWER(u.bio) LIKE ?
              )
            """
            like_pattern = f"%{query}%"
            params.extend([like_pattern] * 6)

        if persona:
            sql += " AND u.persona = ?"
            params.append(persona)

        sql += " GROUP BY u.username ORDER BY u.pet_name ASC, u.username ASC"
        rows = conn.execute(sql, params).fetchall()

    viewer_profile = row_to_profile(viewer_row, viewer_username)
    results = []
    for row in rows:
        profile = row_to_profile(row)
        profile["posts_count"] = row["posts_count"] or 0
        profile["total_likes"] = row["total_likes"] or 0
        profile["friend_count"] = row["friend_count"] or 0
        add_match_info(viewer_profile, profile)
        profile["badges"] = build_profile_badges(profile)

        results.append(
            {
                "username": profile["username"],
                "pet_name": profile["pet_name"],
                "handle": profile["handle"],
                "pet_species": profile["pet_species"],
                "persona": profile["persona"],
                "status_message": profile["status_message"],
                "avatar_url": profile["avatar_url"],
                "display_avatar_url": profile["display_avatar_url"],
                "initial": profile["initial"],
                "posts_count": profile["posts_count"],
                "total_likes": profile["total_likes"],
                "last_post_at": row["last_post_at"] or "",
                "last_post_label": format_post_time(row["last_post_at"]) if row["last_post_at"] else "아직 게시물 없음",
                "match_score": profile["match_score"],
                "match_label": profile["match_label"],
                "match_reasons": profile["match_reasons"],
                "match_summary": profile["match_summary"],
                "badges": profile["badges"],
                "is_following": profile["username"] in following_usernames,
                "is_me": profile["username"] == viewer_username,
            }
        )

    sort_key_map = {
        "match": lambda item: (item["match_score"], item["posts_count"], item["total_likes"], item["pet_name"]),
        "recent": lambda item: (item["last_post_at"] or "", item["posts_count"], item["match_score"], item["pet_name"]),
        "posts": lambda item: (item["posts_count"], item["total_likes"], item["match_score"], item["pet_name"]),
        "likes": lambda item: (item["total_likes"], item["posts_count"], item["match_score"], item["pet_name"]),
    }
    results.sort(key=sort_key_map.get(sort, sort_key_map["match"]), reverse=True)
    return results[:limit]


def build_profile_badges(profile):
    if profile.get("has_pet_profile") is False:
        return []

    posts_count = int(profile.get("posts_count") or 0)
    total_likes = int(profile.get("total_likes") or 0)
    friend_count = int(profile.get("friend_count") or 0)

    badges = []
    if total_likes >= 10:
        badges.append({"label": "인기스타", "icon": "fa-solid fa-star", "description": "좋아요를 많이 받은 친구"})
    elif total_likes >= 3:
        badges.append({"label": "반응부자", "icon": "fa-solid fa-heart", "description": "반응이 차곡차곡 쌓이는 중"})

    if posts_count >= 10:
        badges.append({"label": "기록왕", "icon": "fa-solid fa-camera-retro", "description": "일상을 꾸준히 남기는 친구"})
    elif posts_count >= 3:
        badges.append({"label": "꾸준러", "icon": "fa-regular fa-images", "description": "게시물을 꾸준히 올리는 친구"})

    if friend_count >= 5:
        badges.append({"label": "사교왕", "icon": "fa-solid fa-user-group", "description": "친구들과 활발히 연결돼 있어요"})
    elif friend_count >= 2:
        badges.append({"label": "친구부자", "icon": "fa-regular fa-handshake", "description": "친구 관계가 자라는 중"})

    if profile.get("persona_energy") == "outdoor" or profile.get("activity_level") == "높음":
        badges.append({"label": "산책왕", "icon": "fa-solid fa-shoe-prints", "description": "밖에서 보내는 시간을 좋아해요"})
    if profile.get("persona_focus") == "snack":
        badges.append({"label": "간식러버", "icon": "fa-solid fa-cookie-bite", "description": "간식 시간이 제일 설레요"})
    elif profile.get("persona_focus") == "play":
        badges.append({"label": "놀이대장", "icon": "fa-solid fa-baseball", "description": "노는 시간이 제일 빛나요"})

    if not badges:
        badges.append({"label": "새싹친구", "icon": "fa-solid fa-seedling", "description": "프로필을 채워가고 있어요"})
    return badges[:3]


def get_profile_stats(username):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS posts_count,
                COALESCE(SUM(likes), 0) AS total_likes,
                (
                    SELECT COUNT(*)
                    FROM follows
                    WHERE follower_username = ?
                ) AS friend_count,
                (
                    SELECT COUNT(*)
                    FROM post_bookmarks
                    WHERE username = ?
                ) AS bookmark_count
            FROM posts
            WHERE username = ?
            """,
            (username, username, username),
        ).fetchone()

    posts_count = row["posts_count"] if row else 0
    total_likes = row["total_likes"] if row else 0
    friend_count = row["friend_count"] if row else 0
    bookmark_count = row["bookmark_count"] if row else 0
    return {
        "posts_count": posts_count,
        "total_likes": total_likes,
        "friend_count": friend_count,
        "bookmark_count": bookmark_count,
    }


def serialize_bootstrap(page_name, profile, notifications, message_threads):
    return {
        "page": page_name,
        "profile": profile,
        "notifications": notifications,
        "notification_unread_count": get_unread_notification_count(profile["username"]),
        "message_unread_count": get_unread_message_count(profile["username"]),
        "message_threads": message_threads,
        "has_pet_profile": bool(profile.get("has_pet_profile", True)),
        "pet_onboarding_url": "/pet-onboarding",
    }
