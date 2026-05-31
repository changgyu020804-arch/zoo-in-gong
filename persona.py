from text_utils import clean_single_line_text

PERSONA_QUESTIONS = [
    {
        "key": "persona_energy",
        "title": "가장 가까운 기본 에너지는?",
        "options": [
            {"value": "outdoor", "label": "밖이 좋아요", "description": "새 냄새와 긴 산책이 있어야 텐션이 올라가요."},
            {"value": "indoor", "label": "집이 좋아요", "description": "익숙한 공간에서 느긋하게 쉬는 시간이 더 좋아요."},
            {"value": "spotlight", "label": "관심이 좋아요", "description": "시선을 받으면 텐션이 확 올라가는 열정적인 타입이에요."},
            {"value": "zen", "label": "평화가 좋아요", "description": "조용한 리듬과 느긋한 시간을 즐기는 명상 타입이에요."},
        ],
    },
    {
        "key": "persona_social",
        "title": "처음 보는 강아지를 만나면?",
        "options": [
            {"value": "social", "label": "먼저 인사해요", "description": "새 친구를 보면 먼저 다가가 보는 편이에요."},
            {"value": "selective", "label": "천천히 살펴봐요", "description": "마음 맞는 친구와 깊게 친해지는 타입이에요."},
        ],
    },
    {
        "key": "persona_curiosity",
        "title": "낯선 장소에서는 어떻게 움직이나요?",
        "options": [
            {"value": "explorer", "label": "구석구석 탐험해요", "description": "새로운 길과 냄새를 그냥 지나치지 못해요."},
            {"value": "steady", "label": "익숙한 동선이 편해요", "description": "안정적인 루틴이 있으면 훨씬 편안해져요."},
        ],
    },
    {
        "key": "persona_expression",
        "title": "집사에게 애정을 표현할 때는?",
        "options": [
            {"value": "affectionate", "label": "애교 직진형", "description": "꼬리 흔들기와 안기기를 아낌없이 보여줘요."},
            {"value": "cool", "label": "도도 관찰형", "description": "조용하지만 은근히 곁을 지키는 편이에요."},
        ],
    },
    {
        "key": "persona_focus",
        "title": "하루 중 제일 기다려지는 순간은?",
        "options": [
            {"value": "snack", "label": "간식 시간", "description": "맛있는 한 입이 하루 만족도를 확 올려줘요."},
            {"value": "play", "label": "놀이 시간", "description": "공놀이와 장난감이 최고의 이벤트예요."},
        ],
    },
    {
        "key": "persona_reaction",
        "title": "큰 소리나 낯선 자극이 오면?",
        "options": [
            {"value": "brave", "label": "바로 확인하러 가요", "description": "무슨 일인지 직접 봐야 마음이 놓여요."},
            {"value": "cautious", "label": "먼저 거리부터 둬요", "description": "상황을 먼저 읽고 천천히 움직이는 편이에요."},
        ],
    },
    {
        "key": "persona_routine",
        "title": "하루 루틴은 어느 쪽이 더 잘 맞나요?",
        "options": [
            {"value": "routine", "label": "정해진 루틴 선호", "description": "산책, 식사, 낮잠 시간이 일정하면 안정감이 커요."},
            {"value": "free", "label": "즉흥적인 변화 선호", "description": "그날그날 다른 코스와 분위기도 좋아해요."},
        ],
    },
    {
        "key": "persona_voice",
        "title": "기분 좋을 때 표현 방식은?",
        "options": [
            {"value": "chatty", "label": "표현이 많은 편", "description": "소리와 움직임으로 리액션을 확실하게 보여줘요."},
            {"value": "quiet", "label": "표현이 잔잔한 편", "description": "몸짓과 눈빛으로 조용하게 반응해요."},
        ],
    },
    {
        "key": "persona_cuddle",
        "title": "집사와 붙어 있는 시간은?",
        "options": [
            {"value": "cuddly", "label": "항상 붙어 있고 싶어요", "description": "가까이 붙어 있을수록 마음이 편해져요."},
            {"value": "independent", "label": "혼자만의 시간도 필요해요", "description": "적당한 거리감을 유지할 때 더 안정적이에요."},
        ],
    },
    {
        "key": "persona_style",
        "title": "사진 찍을 때 더 잘 나오는 분위기는?",
        "options": [
            {"value": "flashy", "label": "시선 강탈형", "description": "표정과 포즈가 화려해서 카메라를 잘 받아요."},
            {"value": "natural", "label": "꾸안꾸 자연형", "description": "힘 빼고 있을 때 오히려 분위기가 더 살아나요."},
        ],
    },
]


PERSONA_KEYS = [question["key"] for question in PERSONA_QUESTIONS]


def get_default_avatar_url(profile):
    focus = profile.get("persona_focus") or "snack"
    suffix = "play" if focus == "play" else "snack"
    return f"/static/images/persona-avatars/zen-{suffix}.png"


def persona_defaults():
    return {question["key"]: question["options"][0]["value"] for question in PERSONA_QUESTIONS}


def get_selected_option(question, value):
    for option in question["options"]:
        if option["value"] == value:
            return option
    return question["options"][0]

def derive_persona_details(profile):
    values = {key: profile.get(key) or persona_defaults()[key] for key in PERSONA_KEYS}
    selected = []
    for question in PERSONA_QUESTIONS:
        option = get_selected_option(question, values[question["key"]])
        selected.append(
            {
                "key": question["key"],
                "title": question["title"],
                "label": option["label"],
                "description": option["description"],
            }
        )

    base_map = {
        ("outdoor", "social"): "산책 리더형",
        ("outdoor", "selective"): "탐험 파트너형",
        ("indoor", "social"): "애교 네트워커형",
        ("indoor", "selective"): "집사 껌딱지형",
    }
    focus_map = {"snack": "간식파", "play": "놀이파"}
    mood_map = {
        ("flashy", "chatty"): "시선강탈형",
        ("flashy", "quiet"): "무드모델형",
        ("natural", "chatty"): "꾸밈없는 매력형",
        ("natural", "quiet"): "잔잔한 분위기형",
    }

    special_base_map = {
        "spotlight": "열정적 관종형",
        "zen": "평화주의 명상형",
    }
    if values["persona_energy"] in special_base_map:
        base_label = special_base_map[values["persona_energy"]]
    else:
        base_label = base_map[(values["persona_energy"], values["persona_social"])]
    persona_label = f"{base_label} {focus_map[values['persona_focus']]}"
    mood_label = mood_map[(values["persona_style"], values["persona_voice"])]

    summary_parts = [
        f"{profile['pet_name']}는 {persona_label}에 가까운 강아지예요.",
        "새로운 환경에 강하게 끌리는 편이에요."
        if values["persona_curiosity"] == "explorer"
        else "익숙한 루틴이 있을 때 훨씬 편안해져요.",
        "애정 표현이 적극적이고 밀착도가 높은 편이에요."
        if values["persona_expression"] == "affectionate" and values["persona_cuddle"] == "cuddly"
        else "집사에게 착 붙어 자기 방식대로 애정을 보여주는 타입이에요.",
        "갑작스러운 자극에도 바로 반응하는 담대한 성향이에요."
        if values["persona_reaction"] == "brave"
        else "상황을 먼저 읽고 천천히 움직이는 신중한 스타일이에요.",
        f"전체 무드는 {mood_label}에 가까워요.",
    ]

    owner_note = clean_single_line_text(profile.get("owner_persona_note") or "", 160)
    if owner_note:
        summary_parts.append(f"집사가 보는 한 줄 메모는 '{owner_note}'예요.")

    return {
        "persona": persona_label,
        "persona_summary": " ".join(summary_parts),
        "persona_traits": selected,
        "persona_answers": values,
    }


def enrich_profile(profile):
    details = derive_persona_details(profile)
    profile.update(details["persona_answers"])
    profile["persona"] = details["persona"]
    profile["persona_summary"] = details["persona_summary"]
    profile["persona_traits"] = details["persona_traits"]
    profile["handle"] = f"@{profile['username']}"
    profile["initial"] = (profile["pet_name"] or profile["username"] or "멍")[0].upper()
    profile["default_avatar_url"] = get_default_avatar_url(profile)
    profile["display_avatar_url"] = profile.get("avatar_url") or profile["default_avatar_url"]
    return profile


def build_default_profile(username):
    defaults = persona_defaults()
    return enrich_profile(
        {
            "username": username or "guest",
            "pet_name": username or "멍스타",
            "pet_species": "강아지",
            "pet_age": 2,
            "activity_level": "보통",
            "pet_likes": "간식, 공놀이, 냄새 맡기",
            "pet_dislikes": "목욕, 드라이기",
            "avatar_url": "",
            "bio": "오늘도 귀엽고 부지런하게 일상을 기록하는 강아지 계정이에요.",
            "status_message": "산책 메이트 구함",
            "favorite_place": "동네 공원",
            "personality": "",
            "owner_persona_note": "",
            **defaults,
        }
    )


def row_to_profile(row, username=None):
    if not row:
        return build_default_profile(username)

    base = build_default_profile(username or row["username"])
    profile = {
        "username": row["username"],
        "pet_name": row["pet_name"] or base["pet_name"],
        "pet_species": row["pet_species"] or base["pet_species"],
        "pet_age": row["pet_age"] if row["pet_age"] is not None else base["pet_age"],
        "activity_level": row["activity_level"] or base["activity_level"],
        "pet_likes": row["pet_likes"] or base["pet_likes"],
        "pet_dislikes": row["pet_dislikes"] or base["pet_dislikes"],
        "avatar_url": row["avatar_url"] or base["avatar_url"],
        "bio": row["bio"] or base["bio"],
        "status_message": row["status_message"] or base["status_message"],
        "favorite_place": row["favorite_place"] or base["favorite_place"],
        "personality": row["personality"] or base["personality"],
        "owner_persona_note": row["owner_persona_note"] or "",
    }
    for key in PERSONA_KEYS:
        profile[key] = row[key] or base[key]
    return enrich_profile(profile)

def extract_persona_answers(source):
    answers = {}
    defaults = persona_defaults()
    for question in PERSONA_QUESTIONS:
        raw_value = source.get(question["key"], defaults[question["key"]])
        allowed_values = {option["value"] for option in question["options"]}
        answers[question["key"]] = raw_value if raw_value in allowed_values else defaults[question["key"]]
    return answers
