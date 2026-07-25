import os
import re
import time
import logging
import gc
from contextlib import suppress
from threading import BoundedSemaphore
from types import SimpleNamespace

from config import load_local_env

load_local_env()

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
GEMINI_MODELS = [
    model.strip()
    for model in os.environ.get("GEMINI_MODELS", GEMINI_MODEL).split(",")
    if model.strip()
]
GEMINI_MAX_RESPONSE_CHARS = max(256, int(os.environ.get("GEMINI_MAX_RESPONSE_CHARS", "6000")))
GEMINI_CONCURRENCY = max(1, int(os.environ.get("GEMINI_CONCURRENCY", "1")))
GEMINI_GC_AFTER_CALL = os.environ.get("GEMINI_GC_AFTER_CALL", "1") != "0"

client = genai.Client(api_key=GEMINI_API_KEY) if genai and GEMINI_API_KEY else None
logger = logging.getLogger(__name__)
_gemini_semaphore = BoundedSemaphore(GEMINI_CONCURRENCY)


DOG_LANGUAGE_SYSTEM_INSTRUCTION = """
너는 반려견 SNS 'Zoo-In-Gong'의 강아지 언어 번역 AI다.
사용자가 적은 활동, 사진 설명, 반려견 프로필을 바탕으로 사람의 설명을 강아지 1인칭 말투로 바꾼다.

핵심 원칙:
1. 반드시 강아지 본인이 말하는 것처럼 쓴다. 관찰자나 집사 시점으로 설명하지 않는다.
2. 사진에 없는 물건, 장소, 사건을 새로 만들지 않는다.
3. 사용자가 적은 활동 내용이 있으면 사진 설명보다 우선 반영한다.
4. 반려견의 이름, 성격, 좋아하는 것, 싫어하는 것, 페르소나를 말투에 반영한다.
5. 너무 많은 '멍', '개', 이모지, 해시태그로 채우지 않는다.
6. 어려운 설명보다 감각, 기분, 냄새, 움직임, 기대감을 중심으로 쓴다.
7. 출력 형식은 요청받은 결과만 쓴다. 설명, 제목, 번호, 따옴표는 붙이지 않는다.

캡션 규칙:
- 본문은 보통 2~4문장으로 쓴다.
- 마지막 줄에 해시태그를 붙일 수 있지만 3개 이하로 제한한다.
- 글쓴이 말투가 과장 광고처럼 들리지 않게 한다.
- 강아지가 알 수 없는 전문적인 표현은 피한다.

댓글 규칙:
- 댓글은 1문장, 60자 이내로 쓴다.
- 게시물의 강아지와 상황을 구체적으로 반영한다.
- 비난, 외모 평가, 건강 진단, 위험한 조언은 하지 않는다.
""".strip()


def _text_parts(contents):
    if isinstance(contents, str):
        return [contents]
    if isinstance(contents, (list, tuple)):
        return [item for item in contents if isinstance(item, str)]
    return []


def extract_activity_block(contents):
    text = "\n".join(_text_parts(contents))
    if not text:
        return ""

    next_marker = (
        r"사진 참고|프로필|성향 질문 결과|댓글 작성자|댓글 작성자 말투 규칙|"
        r"댓글을 달 게시물|말투 규칙|참고 프로필"
    )
    match = re.search(
        rf"^\s*(?:집사가 적은 오늘 활동|오늘 활동|활동 내용)\s*:\s*(.*?)(?=^\s*(?:{next_marker})\s*:|\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if not match:
        return ""

    activity = re.sub(r"\n{3,}", "\n\n", match.group(1).strip())
    return activity[:600]


def build_effective_system_instruction(base_instruction, contents):
    activity_block = extract_activity_block(contents)
    if not activity_block:
        return base_instruction

    return (
        f"{base_instruction}\n\n"
        "# 이번 요청의 우선 규칙\n"
        "아래 활동 내용은 사용자가 직접 적은 실제 상황이다. 사진 설명보다 우선해서 반영한다.\n"
        f"{activity_block}\n"
        "활동 내용의 장소, 행동, 감정, 물건 중 최소 1개 이상을 결과에 자연스럽게 포함한다.\n"
    )


def _normalize_thinking_level(thinking_level):
    if os.environ.get("GEMINI_ENABLE_THINKING", "0") != "1":
        return None
    if not thinking_level:
        return None

    normalized = str(thinking_level).strip().lower()
    aliases = {
        "minimal": "low",
        "minimum": "low",
        "none": "low",
        "medium": "medium",
    }
    return aliases.get(normalized, normalized)


def _google_search_tool():
    if types is None:
        return None
    try:
        return types.Tool(google_search=types.GoogleSearch())
    except Exception:
        return None


def _generate_config(
    contents,
    system_instruction=None,
    thinking_level="low",
    use_search=False,
    response_mime_type=None,
    response_json_schema=None,
    temperature=None,
    top_p=None,
    max_output_tokens=None,
):
    if types is None:
        return None

    effective_instruction = build_effective_system_instruction(
        system_instruction or DOG_LANGUAGE_SYSTEM_INSTRUCTION,
        contents,
    )
    config_kwargs = {"system_instruction": effective_instruction}

    normalized_thinking = _normalize_thinking_level(thinking_level)
    if normalized_thinking:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=normalized_thinking
        )

    if use_search:
        search_tool = _google_search_tool()
        if search_tool is not None:
            config_kwargs["tools"] = [search_tool]

    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type
    if response_json_schema:
        config_kwargs["response_json_schema"] = response_json_schema
    if temperature is not None:
        config_kwargs["temperature"] = float(temperature)
    if top_p is not None:
        config_kwargs["top_p"] = float(top_p)
    if max_output_tokens is not None:
        config_kwargs["max_output_tokens"] = int(max_output_tokens)

    try:
        return types.GenerateContentConfig(**config_kwargs)
    except TypeError:
        for key in ("thinking_config", "temperature", "top_p", "max_output_tokens"):
            config_kwargs.pop(key, None)
        return types.GenerateContentConfig(**config_kwargs)


def _stream_text(model, contents, config):
    chunks = None
    parts = []
    total_chars = 0
    try:
        chunks = client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )
        for chunk in chunks:
            piece = chunk.text or ""
            if not piece:
                continue

            remaining = GEMINI_MAX_RESPONSE_CHARS - total_chars
            if remaining <= 0:
                break
            if len(piece) > remaining:
                piece = piece[:remaining]

            parts.append(piece)
            total_chars += len(piece)

        return "".join(parts).strip()
    finally:
        close = getattr(chunks, "close", None)
        if callable(close):
            with suppress(Exception):
                close()
        chunks = None
        parts.clear()


def generate_gemini_content(
    contents,
    system_instruction=None,
    thinking_level=None,
    use_search=False,
    response_mime_type=None,
    response_json_schema=None,
    temperature=None,
    top_p=None,
    max_output_tokens=None,
    max_attempts=2,
    retry_delay=0.7,
):
    if genai is None:
        raise RuntimeError("google-genai 패키지가 설치되어 있지 않습니다.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되어 있지 않습니다.")
    if client is None:
        raise RuntimeError("Gemini 클라이언트가 준비되지 않았습니다.")

    config = _generate_config(
        contents,
        system_instruction=system_instruction,
        thinking_level=thinking_level,
        use_search=use_search,
        response_mime_type=response_mime_type,
        response_json_schema=response_json_schema,
        temperature=temperature,
        top_p=top_p,
        max_output_tokens=max_output_tokens,
    )

    last_error_name = "UnknownError"
    last_error_message = "알 수 없는 오류"
    attempts = max(1, int(max_attempts or 1))
    started_at = time.perf_counter()

    _gemini_semaphore.acquire()
    try:
        for attempt in range(1, attempts + 1):
            for model in GEMINI_MODELS:
                text = ""
                try:
                    attempt_started_at = time.perf_counter()
                    text = _stream_text(model, contents, config)
                    if text:
                        elapsed = time.perf_counter() - started_at
                        attempt_elapsed = time.perf_counter() - attempt_started_at
                        logger.info(
                            "Gemini call completed model=%s attempt=%s elapsed=%.2fs attempt_elapsed=%.2fs chars=%s",
                            model,
                            attempt,
                            elapsed,
                            attempt_elapsed,
                            len(text),
                        )
                        return SimpleNamespace(text=text, model=model, attempts=attempt, elapsed=elapsed)
                    last_error_name = "EmptyResponse"
                    last_error_message = "Gemini가 빈 응답을 반환했습니다."
                except Exception as error:
                    last_error_name = type(error).__name__
                    last_error_message = str(error)
                    logger.warning(
                        "Gemini call failed model=%s attempt=%s elapsed=%.2fs error=%s",
                        model,
                        attempt,
                        time.perf_counter() - started_at,
                        last_error_name,
                    )
                finally:
                    text = ""

            if attempt < attempts:
                time.sleep(float(retry_delay or 0))
    finally:
        _gemini_semaphore.release()
        if GEMINI_GC_AFTER_CALL:
            gc.collect()

    model_list = ", ".join(GEMINI_MODELS) or "(모델 없음)"
    raise RuntimeError(
        f"Gemini 호출에 실패했습니다. models={model_list}, error={last_error_name}: {last_error_message}"
    )
