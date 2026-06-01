import logging
import re
from datetime import datetime

from ai_client import generate_gemini_content
from persona_prompt import build_persona_prompt_text
from text_utils import meaningful_text_length, normalize_ai_text, soften_walk_terms


logger = logging.getLogger(__name__)

COMMENT_VARIATION_STYLES = [
    "짧고 신나는 리액션",
    "살짝 장난치는 반응",
    "다정하게 공감하는 반응",
    "강아지다운 감각을 섞은 반응",
    "페르소나가 드러나는 한마디",
    "살짝 질투 섞인 귀여운 칭찬",
    "집사에게도 들릴 듯한 농담",
    "사진 속 순간을 콕 집는 한 줄 감상",
    "예능 자막처럼 한 박자 튀는 반응",
    "사진 속 표정을 증거로 삼는 반응",
    "집사 카메라 실력을 놀리듯 칭찬하는 반응",
    "강아지 세계관의 짧은 판정문",
    "댓글을 보는 사람도 따라 웃게 하는 작은 오해",
]

COMMENT_HOOKS = [
    "이 장면은 저장각이라는 식으로 반응한다.",
    "집사 심장 조심하라는 농담을 섞는다.",
    "사진 속 표정이나 자세를 하나 콕 집는다.",
    "내 강아지가 옆에서 한마디 보태는 느낌을 낸다.",
    "칭찬을 하되 너무 평범한 감탄으로 끝내지 않는다.",
    "작은 사건명처럼 귀엽게 판정한다.",
]


COMMENT_SYSTEM_INSTRUCTION = """
너는 반려견 SNS 'Zoo-In-Gong'의 댓글 추천 AI다.
댓글 작성자의 강아지 프로필과 대상 게시물을 보고, 어울리고 짧은 강아지 말투 댓글을 만든다.

규칙:
1. 댓글은 1문장, 70자 이내로 쓴다.
2. 작성자의 이름, 아이디, 해시태그는 넣지 않는다.
3. 이모지나 이모티콘은 0~1개만 자연스럽게 넣을 수 있다.
4. 게시물의 강아지, 활동, 캡션을 구체적으로 반영한다.
5. 댓글 작성자 강아지의 성격과 페르소나를 말투에 반영한다.
6. 비난, 외모 평가, 건강 진단, 위험한 조언은 하지 않는다.
7. 최종 댓글 한 줄만 출력한다.
8. "귀여워요", "좋아 보여", "분위기 좋다" 같은 평범한 감탄만 반복하지 않는다.
9. "산책", "순찰", "리드줄", "코스" 표현은 가능하면 쓰지 말고, 꼬리/발바닥/표정/집사 반응으로 바꾼다.
""".strip()


FALLBACK_COMMENTS = [
    "이 장면은 꼬리가 먼저 저장 눌렀다멍 🐾",
    "표정이 너무 당당해서 나도 박수 치고 싶다개",
    "집사 카메라가 오늘 제일 잘한 일 인정이개",
    "발바닥까지 신난 게 여기까지 느껴진다멍",
    "이건 귀여움이 아니라 작은 사건이다개",
    "오늘의 주인공 포즈, 내 꼬리 심사 통과다멍",
    "이 눈빛은 집사 심장에 바로 도착하겠개",
    "사진 한 장인데 왜 이야기가 이렇게 많다멍",
    "이건 댓글보다 박수가 먼저 나오는 장면이개",
]


def _comment_variation_hint(viewer_profile, post):
    seed_text = (
        f"{viewer_profile.get('pet_name', '')}{viewer_profile.get('persona', '')}"
        f"{post.get('pet_name', '')}{post.get('caption_text', '')}"
    )
    index = (sum(ord(char) for char in seed_text) + datetime.now().second) % len(COMMENT_VARIATION_STYLES)
    return COMMENT_VARIATION_STYLES[index]


def _comment_hook_hint(viewer_profile, post):
    seed_text = (
        f"{viewer_profile.get('username', '')}{viewer_profile.get('pet_name', '')}"
        f"{post.get('id', '')}{post.get('activity_text', '')}{datetime.now().strftime('%S%f')}"
    )
    return COMMENT_HOOKS[sum(ord(char) for char in seed_text) % len(COMMENT_HOOKS)]


def _clean_ai_comment(text, max_chars=70):
    text = re.sub(r"<[^>]+>", "", normalize_ai_text(text))
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"^[\"'`]+|[\"'`]+$", "", text.strip())
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"#\S+", "", text).strip()
    text = _soften_overused_terms(text)
    return text[:max_chars].strip()


def _is_comment_too_short(text, min_chars=8):
    return meaningful_text_length(text) < min_chars


def _soften_overused_terms(text):
    return soften_walk_terms(text)


def make_fallback_comment(post):
    pet_name = (post or {}).get("pet_name") or ""
    if pet_name:
        return f"{pet_name} 이 장면은 꼬리가 먼저 저장 눌렀다멍 🐾"[:70]
    return FALLBACK_COMMENTS[0]


def generate_comment_suggestion(viewer_profile, post, recent_comments=None):
    recent_comments = recent_comments or []
    persona_rule = build_persona_prompt_text(
        viewer_profile.get("persona", ""),
        viewer_profile.get("personality", ""),
    )
    variation_hint = _comment_variation_hint(viewer_profile, post)
    hook_hint = _comment_hook_hint(viewer_profile, post)
    prompt = f"""
댓글 작성자:
- 이름: {viewer_profile.get("pet_name", "")}
- 견종: {viewer_profile.get("pet_species", "")}
- 페르소나: {viewer_profile.get("persona", "")}
- 성격: {viewer_profile.get("personality", "")}

댓글 작성자 말투 규칙:
{persona_rule}

댓글을 달 게시물:
- 강아지 이름: {post.get("pet_name", "")}
- 견종: {post.get("pet_species", "")}
- 페르소나: {post.get("persona", "")}
- 캡션: {post.get("caption_text", "")}
- 활동 메모: {post.get("activity_text", "")}
- 최근 댓글: {" / ".join(recent_comments[-5:])}

이번 댓글 스타일:
{variation_hint}

이번 댓글 훅:
{hook_hint}

재미와 다양성 규칙:
- 매번 "귀여워", "좋아 보여"만 반복하지 않는다.
- 게시물 속 행동이나 장소를 하나 콕 집어 반응한다.
- 강아지다운 감각, 장난, 작은 질투, 응원 중 하나를 섞는다.
- 이모지는 넣어도 1개까지만 쓴다.
- "산책/순찰/리드줄/코스" 대신 바깥 구경, 발바닥 시간, 집사 손, 우리 길 같은 표현을 우선한다.
- "대박", "힐링", "예쁘다"처럼 사람 SNS 댓글 같은 단어만으로 끝내지 않는다.

상황에 맞는 댓글 1개만 출력해.
""".strip()

    try:
        response = generate_gemini_content(
            prompt,
            system_instruction=COMMENT_SYSTEM_INSTRUCTION,
            thinking_level="low",
            use_search=False,
            temperature=1.05,
            top_p=0.95,
            max_output_tokens=80,
        )
        comment = _clean_ai_comment(response.text)
        return comment if comment and not _is_comment_too_short(comment) else make_fallback_comment(post)
    except Exception:
        logger.exception("Gemini comment generation failed")
        return make_fallback_comment(post)
