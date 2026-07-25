"""AI module for Zoo-In-Gong: caption, comment, and Gemini client."""

from ai.client import generate_gemini_content, DOG_LANGUAGE_SYSTEM_INSTRUCTION
from ai.caption import generate_caption, make_fallback_caption, sanitize_caption_text, is_supported_image_file, is_caption_too_short
from ai.comment import generate_comment_suggestion, make_fallback_comment
