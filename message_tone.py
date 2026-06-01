import re

from text_utils import clean_single_line_text, meaningful_text_length, soften_walk_terms


COMMON_REWRITES = {
    "안녕하세요": ["안녕하시나멍", "안녕하시개", "반갑다멍"],
    "안녕": ["안녕하개", "안녕멍", "반가워멍"],
    "하이": ["하이멍", "하이하개", "반갑다멍"],
    "뭐해": ["뭐하개?", "지금 뭐하나멍?", "꼬리 흔들 시간 있개?"],
    "뭐해?": ["뭐하개?", "지금 뭐하나멍?", "꼬리 흔들 시간 있개?"],
    "심심해": ["심심함이 꼬리까지 내려왔개", "재미 긴급 호출하개", "이 무료한 공기를 흔들어보자멍"],
    "심심해요": ["심심함이 꼬리까지 내려왔개", "재미 긴급 호출하개", "이 무료한 공기를 흔들어보자멍"],
    "좋아": ["좋다멍", "좋아하개", "내 마음이 꼬리 흔든다멍"],
    "고마워": ["고맙다멍", "고맙개", "내 꼬리가 고맙다고 흔들린다멍"],
    "고마워요": ["고맙다멍", "고맙습니다개", "내 꼬리가 고맙다고 흔들린다멍"],
    "보고싶어": ["보고 싶었개", "보고 싶다멍", "네 냄새가 그리웠개"],
    "놀자": ["같이 놀자멍", "놀 준비 됐개?", "장난감이 나를 부른다개"],
    "산책가자": ["발바닥 시간 어때멍?", "밖에 재미 냄새 맡으러 가자개", "문 앞에서 꼬리 대기 중이개"],
    "밥먹자": ["밥 먹자멍", "맛있는 시간 시작하개", "밥그릇 앞으로 출동하개"],
    "잘자": ["잘 자라멍", "좋은 꿈 꾸개", "포근하게 쉬자멍"],
    "사진봐줘": ["이 사진 심사 부탁하개", "내 포즈값 확인해주라멍", "집사 카메라 결과물 봐주개"],
    "사진 봐줘": ["이 사진 심사 부탁하개", "내 포즈값 확인해주라멍", "집사 카메라 결과물 봐주개"],
}


PERSONALITY_FLAVORS = {
    "장난꾸러기": ["쉿, 이건 장난 아니고 작전이개", "꼬리가 먼저 들켰다멍", "아무 일도 없었던 척하개", "증거는 없고 귀여움만 있개"],
    "차분한": ["천천히 말하개", "조용히 반갑다멍", "마음 편하게 있자개"],
    "애교많은": ["집사야, 나 좀 봐주라개", "쓰담도 같이 주면 좋겠다멍", "꼬옥 옆에 있을래", "눈빛 서비스 들어간다멍"],
    "호기심 많은": ["이건 좀 궁금하개", "새 냄새 확인하러 가자멍", "따라가 봐도 되개?", "수상한 재미 냄새가 나개"],
    "용감한": ["씩씩하게 가보자개", "내가 먼저 확인하겠다멍", "괜찮아, 출동하개"],
    "소심한": ["천천히 와주면 좋겠개", "조금 조심스럽지만 반갑다멍", "옆에 있으면 괜찮개"],
    "활발한": ["바로 출발하개", "신난다멍", "한 번 더 하자개", "꼬리 엔진 켜졌개"],
    "느긋한": ["천천히 해도 좋다멍", "햇볕처럼 느긋하개", "급하지 않게 가자개"],
    "똑똑한": ["판단 완료했개", "상황 파악했다멍", "이건 꽤 좋은 선택이개", "내 머릿속 회의 통과했개"],
    "먹보": ["맛있는 냄새가 스친다멍", "코가 먼저 반응했개", "한입 생각은 살짝만 하개", "마음속 그릇이 딸랑했개"],
}


PERSONA_FLAVORS = [
    ("산책 리더형", ["발바닥 회의는 내가 열었개", "집사 손 잡고 나가자멍", "바깥 구경 준비 끝났개"]),
    ("탐험 탐정형", ["수상한 냄새 단서 발견했개", "현장 조사하러 가자멍", "이건 확인이 필요하개"]),
    ("애교 스트라이커형", ["눈빛 발사하개", "꼬리로 먼저 인사한다멍", "쓰담 받을 준비 됐개"]),
    ("집사 껌딱지형", ["가까이서 말하개", "옆에 있어주면 좋겠다멍", "집사 옆이면 더 좋개"]),
    ("인정욕구형", ["오늘의 주인공 등장하개", "칭찬 준비됐나멍", "박수 받을 준비 끝났개"]),
    ("평화주의 명상형", ["천천히 인사하개", "바람처럼 반갑다멍", "조용히 꼬리 흔든다개"]),
]


FOCUS_FLAVORS = {
    "간식파": ["코끝이 먼저 반응했다멍", "한입 생각은 나중에 하개", "눈빛 협상은 잠깐만 열어두개"],
    "놀이파": ["장난감도 같이 출동하개", "한 번 더 놀 준비 됐멍", "발바닥 엔진 예열 끝났개"],
}

SHORT_TONE_ENDINGS = (
    "꼬리로 바로 접수했개",
    "발바닥까지 기분이 전해졌멍",
    "내 마음이 먼저 반응했개",
)


def _compact_message(body):
    text = clean_single_line_text(body, 120)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_key(text):
    return re.sub(r"[\s!~.,]+", "", text).strip()


def _with_dog_ending(text):
    text = text.strip()
    if not text:
        return ""
    if any(token in text for token in ("멍", "개", "하개", "다멍")):
        return text

    if text.endswith("?"):
        base = text[:-1].strip()
        return f"{base}하개?"
    if text.endswith(("요", "여")):
        return f"{text[:-1]}다멍"
    if text.endswith(("다", "어", "아")):
        return f"{text}멍"
    return f"{text}멍"


def _soften_plain_korean(text):
    replacements = [
        ("하세요", "하시개"),
        ("해줘", "해주라멍"),
        ("할래", "할래멍"),
        ("갈래", "갈래멍"),
        ("가자", "가자멍"),
        ("좋아", "좋다멍"),
        ("고마워", "고맙다멍"),
    ]
    result = text
    for before, after in replacements:
        if before in result:
            result = result.replace(before, after)
    return result if result != text else ""


def _persona_flavor(persona):
    for keyword, flavors in PERSONA_FLAVORS:
        if keyword in (persona or ""):
            return flavors
    return ["반갑다멍", "안녕하개", "꼬리 흔든다멍"]


def _focus_flavor(persona):
    for keyword, flavors in FOCUS_FLAVORS.items():
        if keyword in (persona or ""):
            return flavors
    return []


def _personality_flavor(personality):
    return PERSONALITY_FLAVORS.get(personality or "", [])


def _dedupe(items, limit=3):
    result = []
    seen = set()
    for index, item in enumerate(items):
        value = clean_single_line_text(_soften_overused_terms(item), 90).strip()
        value = _expand_short_tone(value, index)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _soften_overused_terms(text):
    return soften_walk_terms(text)


def _is_tone_too_short(text, min_chars=8):
    return meaningful_text_length(text, normalize=False) < min_chars


def _expand_short_tone(text, seed=0):
    value = clean_single_line_text(text, 90)
    if not value or not _is_tone_too_short(value):
        return value

    ending = SHORT_TONE_ENDINGS[seed % len(SHORT_TONE_ENDINGS)]
    if value.endswith("?"):
        return f"{value} {ending}?"
    return f"{value}, {ending}"


def suggest_message_tones(sender_profile, body, limit=3):
    original = _compact_message(body)
    if not original:
        return []

    persona = sender_profile.get("persona") or ""
    personality = sender_profile.get("personality") or ""
    pet_name = sender_profile.get("pet_name") or ""
    key = _normalize_key(original)

    candidates = []
    candidates.extend(COMMON_REWRITES.get(key, []))

    softened = _soften_plain_korean(original)
    if softened:
        candidates.append(softened)

    dog_ending = _with_dog_ending(original)
    if dog_ending:
        candidates.append(dog_ending)

    persona_flavors = _persona_flavor(persona)
    personality_flavors = _personality_flavor(personality)
    focus_flavors = _focus_flavor(persona)

    if key in {"안녕하세요", "안녕", "하이"}:
        candidates.append(persona_flavors[0])
        if personality_flavors:
            candidates.append(personality_flavors[0])
    elif key in {"뭐해", "뭐해?"}:
        candidates.append(f"지금 뭐하개? {persona_flavors[0]}")
    elif key in {"놀자", "산책가자"} and focus_flavors:
        candidates.append(f"{dog_ending} {focus_flavors[0]}")
    elif personality_flavors:
        candidates.append(f"{dog_ending} {personality_flavors[0]}")

    if focus_flavors:
        candidates.append(f"{dog_ending} {focus_flavors[0]}")
    if pet_name:
        candidates.append(f"{pet_name} 말투로 바꾸면, {dog_ending}")

    return _dedupe(candidates, limit=limit)
