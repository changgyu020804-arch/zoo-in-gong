import re


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
