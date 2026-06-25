import re

from text_utils import clean_single_line_text


COMMON_REWRITES = {
    "안녕하세요": ["안녕하개", "안녕하세요멍", "반갑개"],
    "안녕": ["안녕하개", "안녕멍", "반갑개"],
    "하이": ["하이멍", "반갑개", "안녕하개"],
    "뭐해": ["뭐하개?", "뭐 하냐멍?", "지금 뭐 해멍?"],
    "심심해": ["심심하개", "심심하다멍", "같이 놀개?"],
    "심심해요": ["심심하개", "심심하다멍", "같이 놀개?"],
    "좋아": ["좋다멍", "좋아하개", "마음에 든다멍"],
    "고마워": ["고맙다멍", "고맙개", "정말 고마워멍"],
    "고마워요": ["고맙다멍", "고맙개", "정말 고마워멍"],
    "보고싶어": ["보고 싶다멍", "보고 싶었개", "만나고 싶다멍"],
    "놀자": ["같이 놀자멍", "놀자개", "한 번 더 놀개?"],
    "산책가자": ["산책 가자멍", "같이 나가개", "바깥 구경 가자멍"],
    "밥먹자": ["밥 먹자멍", "같이 먹개", "밥 먹으러 가자멍"],
    "잘자": ["잘 자라멍", "잘 자개", "좋은 꿈 꾸멍"],
    "사진봐줘": ["사진 봐주개", "사진 봐줘멍", "이 사진 어때멍?"],
}


def _compact_message(body):
    text = clean_single_line_text(body, 120)
    text = re.sub(r"\s+", " ", text).strip()
    # Old suggestions sometimes added an unrelated phrase after a comma.
    return re.split(r"[,，]", text, maxsplit=1)[0].strip()


def _normalize_key(text):
    return re.sub(r"[\s!?~.,，]+", "", text).strip()


def _with_meong_ending(text):
    value = text.rstrip("!?~. ").strip()
    was_question = text.rstrip().endswith("?")
    if not value:
        return ""
    if value.endswith(("멍", "개")):
        return f"{value}?" if was_question else value
    if value.endswith("해요"):
        value = f"{value[:-2]}한다멍"
    elif value.endswith("요"):
        value = f"{value[:-1]}멍"
    elif value.endswith("해"):
        value = f"{value[:-1]}한다멍"
    elif value.endswith("다"):
        value = f"{value}멍"
    else:
        value = f"{value}멍"
    return f"{value}?" if was_question else value


def _with_gae_ending(text):
    value = text.rstrip("!?~. ").strip()
    was_question = text.rstrip().endswith("?")
    if not value:
        return ""
    if value.endswith(("멍", "개")):
        return f"{value}?" if was_question else value

    replacements = (
        ("하세요", "하개"),
        ("해요", "하개"),
        ("해줘", "해주개"),
        ("할래", "할개"),
        ("갈래", "갈개"),
        ("해", "하개"),
        ("가자", "가개"),
        ("보자", "보개"),
        ("놀자", "놀개"),
        ("고마워", "고맙개"),
        ("좋아", "좋개"),
    )
    for before, after in replacements:
        if value.endswith(before):
            value = f"{value[:-len(before)]}{after}"
            break
    else:
        value = f"{value}개"
    return f"{value}?" if was_question else value


def _dedupe(items, limit=3):
    result = []
    seen = set()
    for item in items:
        value = _compact_message(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def suggest_message_tones(sender_profile, body, limit=3):
    del sender_profile
    original = _compact_message(body)
    if not original:
        return []

    key = _normalize_key(original)
    candidates = list(COMMON_REWRITES.get(key, []))
    candidates.extend((_with_meong_ending(original), _with_gae_ending(original)))
    return _dedupe(candidates, limit=limit)
