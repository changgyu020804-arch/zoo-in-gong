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
    "persona_social": "친구 관계",
    "persona_curiosity": "호기심",
    "persona_expression": "애정 표현",
    "persona_focus": "하루의 즐거움",
    "persona_reaction": "반응 방식",
    "persona_routine": "루틴",
    "persona_voice": "표현 방식",
    "persona_cuddle": "스킨십",
    "persona_style": "사진 무드",
}

MATCH_FIELD_WEIGHTS = {
    "persona_energy": 13,
    "persona_social": 14,
    "persona_curiosity": 10,
    "persona_expression": 8,
    "persona_focus": 10,
    "persona_reaction": 12,
    "persona_routine": 11,
    "persona_voice": 6,
    "persona_cuddle": 10,
    "persona_style": 6,
}

MATCH_DIFFERENCE_COMPATIBILITY = {
    "persona_energy": {
        frozenset(("outdoor", "indoor")): 0.48,
        frozenset(("outdoor", "spotlight")): 0.78,
        frozenset(("outdoor", "zen")): 0.5,
        frozenset(("indoor", "spotlight")): 0.72,
        frozenset(("indoor", "zen")): 0.86,
        frozenset(("spotlight", "zen")): 0.58,
    },
    "persona_social": {frozenset(("social", "selective")): 0.68},
    "persona_curiosity": {frozenset(("explorer", "steady")): 0.58},
    "persona_expression": {frozenset(("affectionate", "cool")): 0.7},
    "persona_focus": {frozenset(("snack", "play")): 0.62},
    "persona_reaction": {frozenset(("brave", "cautious")): 0.58},
    "persona_routine": {frozenset(("routine", "free")): 0.48},
    "persona_voice": {frozenset(("chatty", "quiet")): 0.62},
    "persona_cuddle": {frozenset(("cuddly", "independent")): 0.48},
    "persona_style": {frozenset(("flashy", "natural")): 0.68},
}

MATCH_COMPLEMENT_MESSAGES = {
    "persona_energy": "활동 리듬이 서로 균형을 잡아줘요",
    "persona_social": "한쪽이 먼저 다가가고 한쪽이 천천히 마음을 열어요",
    "persona_curiosity": "탐험과 안정감이 적당히 섞여요",
    "persona_expression": "서로 다른 애정 표현을 알아가는 재미가 있어요",
    "persona_focus": "간식과 놀이 취향을 함께 즐길 수 있어요",
    "persona_reaction": "대담함과 신중함이 서로를 보완해요",
    "persona_routine": "계획과 즉흥성이 균형을 이뤄요",
    "persona_voice": "표현의 강약이 자연스럽게 맞아요",
    "persona_cuddle": "가까움과 혼자 쉬는 시간을 조절할 수 있어요",
    "persona_style": "사진 분위기가 서로 다르게 빛나요",
}

ACTIVITY_LEVELS = {"낮음": 0, "보통": 1, "높음": 2}

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


def build_match_summary(viewer_profile, target_profile, highlights):
    if not viewer_profile or not target_profile:
        return "프로필을 조금 더 채우면 더 정확하게 추천할 수 있어요."

    if len(highlights) >= 2:
        return f"{highlights[0]} {highlights[1]}"
    if highlights:
        return f"{highlights[0]} 천천히 인사해 보기 좋은 친구예요."

    return f"{target_profile.get('persona') or '비슷한 분위기'} 성향이라 새 친구로 추천해요."


def _field_compatibility(field, viewer_value, target_value):
    if not viewer_value or not target_value:
        return 0.5
    if viewer_value == target_value:
        return 1.0
    return MATCH_DIFFERENCE_COMPATIBILITY.get(field, {}).get(
        frozenset((viewer_value, target_value)),
        0.45,
    )


def _profile_tokens(value):
    tokens = {
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]+", str(value or "").lower())
        if len(token) >= 2
    }
    return tokens


def _shared_profile_tokens(first, second):
    return _profile_tokens(first) & _profile_tokens(second)


def _age_match_points(viewer_age, target_age):
    try:
        gap = abs(int(viewer_age) - int(target_age))
    except (TypeError, ValueError):
        return 2.5, None

    if gap <= 1:
        return 5.0, "나이대가 비슷해요"
    if gap <= 3:
        return 3.5, "나이 차이가 크지 않아요"
    if gap <= 6:
        return 2.0, None
    return 0.5, None


def add_match_info(viewer_profile, target_profile):
    if not viewer_profile or not target_profile:
        target_profile["match_score"] = 0
        target_profile["match_label"] = "새 친구"
        target_profile["match_reasons"] = []
        return target_profile

    exact_fields = []
    complementary_fields = []
    trait_weighted_score = 0.0
    total_trait_weight = sum(MATCH_FIELD_WEIGHTS.values())
    for field in MATCH_FIELDS:
        viewer_value = viewer_profile.get(field)
        target_value = target_profile.get(field)
        compatibility = _field_compatibility(field, viewer_value, target_value)
        trait_weighted_score += compatibility * MATCH_FIELD_WEIGHTS[field]
        if viewer_value and viewer_value == target_value:
            exact_fields.append(field)
        elif compatibility >= 0.68:
            complementary_fields.append((field, compatibility))

    # Detailed temperament accounts for 72% of the total score.
    score = (trait_weighted_score / total_trait_weight) * 72
    highlights = []
    reasons = []

    if exact_fields:
        labels = [MATCH_FIELD_LABELS[field] for field in exact_fields[:2]]
        highlights.append(f"{' · '.join(labels)} 조합이 잘 맞아요.")
        reasons.append(f"핵심 성향 {len(exact_fields)}개가 같아요")

    complementary_fields.sort(key=lambda item: item[1] * MATCH_FIELD_WEIGHTS[item[0]], reverse=True)
    if complementary_fields:
        field = complementary_fields[0][0]
        reasons.append(MATCH_COMPLEMENT_MESSAGES[field])
        if not exact_fields:
            highlights.append(f"{MATCH_COMPLEMENT_MESSAGES[field]}.")

    viewer_activity = ACTIVITY_LEVELS.get(viewer_profile.get("activity_level"))
    target_activity = ACTIVITY_LEVELS.get(target_profile.get("activity_level"))
    if viewer_activity is None or target_activity is None:
        score += 4
    else:
        activity_gap = abs(viewer_activity - target_activity)
        activity_points = {0: 8, 1: 5, 2: 1}[activity_gap]
        score += activity_points
        if activity_gap == 0:
            reasons.append("활동량이 비슷해요")
            highlights.append("함께 움직일 때 속도가 잘 맞아요.")
        elif activity_gap == 1:
            reasons.append("활동량 차이가 적당해요")

    shared_likes = _shared_profile_tokens(
        viewer_profile.get("pet_likes"),
        target_profile.get("pet_likes"),
    )
    viewer_likes = _profile_tokens(viewer_profile.get("pet_likes"))
    target_likes = _profile_tokens(target_profile.get("pet_likes"))
    if shared_likes:
        union_size = max(1, len(viewer_likes | target_likes))
        score += min(8, 4 + (len(shared_likes) / union_size) * 4)
        shared_like = sorted(shared_likes, key=lambda token: (-len(token), token))[0]
        reasons.append(f"{shared_like}을 같이 좋아해요")
        highlights.append(f"{shared_like} 취향도 같아요.")
    elif viewer_likes and target_likes:
        score += 1
    else:
        score += 3

    age_points, age_reason = _age_match_points(
        viewer_profile.get("pet_age"),
        target_profile.get("pet_age"),
    )
    score += age_points
    if age_reason:
        reasons.append(age_reason)

    if (
        viewer_profile.get("pet_species")
        and viewer_profile.get("pet_species") == target_profile.get("pet_species")
    ):
        score += 3
        reasons.append("견종이 같아요")
    else:
        score += 1

    shared_places = _shared_profile_tokens(
        viewer_profile.get("favorite_place"),
        target_profile.get("favorite_place"),
    )
    if shared_places:
        score += 2
        reasons.append("좋아하는 장소가 비슷해요")
    elif viewer_profile.get("favorite_place") and target_profile.get("favorite_place"):
        score += 0.5
    else:
        score += 1

    shared_dislikes = _shared_profile_tokens(
        viewer_profile.get("pet_dislikes"),
        target_profile.get("pet_dislikes"),
    )
    if shared_dislikes:
        score += 2
        reasons.append("불편해하는 상황을 서로 이해하기 쉬워요")
    elif viewer_profile.get("pet_dislikes") and target_profile.get("pet_dislikes"):
        score += 0.5
    else:
        score += 1

    score = max(20, min(round(score), 98))
    if score >= 88:
        label = "찰떡 멍친구"
    elif score >= 74:
        label = "잘 맞는 친구"
    elif score >= 60:
        label = "천천히 친해질 친구"
    else:
        label = "새로 알아갈 친구"

    target_profile["match_score"] = score
    target_profile["match_label"] = label
    target_profile["match_reasons"] = list(dict.fromkeys(reasons))[:3] or ["프로필 분위기를 더 알아가는 중이에요"]
    target_profile["match_summary"] = build_match_summary(
        viewer_profile,
        target_profile,
        list(dict.fromkeys(highlights)),
    )
    return target_profile


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
        "has_pet_profile": bool(profile.get("has_pet_profile", True)),
        "pet_onboarding_url": "/pet-onboarding",
    }
