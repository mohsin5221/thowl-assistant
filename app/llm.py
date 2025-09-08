# llm.py
import os
from pathlib import Path
import time
from typing import Optional
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
from langdetect import detect, DetectorFactory, LangDetectException

# Deterministic language detection
DetectorFactory.seed = 0

# Load .env robustly from the current working dir or parents
load_dotenv(find_dotenv(usecwd=True), override=False)

# ----------------------------
# Configuration
# ----------------------------
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

LANG_NAMES = {
    "en": "English", "de": "German", "fr": "French", "es": "Spanish",
    "it": "Italian", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
    "ru": "Russian", "pt": "Portuguese", "tr": "Turkish",
    "ar": "Arabic", "hi": "Hindi", "bn": "Bengali",
    "ja": "Japanese", "ko": "Korean", "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)"
}

# Friendly fallback text if no context; we’ll translate this if needed
NO_CONTEXT_HINT_EN = (
    "I couldn’t find relevant information in the indexed official pages for your question.\n"
    "Try phrasing it differently (German and English keywords), or check the Serviceportal/Studienbüro pages. "
    "You can also rebuild the index from the sidebar to include more pages."
)
NO_CONTEXT_HINT_DE = (
    "Ich konnte in den indizierten offiziellen Seiten keine passenden Informationen zu Ihrer Frage finden.\n"
    "Versuchen Sie andere Formulierungen (deutsche und englische Suchbegriffe) oder prüfen Sie das Serviceportal/Studienbüro. "
    "Sie können im Seitenmenü auch den Index neu aufbauen, um mehr Seiten einzuschließen."
)

# ----------------------------
# OpenAI client (lazy init)
# ----------------------------
_client: Optional[OpenAI] = None

def _get_api_key() -> str:
    """
    Returns API key if available; empty string otherwise.
    Don’t raise here — we want Streamlit to render without crashing.
    """
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    # Optional: Streamlit Secrets fallback (won’t import unless running under Streamlit)
    try:
        import streamlit as st  # noqa
        key = (st.secrets.get("OPENAI_API_KEY") or "").strip()
    except Exception:
        key = ""
    return key

def _get_client() -> Optional[OpenAI]:
    global _client
    if _client is not None:
        return _client
    key = _get_api_key()
    if not key:
        return None
    _client = OpenAI(api_key=key)
    return _client

# ----------------------------
# Utilities
# ----------------------------
def _detect_lang_code(text: str, default: str = "en") -> str:
    try:
        code = detect(text)
        return code if code in LANG_NAMES else code.split("-")[0]
    except LangDetectException:
        return default
    except Exception:
        return default

def _retry(func, *args, **kwargs):
    """Simple exponential backoff for transient errors."""
    delays = [0.5, 1.0, 2.0, 4.0]
    last_exc = None
    for d in delays:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            time.sleep(d)
    # Final attempt without sleep to propagate the error
    return func(*args, **kwargs)

def _ensure_language(text: str, lang_code: str) -> str:
    """
    If the output is not in target language, translate it.
    Best-effort; if API missing, return original.
    """
    if not text.strip():
        return text
    if _detect_lang_code(text, default=lang_code) == lang_code:
        return text
    try:
        return translate(text, target_code=lang_code)
    except Exception:
        return text

def _shrink_context(ctx: str, max_chars: int = 16000) -> str:
    """Guardrails against over-long prompts."""
    if not ctx:
        return ctx
    ctx = ctx.strip()
    return ctx[:max_chars]

# ----------------------------
# Public API
# ----------------------------
def ask_llm(user_text: str, context: str = "", force_lang_code: str | None = None) -> str:
    """
    Answer in the same language as the user's question by default; optionally force a language.
    - Returns a plain string (your UI already renders sources separately).
    - Gracefully handles: missing API key, empty/insufficient context, transient API errors.
    - Enforces final output language (auto-translate on slip).
    """
    # 1) Decide output language
    lang_code = (force_lang_code or _detect_lang_code(user_text)).lower()
    lang_name = LANG_NAMES.get(lang_code, "English")

    # 2) Handle missing API key early (don’t crash)
    client = _get_client()
    if client is None:
        # Return a helpful message in the user’s language (best-effort)
        base = (
            "OpenAI API key is missing. Set OPENAI_API_KEY in your environment "
            "or Streamlit Secrets to enable answers."
        )
        return _ensure_language(base, lang_code)

    # 3) If no/empty context, provide a helpful hint instead of a hard “I don’t know”
    if not context or not context.strip():
        hint = NO_CONTEXT_HINT_DE if lang_code == "de" else NO_CONTEXT_HINT_EN
        return _ensure_language(hint, lang_code)

    # 4) Build messages (strict language policy)
    system_prompt = (
        "You are a TH OWL university assistant.\n"
        f"STRICT LANGUAGE POLICY: Respond ONLY in {lang_name} ({lang_code}). "
        f"If provided context is in another language, translate it into {lang_name} "
        "and then answer. Do not include any other language.\n"
        "Use only the provided official context when present; if missing or insufficient, "
        "give a short, actionable next step (which office/page to check)."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": f"Official context:\n{_shrink_context(context)}"})
    messages.append({"role": "user", "content": user_text})

    # 5) Call OpenAI with retries
    try:
        resp = _retry(
            client.chat.completions.create,
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=700,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        # Return a localized error message rather than a Python exception
        msg = f"Temporary error contacting the language model: {e}. Please try again."
        return _ensure_language(msg, lang_code)

    # 6) Final language enforcement (translate back if the model slipped)
    return _ensure_language(answer, lang_code)

def translate(text: str, target_code: str = "en") -> str:
    """
    Translate `text` into language `target_code` (e.g., 'en', 'de').
    - No-op if already in the target language.
    - If API key is missing, returns the original text.
    """
    if not text.strip():
        return text
    try:
        if _detect_lang_code(text) == target_code:
            return text
    except Exception:
        pass

    client = _get_client()
    if client is None:
        return text  # can’t translate without an API key

    lang_name = LANG_NAMES.get(target_code, "English")
    try:
        resp = _retry(
            client.chat.completions.create,
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator. Output only {lang_name} ({target_code}) text."
                },
                {"role": "user", "content": text}
            ],
            temperature=0.0,
            max_tokens=500,
        )
        out = (resp.choices[0].message.content or "").strip()
        return out if out else text
    except Exception:
        return text
