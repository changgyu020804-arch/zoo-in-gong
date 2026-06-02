from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import re

from db import get_db_connection
from persona import PERSONA_KEYS, row_to_profile
from text_utils import clean_single_line_text


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

MATCH_FIELDS = [
    "persona_energy",
    "persona_social",
    "persona_curiosity",
    "persona_expression",
    "persona_focus",
    "persona_reaction",
    "persona_routine",
    "persona_voice",
    "persona_cuddle",
    "persona_style",
]

MATCH_FIELD_LABELS = {
    "persona_energy": "에너지",
    "persona_social": "친구 성향",
    "persona_curiosity": "호기심",
    "persona_expression": "애정 표현",
    "persona_focus": "하루의 즐거움",
    "persona_reaction": "반응 방식",
    "persona_routine": "루틴",
    "persona_voice": "표현 방식",
    "persona_cuddle": "스킨십",
    "persona_style": "사진 무드",
}

DAILY_MISSIONS = [
    {
        "key": "tail-moment",
        "title": "꼬리가 먼저 말한 순간",
        "prompt": "꼬리가 먼저 반응했던 순간을 찍었어요. 어떤 표정이었는지 같이 적어주세요.",
        "helper": "반가움, 기대, 신남처럼 표정이 보이는 사진에 잘 맞아요.",
        "icon": "fa-solid fa-heart",
        "angles": ["눈빛 먼저", "꼬리 증거", "집사 반응"],
    },
    {
        "key": "best-spot",
        "title": "오늘의 최애 자리",
        "prompt": "오늘 가장 마음에 들었던 자리에서 쉬거나 놀았어요. 왜 그 자리가 좋았는지 적어주세요.",
        "helper": "소파, 창가, 공원 벤치, 집사 옆자리 모두 좋아요.",
        "icon": "fa-solid fa-location-dot",
        "angles": ["자리 자랑", "햇살 점수", "편안함 인증"],
    },
    {
        "key": "tiny-brag",
        "title": "작은 자랑 하나",
        "prompt": "오늘 잘한 일을 하나 자랑하고 싶어요. 기다리기, 앉기, 예쁜 표정 같은 작은 성공을 적어주세요.",
        "helper": "훈련 성공이나 귀여운 포즈를 올릴 때 좋아요.",
        "icon": "fa-solid fa-star",
        "angles": ["칭찬 대기", "성공 인증", "표정 점수"],
    },
    {
        "key": "sniff-report",
        "title": "코끝 리포트",
        "prompt": "오늘 코끝이 제일 바빴던 순간을 기록했어요. 어떤 냄새나 장면이 궁금했는지 적어주세요.",
        "helper": "킁킁 탐색, 새 장소, 낯선 물건 사진에 잘 맞아요.",
        "icon": "fa-solid fa-magnifying-glass",
        "angles": ["단서 발견", "수상한 물건", "코끝 뉴스"],
    },
    {
        "key": "play-scene",
        "title": "놀이 하이라이트",
        "prompt": "오늘 제일 신났던 놀이 순간이에요. 장난감, 공, 달리기 중 무엇이 좋았는지 적어주세요.",
        "helper": "움직임이 있거나 신난 표정의 사진에 잘 맞아요.",
        "icon": "fa-solid fa-baseball",
        "angles": ["MVP 장면", "한 번 더", "장난감 주연"],
    },
    {
        "key": "with-human",
        "title": "집사랑 한 컷",
        "prompt": "집사랑 같이 보낸 순간을 올려요. 집사가 오늘 어떤 역할을 했는지 귀엽게 적어주세요.",
        "helper": "손, 발, 그림자, 같이 있는 분위기만 보여도 충분해요.",
        "icon": "fa-solid fa-hand-holding-heart",
        "angles": ["집사 평가", "옆자리 인증", "둘만의 순간"],
    },
    {
        "key": "sleepy-peace",
        "title": "몽글몽글 휴식",
        "prompt": "오늘 가장 포근했던 쉬는 시간을 남겨요. 어디서 어떻게 쉬었는지 적어주세요.",
        "helper": "낮잠, 햇볕, 담요, 조용한 표정에 잘 맞아요.",
        "icon": "fa-solid fa-cloud",
        "angles": ["낮잠 증거", "담요 보고", "느긋한 표정"],
    },
    {
        "key": "guilty-face",
        "title": "억울한 척 챌린지",
        "prompt": "오늘 가장 억울하거나 아무 잘못 없는 척한 표정을 찍었어요. 무슨 일이 있었는지 적어주세요.",
        "helper": "눈썹, 입꼬리, 고개 각도가 살아 있는 사진이면 반응이 좋아요.",
        "icon": "fa-regular fa-face-meh",
        "angles": ["무죄 주장", "눈빛 해명", "집사 재판"],
    },
    {
        "key": "snack-stare",
        "title": "기대 눈빛 한 컷",
        "prompt": "무언가를 기다리는 눈빛을 남겼어요. 무엇을 기대했는지 강아지 입장에서 적어주세요.",
        "helper": "밥그릇, 손, 식탁 아래, 문 앞에서 찍은 사진에 잘 맞아요.",
        "icon": "fa-solid fa-cookie-bite",
        "angles": ["눈빛 협상", "기다림 인증", "한입 상상"],
    },
    {
        "key": "before-after",
        "title": "전후 사정 있는 사진",
        "prompt": "이 사진 전후에 무슨 일이 있었는지 짧게 적어주세요. 사진만 봐도 궁금해지는 순간이면 좋아요.",
        "helper": "비포/애프터가 떠오르는 장면은 댓글을 부르기 좋아요.",
        "icon": "fa-solid fa-wand-magic-sparkles",
        "angles": ["사건 전말", "3초 전", "다음 장면"],
    },
    {
        "key": "main-character",
        "title": "오늘의 주인공 포즈",
        "prompt": "오늘 우리 강아지가 주인공처럼 보였던 순간을 올려요. 어떤 포인트가 제일 빛났는지 적어주세요.",
        "helper": "정면샷, 옆모습, 당당한 자세처럼 한눈에 캐릭터가 보이는 사진에 잘 맞아요.",
        "icon": "fa-solid fa-crown",
        "angles": ["무대 등장", "포즈값 완료", "시선 강탈"],
    },
    {
        "key": "weird-sleep",
        "title": "수상한 자세 박물관",
        "prompt": "오늘 이상하지만 귀여운 자세를 발견했어요. 왜 그렇게 있었는지 상상해서 적어주세요.",
        "helper": "잠자는 자세, 삐딱한 자세, 엉뚱한 각도 사진이 잘 어울려요.",
        "icon": "fa-solid fa-puzzle-piece",
        "angles": ["자세 해석", "편안함 논란", "수면 과학"],
    },
]

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


def user_profile_select(alias="u", username_expr=None):
    username_expr = username_expr or f"{alias}.username"
    columns = [f"{username_expr} AS username"]
    columns.extend(f"{alias}.{column}" for column in USER_PROFILE_COLUMNS)
    return ",\n            ".join(columns)


def get_user_profile(username):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return row_to_profile(row, username)


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


def build_match_summary(viewer_profile, target_profile, same_fields, reasons):
    if not viewer_profile or not target_profile:
        return "프로필을 조금 더 채우면 더 정확하게 추천할 수 있어요."

    if same_fields:
        labels = [MATCH_FIELD_LABELS.get(field, field) for field in same_fields[:2]]
        if len(same_fields) > 2:
            labels.append(f"외 {len(same_fields) - 2}개")
        return f"{', '.join(labels)}가 잘 맞아서 먼저 말을 걸기 좋아 보여요."

    if reasons:
        return f"{reasons[0]} 그래서 천천히 친해지기 좋은 친구예요."

    return f"{target_profile.get('persona') or '비슷한 분위기'} 성향이라 새 친구로 추천해요."


def add_match_info(viewer_profile, target_profile):
    if not viewer_profile or not target_profile:
        target_profile["match_score"] = 0
        target_profile["match_label"] = "새 친구"
        target_profile["match_reasons"] = []
        return target_profile

    score = 42
    reasons = []
    same_fields = [
        field
        for field in MATCH_FIELDS
        if viewer_profile.get(field) and viewer_profile.get(field) == target_profile.get(field)
    ]
    score += min(40, len(same_fields) * 4)
    if same_fields:
        reasons.append(f"성향 {len(same_fields)}개가 같아요")

    if viewer_profile.get("pet_species") and viewer_profile.get("pet_species") == target_profile.get("pet_species"):
        score += 8
        reasons.append("견종이 같아요")
    if viewer_profile.get("activity_level") and viewer_profile.get("activity_level") == target_profile.get("activity_level"):
        score += 6
        reasons.append("활동량이 비슷해요")

    likes = " ".join([viewer_profile.get("pet_likes") or "", target_profile.get("pet_likes") or ""]).lower()
    if viewer_profile.get("pet_likes") and target_profile.get("pet_likes"):
        viewer_tokens = set(re.findall(r"[\w가-힣]+", viewer_profile["pet_likes"].lower()))
        target_tokens = set(re.findall(r"[\w가-힣]+", target_profile["pet_likes"].lower()))
        shared_likes = viewer_tokens & target_tokens
        if shared_likes:
            score += 4
            reasons.append(f"{sorted(shared_likes)[0]}을 같이 좋아해요")
    if any(keyword in likes for keyword in ["산책", "공원", "run", "walk"]):
        score += 2
        reasons.append("산책 취향이 맞아요")

    score = max(35, min(score, 98))
    if score >= 86:
        label = "찰떡 멍친구"
    elif score >= 72:
        label = "잘 맞는 친구"
    elif score >= 58:
        label = "천천히 친해질 친구"
    else:
        label = "새로 알아갈 친구"

    target_profile["match_score"] = score
    target_profile["match_label"] = label
    target_profile["match_reasons"] = reasons[:3] or ["프로필 분위기가 잘 맞아요"]
    target_profile["match_summary"] = build_match_summary(viewer_profile, target_profile, same_fields, reasons)
    return target_profile


def build_profile_badges(profile):
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


def build_daily_mission(profile, today=None):
    today = today or datetime.now().date()
    seed_text = f"{today.isoformat()}:{profile.get('username', '')}:{profile.get('persona', '')}"
    seed = sum(ord(char) for char in seed_text)
    mission = dict(DAILY_MISSIONS[seed % len(DAILY_MISSIONS)])

    persona = profile.get("persona", "")
    if "간식파" in persona:
        mission["helper"] = f"{mission['helper']} 칭찬이나 작은 기대감을 살짝 섞어도 좋아요."
        mission["angles"] = ["기대 눈빛", "한입 협상", *(mission.get("angles") or [])]
    elif "놀이파" in persona:
        mission["helper"] = f"{mission['helper']} 신난 에너지를 한 문장 더해보세요."
        mission["angles"] = ["한 번 더", "장난감 주연", *(mission.get("angles") or [])]
    elif "평화주의" in persona:
        mission["helper"] = f"{mission['helper']} 느긋하고 포근한 느낌을 살려보세요."
        mission["angles"] = ["느긋한 표정", "햇살 저장", *(mission.get("angles") or [])]

    mission["angles"] = list(dict.fromkeys(mission.get("angles") or []))[:4]
    mission["date_label"] = today.strftime("%m.%d")
    mission["cta"] = "이 미션으로 쓰기"
    return mission


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
    posts = get_posts(viewer_username=viewer_username)[:80]
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
            WHERE row_number <= 80
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
                    "messages": message_items,
                    "unread_count": unread_counts.get(partner_username, 0),
                    "can_message": True,
                }
            )

    threads.sort(key=lambda thread: thread["last_time"] or "", reverse=True)
    return threads


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
            GROUP BY u.username
            ORDER BY u.pet_name ASC, u.username ASC
            """
        ).fetchall()

    viewer_profile = row_to_profile(viewer_row, viewer_username)
    results = []
    for row in rows:
        profile = row_to_profile(row)
        if profile["username"] == viewer_username:
            continue
        profile["posts_count"] = row["posts_count"] or 0
        profile["total_likes"] = row["total_likes"] or 0
        profile["friend_count"] = row["friend_count"] or 0
        add_match_info(viewer_profile, profile)
        profile["badges"] = build_profile_badges(profile)

        if persona and profile["persona"] != persona:
            continue

        haystack = " ".join(
            [
                profile["username"],
                profile["pet_name"],
                profile["pet_species"],
                profile["persona"],
                profile["status_message"],
                profile["bio"],
            ]
        ).lower()
        if query and query not in haystack:
            continue

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


def fetch_comments_by_post(conn, post_ids, viewer_username=None):
    if not post_ids:
        return {}

    placeholders = ",".join("?" for _ in post_ids)
    rows = conn.execute(
        f"""
        SELECT id, post_id, content, username, created_at
        FROM comments
        WHERE post_id IN ({placeholders})
        ORDER BY id ASC
        """,
        post_ids,
    ).fetchall()

    comments_by_post = {post_id: [] for post_id in post_ids}
    for row in rows:
        comments_by_post.setdefault(row["post_id"], []).append(build_comment_item(row, viewer_username))
    return comments_by_post


def get_posts(username=None, viewer_username=None, post_ids=None):
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
            p.likes,
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
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY p.created_at DESC, p.id DESC"

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        row_ids = [row["id"] for row in rows]
        comments_by_post = fetch_comments_by_post(conn, row_ids, viewer_username)
        following_usernames = get_following_usernames(conn, viewer_username) if viewer_username else set()
        liked_post_ids = set()
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
                "likes": row["likes"] or 0,
                "liked_by_viewer": row["id"] in liked_post_ids,
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
        for post in get_posts(viewer_username=username, post_ids=bookmarked_ids)
    }
    return [posts_by_id[post_id] for post_id in bookmarked_ids if post_id in posts_by_id]


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


def build_like_ranking():
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                u.*,
                COALESCE(SUM(p.likes), 0) AS total_likes,
                COUNT(p.id) AS post_count
            FROM users u
            LEFT JOIN posts p ON p.username = u.username
            GROUP BY u.username
            ORDER BY total_likes DESC, post_count DESC, u.username ASC
            LIMIT 5
            """
        ).fetchall()
        latest_rows = conn.execute(
            """
            SELECT p.id, p.username, p.image_url, p.caption, p.created_at, p.likes
            FROM posts p
            JOIN (
                SELECT username, MAX(created_at) AS latest_at
                FROM posts
                GROUP BY username
            ) latest
              ON latest.username = p.username
             AND latest.latest_at = p.created_at
            ORDER BY p.id DESC
            """
        ).fetchall()

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
    rankings = []
    for index, row in enumerate(rows, start=1):
        profile = row_to_profile(row)
        pet_name = profile["pet_name"] or profile["username"] or "멍스타"
        rankings.append(
            {
                "rank": index,
                "pet_name": pet_name,
                "username": profile["username"],
                "avatar_url": profile["avatar_url"],
                "display_avatar_url": profile["display_avatar_url"],
                "initial": pet_name[0].upper(),
                "persona": profile["persona"],
                "total_likes": row["total_likes"] or 0,
                "post_count": row["post_count"] or 0,
                "latest_post": latest_posts.get(profile["username"]),
            }
        )
    return rankings


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


def serialize_bootstrap(page_name, profile, notifications, message_threads):
    return {
        "page": page_name,
        "profile": profile,
        "notifications": notifications,
        "notification_unread_count": get_unread_notification_count(profile["username"]),
        "message_unread_count": get_unread_message_count(profile["username"]),
        "message_threads": message_threads,
    }
