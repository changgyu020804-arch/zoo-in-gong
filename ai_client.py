"""Backward compatibility shim — import from ai.client instead."""
from ai.client import *  # noqa: F401, F403
from ai.client import generate_gemini_content, DOG_LANGUAGE_SYSTEM_INSTRUCTION, client, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODELS  # noqa: F401
