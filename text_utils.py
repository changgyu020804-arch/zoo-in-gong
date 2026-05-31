from html import unescape
import re


NUMERIC_ENTITY_FRAGMENT_RE = re.compile(r"&?\s*#\s*(x[0-9a-fA-F]+|\d+)\s*;")
NAMED_ENTITY_FRAGMENT_RE = re.compile(r"(?<![\w가-힣])&?\s*(quot|apos|amp|lt|gt)\s*;", re.IGNORECASE)
NAMED_ENTITY_VALUES = {
    "quot": '"',
    "apos": "'",
    "amp": "&",
    "lt": "<",
    "gt": ">",
}


def _decode_numeric_entity(match):
    value = match.group(1)
    try:
        codepoint = int(value[1:], 16) if value.lower().startswith("x") else int(value)
        return chr(codepoint)
    except (TypeError, ValueError, OverflowError):
        return ""


def normalize_ai_text(value):
    text = str(value or "")
    for _ in range(3):
        decoded = unescape(text)
        if decoded == text:
            break
        text = decoded

    text = NUMERIC_ENTITY_FRAGMENT_RE.sub(_decode_numeric_entity, text)
    text = NAMED_ENTITY_FRAGMENT_RE.sub(lambda match: NAMED_ENTITY_VALUES.get(match.group(1).lower(), ""), text)
    text = unescape(text)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def clean_single_line_text(value, max_length=120):
    cleaned = re.sub(r"\s+", " ", normalize_ai_text(value)).strip()
    return cleaned[:max_length]


def clean_multi_line_text(value, max_length=400):
    cleaned = normalize_ai_text(value).replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()[:max_length]
