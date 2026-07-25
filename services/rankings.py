from datetime import datetime
from pathlib import Path
import re

from db import get_db_connection
from persona import row_to_profile
from text_utils import clean_single_line_text

from .feed import caption_html_to_text, format_post_time, get_posts


DAILY_AWARD_CATEGORIES = [
    {
        "key": "expression",
        "title": "오늘의 표정왕",
        "label": "표정왕",
        "icon": "fa-regular fa-face-laugh-beam",
        "keywords": ["표정", "눈빛", "포즈", "사진", "찰칵", "시선", "귀여움", "주인공"],
        "persona_keywords": ["인정욕구", "애교"],
        "reason": "사진 속 표정이 오늘 피드에서 제일 말이 많았어요.",
    },
    {
        "key": "tail",
        "title": "오늘의 꼬리왕",
        "label": "꼬리왕",
        "icon": "fa-solid fa-heart",
        "keywords": ["꼬리", "신남", "반가", "좋아", "두근", "행복", "뛰", "방방"],
        "persona_keywords": ["놀이파", "활발", "애교"],
        "reason": "신난 기분이 꼬리까지 전해지는 게시물이에요.",
    },
    {
        "key": "clingy",
        "title": "오늘의 껌딱지왕",
        "label": "껌딱지왕",
        "icon": "fa-solid fa-hand-holding-heart",
        "keywords": ["집사", "옆", "품", "붙", "같이", "손", "무릎", "기다"],
        "persona_keywords": ["껌딱지", "cuddly"],
        "reason": "집사와의 거리가 가까워 보이는 순간이에요.",
    },
    {
        "key": "play",
        "title": "오늘의 놀이 MVP",
        "label": "놀이 MVP",
        "icon": "fa-solid fa-baseball",
        "keywords": ["놀이", "공", "장난감", "달리", "뛰", "신나", "한번더", "에너지"],
        "persona_keywords": ["놀이파", "outdoor"],
        "reason": "놀 준비가 끝난 에너지가 화면 밖까지 느껴져요.",
    },
]


def _daily_award_score(post, category, index):
    text = " ".join(
        [
            post.get("pet_name") or "",
            post.get("persona") or "",
            post.get("caption_text") or "",
            post.get("activity_text") or "",
            post.get("search_text") or "",
        ]
    ).lower()
    score = max(0, 40 - index)
    score += min(int(post.get("likes") or 0), 20)
    score += sum(9 for keyword in category["keywords"] if keyword.lower() in text)
    score += sum(5 for keyword in category["persona_keywords"] if keyword.lower() in text)
    return score


def _daily_award_relevance(post, category):
    text = " ".join(
        [
            post.get("pet_name") or "",
            post.get("persona") or "",
            post.get("caption_text") or "",
            post.get("activity_text") or "",
            post.get("search_text") or "",
        ]
    ).lower()
    return sum(1 for keyword in category["keywords"] if keyword.lower() in text) + sum(
        1 for keyword in category["persona_keywords"] if keyword.lower() in text
    )


def _award_blurb(post, category):
    source = post.get("activity_text") or post.get("caption_text") or ""
    source = caption_html_to_text(source)
    if source:
        source = clean_single_line_text(source, 58)
        return f"{source}"
    return category["reason"]


def _daily_award_image_key(post):
    image_url = post.get("image_url") or ""
    filename = Path(image_url.split("?", 1)[0]).name.lower()
    return re.sub(r"^\d{14,20}_", "", filename) or image_url


def _select_daily_award_winners(ranked_posts, category, used_post_ids, used_image_keys, limit, require_relevance=True):
    winners = []
    for _index, post in ranked_posts:
        image_key = _daily_award_image_key(post)
        if post["id"] in used_post_ids:
            continue
        if image_key in used_image_keys:
            continue
        if require_relevance and _daily_award_relevance(post, category) <= 0:
            continue
        winners.append(post)
        used_post_ids.add(post["id"])
        used_image_keys.add(image_key)
        if len(winners) >= limit:
            break
    return winners


def build_daily_awards(viewer_username=None, limit_per_category=1):
    # Awards are identical for every viewer and do not render comments or
    # viewer-specific like/bookmark state.
    posts = get_posts(limit=80, comment_limit=0)
    if not posts:
        return []

    awards = []
    used_post_ids = set()
    used_image_keys = set()
    today_label = datetime.now().strftime("%m.%d")
    award_slots = []
    ranked_by_category = []
    for category in DAILY_AWARD_CATEGORIES:
        indexed_posts = list(enumerate(posts))
        ranked = sorted(
            indexed_posts,
            key=lambda item: _daily_award_score(item[1], category, item[0]),
            reverse=True,
        )
        ranked_by_category.append((category, ranked))
        winners = _select_daily_award_winners(
            ranked,
            category,
            used_post_ids,
            used_image_keys,
            limit_per_category,
            require_relevance=True,
        )
        award_slots.append(winners[0] if winners else None)

    for index, (category, ranked) in enumerate(ranked_by_category):
        if award_slots[index] is not None:
            continue
        winners = _select_daily_award_winners(
            ranked,
            category,
            used_post_ids,
            used_image_keys,
            limit_per_category,
            require_relevance=False,
        )
        award_slots[index] = winners[0] if winners else None

    for category, post in zip(DAILY_AWARD_CATEGORIES, award_slots):
        if not post:
            continue

        awards.append(
            {
                "key": category["key"],
                "title": category["title"],
                "label": category["label"],
                "icon": category["icon"],
                "reason": category["reason"],
                "date_label": today_label,
                "post": {
                    "id": post["id"],
                    "image_url": post["image_url"],
                    "pet_name": post["pet_name"],
                    "username": post["username"],
                    "avatar_url": post["avatar_url"],
                    "display_avatar_url": post["display_avatar_url"],
                    "initial": post["initial"],
                    "likes": post["likes"],
                    "time_label": post["time_label"],
                    "blurb": _award_blurb(post, category),
                },
            }
        )
    return awards


def build_reaction_rankings():
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            WITH post_totals AS (
                SELECT
                    username,
                    COUNT(*) AS post_count,
                    COALESCE(SUM(likes), 0) AS total_likes
                FROM posts
                GROUP BY username
            ),
            reaction_totals AS (
                SELECT
                    p.username,
                    COALESCE(SUM(CASE WHEN r.reaction_type = 'cute' THEN 1 ELSE 0 END), 0) AS total_cute,
                    COALESCE(SUM(CASE WHEN r.reaction_type = 'funny' THEN 1 ELSE 0 END), 0) AS total_funny
                FROM posts p
                LEFT JOIN post_reactions r ON r.post_id = p.id
                GROUP BY p.username
            )
            SELECT
                u.*,
                COALESCE(pt.total_likes, 0) AS total_likes,
                COALESCE(pt.post_count, 0) AS post_count,
                COALESCE(rt.total_cute, 0) AS total_cute,
                COALESCE(rt.total_funny, 0) AS total_funny
            FROM users u
            LEFT JOIN post_totals pt ON pt.username = u.username
            LEFT JOIN reaction_totals rt ON rt.username = u.username
            """
        ).fetchall()
        ranking_specs = {
            "likes": ("total_likes", "좋아요"),
            "cute": ("total_cute", "귀여워"),
            "funny": ("total_funny", "웃겨"),
        }
        ranked_rows = {}
        for mode, (count_key, _) in ranking_specs.items():
            ranked_rows[mode] = sorted(
                rows,
                key=lambda row: (
                    -(row[count_key] or 0),
                    -(row["post_count"] or 0),
                    row["username"],
                ),
            )[:5]

        ranked_usernames = list(
            dict.fromkeys(
                row["username"]
                for mode_rows in ranked_rows.values()
                for row in mode_rows
            )
        )
        if ranked_usernames:
            placeholders = ",".join("?" for _ in ranked_usernames)
            latest_rows = conn.execute(
                f"""
                SELECT id, username, image_url, caption, created_at, likes
                FROM (
                    SELECT
                        p.id,
                        p.username,
                        p.image_url,
                        p.caption,
                        p.created_at,
                        p.likes,
                        ROW_NUMBER() OVER (
                            PARTITION BY p.username
                            ORDER BY p.created_at DESC, p.id DESC
                        ) AS row_number
                    FROM posts p
                    WHERE p.username IN ({placeholders})
                )
                WHERE row_number = 1
                """,
                ranked_usernames,
            ).fetchall()
        else:
            latest_rows = []

    latest_posts = {}
    for row in latest_rows:
        latest_posts.setdefault(
            row["username"],
            {
                "id": row["id"],
                "image_url": row["image_url"],
                "caption_text": caption_html_to_text(row["caption"]),
                "likes": row["likes"] or 0,
                "time_label": format_post_time(row["created_at"]),
            },
        )
    rankings = {}
    for mode, mode_rows in ranked_rows.items():
        count_key, reaction_label = ranking_specs[mode]
        rankings[mode] = []
        for index, row in enumerate(mode_rows, start=1):
            profile = row_to_profile(row)
            pet_name = profile["pet_name"] or profile["username"] or "멍스타"
            rankings[mode].append(
                {
                    "rank": index,
                    "pet_name": pet_name,
                    "username": profile["username"],
                    "avatar_url": profile["avatar_url"],
                    "display_avatar_url": profile["display_avatar_url"],
                    "initial": pet_name[0].upper(),
                    "persona": profile["persona"],
                    "total_likes": row["total_likes"] or 0,
                    "total_cute": row["total_cute"] or 0,
                    "total_funny": row["total_funny"] or 0,
                    "reaction_count": row[count_key] or 0,
                    "reaction_label": reaction_label,
                    "post_count": row["post_count"] or 0,
                    "latest_post": latest_posts.get(profile["username"]),
                }
            )
    return rankings


def build_like_ranking():
    return build_reaction_rankings()["likes"]
