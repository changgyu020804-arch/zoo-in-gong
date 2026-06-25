from text_utils import clean_single_line_text

PERSONA_BASE_ORDER = ("leader", "detective", "striker", "companion", "spotlight", "zen")
PERSONA_BASE_STORAGE = {
    "leader": ("outdoor", "social"),
    "detective": ("outdoor", "selective"),
    "striker": ("indoor", "social"),
    "companion": ("indoor", "selective"),
    "spotlight": ("spotlight", "social"),
    "zen": ("zen", "social"),
}


def _option(value, label, scores, *, focus=None, legacy=None):
    return {
        "value": value,
        "label": label,
        "scores": scores,
        "focus": focus or {},
        "legacy": legacy or {},
    }


PERSONA_QUESTIONS = [
    {
        "key": "persona_q1",
        "title": "산책 중 처음 보는 길이 나타나면?",
        "options": [
            _option("lead", "망설임 없이 앞장서요", {"leader": 2, "detective": 1}, legacy={"persona_curiosity": "explorer", "persona_reaction": "brave"}),
            _option("inspect", "냄새부터 꼼꼼히 조사해요", {"detective": 2, "leader": 1}, legacy={"persona_curiosity": "explorer", "persona_reaction": "cautious"}),
            _option("check_owner", "집사 반응을 먼저 살펴봐요", {"companion": 2, "zen": 1}, legacy={"persona_curiosity": "steady", "persona_reaction": "cautious"}),
            _option("stay_route", "익숙한 길을 계속 걸어요", {"zen": 2, "companion": 1}, legacy={"persona_curiosity": "steady", "persona_routine": "routine"}),
        ],
    },
    {
        "key": "persona_q2",
        "title": "처음 보는 강아지가 다가오면?",
        "options": [
            _option("greet", "먼저 다가가 인사해요", {"leader": 2, "striker": 1}, legacy={"persona_expression": "affectionate", "persona_reaction": "brave"}),
            _option("play_invite", "꼬리를 흔들며 놀자고 해요", {"striker": 2, "leader": 1}, focus={"play": 1}, legacy={"persona_expression": "affectionate", "persona_voice": "chatty"}),
            _option("observe", "거리를 두고 천천히 관찰해요", {"detective": 2, "companion": 1}, legacy={"persona_expression": "cool", "persona_reaction": "cautious"}),
            _option("owner_side", "집사 옆에서 상황을 지켜봐요", {"companion": 2, "zen": 1}, legacy={"persona_cuddle": "cuddly", "persona_expression": "cool"}),
        ],
    },
    {
        "key": "persona_q3",
        "title": "자유 시간이 생기면 가장 하고 싶은 것은?",
        "options": [
            _option("walk", "밖으로 나가 신나게 걸어요", {"leader": 2, "detective": 1}, focus={"play": 1}, legacy={"persona_routine": "free"}),
            _option("search", "새 냄새와 장소를 찾아봐요", {"detective": 2, "leader": 1}, legacy={"persona_curiosity": "explorer"}),
            _option("people", "사람들 사이에서 관심받아요", {"spotlight": 2, "striker": 1}, legacy={"persona_style": "flashy", "persona_voice": "chatty"}),
            _option("rest", "편한 자리에서 조용히 쉬어요", {"zen": 2, "companion": 1}, legacy={"persona_routine": "routine", "persona_voice": "quiet"}),
        ],
    },
    {
        "key": "persona_q4",
        "title": "집사가 다른 강아지를 예뻐하면?",
        "options": [
            _option("join", "나도 사이에 들어가 함께 놀아요", {"striker": 2, "leader": 1}, focus={"play": 1}, legacy={"persona_expression": "affectionate", "persona_voice": "chatty"}),
            _option("appeal", "더 귀여운 행동으로 시선을 가져와요", {"spotlight": 2, "striker": 1}, legacy={"persona_style": "flashy", "persona_expression": "affectionate"}),
            _option("cling", "집사 곁에 바짝 붙어 있어요", {"companion": 2, "striker": 1}, legacy={"persona_cuddle": "cuddly"}),
            _option("wait", "신경 쓰지 않고 차분히 기다려요", {"zen": 2, "detective": 1}, legacy={"persona_cuddle": "independent", "persona_voice": "quiet"}),
        ],
    },
    {
        "key": "persona_q5",
        "title": "집사가 카메라를 들면?",
        "options": [
            _option("pose", "바로 표정과 포즈를 준비해요", {"spotlight": 2, "striker": 1}, legacy={"persona_style": "flashy", "persona_voice": "chatty"}),
            _option("approach", "카메라보다 집사에게 다가가요", {"striker": 2, "companion": 1}, legacy={"persona_expression": "affectionate", "persona_cuddle": "cuddly"}),
            _option("inspect_camera", "카메라가 뭔지 냄새 맡아봐요", {"detective": 2, "leader": 1}, legacy={"persona_curiosity": "explorer"}),
            _option("natural", "하던 행동을 편안하게 계속해요", {"zen": 2, "companion": 1}, legacy={"persona_style": "natural", "persona_voice": "quiet"}),
        ],
    },
    {
        "key": "persona_q6",
        "title": "예정에 없던 일이 생기면?",
        "options": [
            _option("enjoy_change", "새로운 일이라 더 신나요", {"leader": 2, "spotlight": 1}, legacy={"persona_routine": "free", "persona_reaction": "brave"}),
            _option("analyze_change", "무슨 상황인지 먼저 파악해요", {"detective": 2, "zen": 1}, legacy={"persona_reaction": "cautious", "persona_curiosity": "explorer"}),
            _option("follow_owner", "집사와 함께라면 따라가요", {"companion": 2, "striker": 1}, legacy={"persona_cuddle": "cuddly"}),
            _option("prefer_plan", "원래 하던 일정이 더 좋아요", {"zen": 2, "companion": 1}, legacy={"persona_routine": "routine"}),
        ],
    },
    {
        "key": "persona_q7",
        "title": "낯선 소리가 들리면?",
        "options": [
            _option("check_sound", "바로 달려가 확인해요", {"leader": 2, "detective": 1}, legacy={"persona_reaction": "brave", "persona_voice": "chatty"}),
            _option("listen", "멈춰서 소리의 정체를 살펴요", {"detective": 2, "zen": 1}, legacy={"persona_reaction": "cautious", "persona_voice": "quiet"}),
            _option("call_owner", "집사에게 가까이 붙어요", {"companion": 2, "striker": 1}, legacy={"persona_cuddle": "cuddly", "persona_reaction": "cautious"}),
            _option("ignore_sound", "금방 진정하고 하던 일을 해요", {"zen": 2, "leader": 1}, legacy={"persona_reaction": "brave", "persona_voice": "quiet"}),
        ],
    },
    {
        "key": "persona_q8",
        "title": "가장 편안하게 쉬는 자리는?",
        "options": [
            _option("center", "모두가 나를 볼 수 있는 한가운데", {"spotlight": 2, "striker": 1}, legacy={"persona_style": "flashy", "persona_cuddle": "independent"}),
            _option("owner_lap", "집사 품이나 바로 옆자리", {"companion": 2, "striker": 1}, legacy={"persona_cuddle": "cuddly", "persona_expression": "affectionate"}),
            _option("window", "밖을 관찰할 수 있는 창가", {"detective": 2, "leader": 1}, legacy={"persona_curiosity": "explorer", "persona_cuddle": "independent"}),
            _option("quiet_corner", "조용하고 익숙한 나만의 자리", {"zen": 2, "companion": 1}, legacy={"persona_routine": "routine", "persona_style": "natural"}),
        ],
    },
    {
        "key": "persona_q9",
        "title": "새 장난감을 받으면?",
        "options": [
            _option("start_game", "바로 물고 놀이를 시작해요", {"leader": 2, "striker": 1}, focus={"play": 2}, legacy={"persona_reaction": "brave", "persona_voice": "chatty"}),
            _option("study_toy", "냄새와 모양부터 연구해요", {"detective": 2, "zen": 1}, focus={"play": 1}, legacy={"persona_curiosity": "explorer", "persona_reaction": "cautious"}),
            _option("show_toy", "사람들에게 보여주며 자랑해요", {"spotlight": 2, "striker": 1}, focus={"play": 1}, legacy={"persona_style": "flashy", "persona_voice": "chatty"}),
            _option("play_together", "집사가 움직여 줄 때까지 기다려요", {"companion": 2, "zen": 1}, focus={"play": 1}, legacy={"persona_cuddle": "cuddly"}),
        ],
    },
    {
        "key": "persona_q10",
        "title": "사람과 강아지가 많은 장소에서는?",
        "options": [
            _option("lead_group", "신나게 돌아다니며 분위기를 이끌어요", {"leader": 2, "spotlight": 1}, legacy={"persona_voice": "chatty", "persona_reaction": "brave"}),
            _option("make_friends", "여기저기 다니며 친구를 만들어요", {"striker": 2, "leader": 1}, legacy={"persona_expression": "affectionate", "persona_voice": "chatty"}),
            _option("enjoy_attention", "사람들의 관심과 칭찬을 즐겨요", {"spotlight": 2, "striker": 1}, legacy={"persona_style": "flashy"}),
            _option("stay_calm", "조용한 곳을 찾아 편하게 있어요", {"zen": 2, "companion": 1}, legacy={"persona_voice": "quiet", "persona_style": "natural"}),
        ],
    },
    {
        "key": "persona_q11",
        "title": "간식과 장난감을 동시에 보여주면?",
        "options": [
            _option("choose_snack", "고민 없이 간식부터 골라요", {"companion": 1, "zen": 1}, focus={"snack": 3}),
            _option("choose_toy", "장난감을 물고 놀자고 해요", {"leader": 1, "striker": 1}, focus={"play": 3}),
            _option("choose_owner", "집사가 주는 쪽을 기다려요", {"companion": 2, "zen": 1}, focus={"snack": 1, "play": 1}, legacy={"persona_cuddle": "cuddly"}),
        ],
    },
    {
        "key": "persona_q12",
        "title": "가장 기분 좋은 보상은?",
        "options": [
            _option("food_reward", "맛있는 간식 한 입", {"zen": 1}, focus={"snack": 3}),
            _option("active_reward", "공놀이와 신나는 장난", {"leader": 1, "striker": 1}, focus={"play": 3}),
            _option("praise_reward", "모두의 칭찬과 박수", {"spotlight": 2, "striker": 1}, focus={"snack": 1, "play": 1}, legacy={"persona_style": "flashy"}),
            _option("cuddle_reward", "집사와 포근하게 붙어 있기", {"companion": 2, "zen": 1}, focus={"snack": 1}, legacy={"persona_cuddle": "cuddly"}),
        ],
    },
]


# These columns already exist in the users table. Scored questionnaire answers are
# converted to this compact representation so existing accounts and deployments
# remain compatible.
PERSONA_KEYS = [
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

PERSONA_TRAIT_LABELS = {
    "persona_energy": {
        "outdoor": ("밖이 좋아요", "바깥 활동과 새로운 자극에서 에너지를 얻어요."),
        "indoor": ("집이 좋아요", "익숙한 공간과 가까운 관계에서 편안함을 느껴요."),
        "spotlight": ("관심이 좋아요", "칭찬과 시선을 받을 때 매력이 더 살아나요."),
        "zen": ("평화가 좋아요", "조용하고 안정적인 흐름을 좋아해요."),
    },
    "persona_social": {
        "social": ("먼저 인사해요", "친구나 사람과 먼저 교류하는 편이에요."),
        "selective": ("천천히 살펴봐요", "상대를 살핀 뒤 천천히 가까워져요."),
    },
    "persona_curiosity": {
        "explorer": ("구석구석 탐험해요", "새로운 장소와 물건을 적극적으로 살펴봐요."),
        "steady": ("익숙한 동선이 편해요", "익숙한 환경과 동선에서 편안함을 느껴요."),
    },
    "persona_expression": {
        "affectionate": ("애교 직진형", "몸짓과 행동으로 마음을 잘 보여줘요."),
        "cool": ("도도 관찰형", "조용히 곁을 지키며 마음을 표현해요."),
    },
    "persona_focus": {
        "snack": ("간식파", "맛있는 보상에 동기부여를 크게 받아요."),
        "play": ("놀이파", "장난감과 함께하는 놀이를 특히 좋아해요."),
    },
    "persona_reaction": {
        "brave": ("바로 확인하러 가요", "낯선 자극에도 비교적 빠르게 다가가요."),
        "cautious": ("먼저 거리부터 둬요", "상황을 충분히 살핀 뒤 움직여요."),
    },
    "persona_routine": {
        "routine": ("정해진 루틴 선호", "예측 가능한 일과에서 안정감을 얻어요."),
        "free": ("즉흥적인 변화 선호", "새로운 일정과 즉흥적인 활동도 즐겨요."),
    },
    "persona_voice": {
        "chatty": ("표현이 많은 편", "소리와 움직임으로 기분을 잘 드러내요."),
        "quiet": ("표현이 잔잔한 편", "눈빛과 작은 몸짓으로 차분하게 반응해요."),
    },
    "persona_cuddle": {
        "cuddly": ("항상 붙어 있고 싶어요", "집사와 가까이 있을 때 안심해요."),
        "independent": ("혼자만의 시간도 필요해요", "혼자 쉬는 시간과 공간도 중요해요."),
    },
    "persona_style": {
        "flashy": ("시선 강탈형", "표정과 포즈로 존재감을 잘 드러내요."),
        "natural": ("꾸안꾸 자연형", "꾸미지 않은 편안한 순간에 매력이 살아나요."),
    },
}


def get_default_avatar_url(profile):
    focus = profile.get("persona_focus") or "snack"
    suffix = "play" if focus == "play" else "snack"
    return f"/static/images/persona-avatars/zen-{suffix}.png"


def persona_defaults():
    return {
        "persona_energy": "outdoor",
        "persona_social": "social",
        "persona_curiosity": "explorer",
        "persona_expression": "affectionate",
        "persona_focus": "snack",
        "persona_reaction": "brave",
        "persona_routine": "routine",
        "persona_voice": "chatty",
        "persona_cuddle": "cuddly",
        "persona_style": "natural",
    }


def get_selected_option(question, value):
    for option in question["options"]:
        if option["value"] == value:
            return option
    return question["options"][0]


def score_persona_answers(source):
    base_scores = {name: 0 for name in PERSONA_BASE_ORDER}
    focus_scores = {"snack": 0, "play": 0}
    legacy = persona_defaults()
    answered = 0

    for question in PERSONA_QUESTIONS:
        raw_value = source.get(question["key"], "")
        option = next((item for item in question["options"] if item["value"] == raw_value), None)
        if not option:
            continue
        answered += 1
        for name, points in option["scores"].items():
            base_scores[name] += points
        for name, points in option["focus"].items():
            focus_scores[name] += points
        legacy.update(option["legacy"])

    winner = max(PERSONA_BASE_ORDER, key=lambda name: base_scores[name])
    energy, social = PERSONA_BASE_STORAGE[winner]
    legacy["persona_energy"] = energy
    legacy["persona_social"] = social
    legacy["persona_focus"] = "play" if focus_scores["play"] > focus_scores["snack"] else "snack"
    return legacy, base_scores, focus_scores, answered

def derive_persona_details(profile):
    values = {key: profile.get(key) or persona_defaults()[key] for key in PERSONA_KEYS}
    selected = [
        {
            "key": key,
            "title": label,
            "label": label,
            "description": description,
        }
        for key, value in values.items()
        for label, description in [PERSONA_TRAIT_LABELS[key][value]]
    ]

    base_map = {
        ("outdoor", "social"): "산책 리더형",
        ("outdoor", "selective"): "탐험 탐정형",
        ("indoor", "social"): "애교 스트라이커형",
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
        "spotlight": "시선강탈 스타형",
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
    answers, _base_scores, _focus_scores, _answered = score_persona_answers(source)
    return answers
