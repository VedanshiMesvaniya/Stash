"""
llm.py
Cloud LLM client: Groq (llama-3.3-70b-versatile) as primary, OpenRouter
(meta-llama/llama-3.3-70b-instruct:free) as fallback if Groq errors, times
out, or rate-limits. Both speak the same OpenAI-style /chat/completions
shape, so this is one small client with two base URLs, not two integrations.

Why a fallback instead of just picking one: Groq's free tier is generous
(1000 req/day) but not infinite, and free APIs occasionally have outages.
If both are down, callers should treat that as a real "unavailable" state
(see LLMUnavailableError) rather than silently returning nothing - the
chat parser uses that distinction to queue the message instead of losing it.
"""

from __future__ import annotations

import json
import os
import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))


class LLMError(Exception):
    """A single provider call failed (used internally before falling back)."""


class LLMUnavailableError(Exception):
    """Both Groq and OpenRouter failed. Callers (see ai/parser.py) should
    treat this as 'the AI is temporarily down' and queue the raw message
    into pending_entries rather than silently dropping it or claiming
    the message wasn't a transaction."""


def _call_provider(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    json_mode: bool,
    max_tokens: int,
    provider_name: str,
) -> str:
    if not api_key:
        raise LLMError(f"{provider_name} API key not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # OpenRouter asks integrators to identify their app; harmless for Groq
    # to include extra headers, but only send these for OpenRouter calls.
    if provider_name == "OpenRouter":
        headers["HTTP-Referer"] = os.getenv("APP_PUBLIC_URL", "https://stash.local")
        headers["X-Title"] = "Stash"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.post(base_url, headers=headers, json=payload)
            if resp.status_code == 429:
                raise LLMError(f"{provider_name} rate-limited (429)")
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return strip_think_tags(content or "")
    except httpx.TimeoutException as e:
        raise LLMError(f"{provider_name} request timed out") from e
    except httpx.ConnectError as e:
        raise LLMError(f"Could not reach {provider_name}") from e
    except httpx.HTTPStatusError as e:
        raise LLMError(f"{provider_name} returned an error: {e.response.text[:300]}") from e
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise LLMError(f"{provider_name} returned an unexpected response shape") from e


def _chat_with_fallback(
    messages: list[dict],
    *,
    temperature: float,
    json_mode: bool,
    max_tokens: int,
) -> str:
    try:
        return _call_provider(
            base_url=GROQ_BASE_URL,
            api_key=GROQ_API_KEY,
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            json_mode=json_mode,
            max_tokens=max_tokens,
            provider_name="Groq",
        )
    except LLMError as groq_error:
        try:
            return _call_provider(
                base_url=OPENROUTER_BASE_URL,
                api_key=OPENROUTER_API_KEY,
                model=OPENROUTER_MODEL,
                messages=messages,
                temperature=temperature,
                json_mode=json_mode,
                max_tokens=max_tokens,
                provider_name="OpenRouter",
            )
        except LLMError as openrouter_error:
            raise LLMUnavailableError(
                f"Groq failed ({groq_error}); OpenRouter fallback also failed ({openrouter_error})"
            ) from openrouter_error


def chat(
    messages: list[dict],
    temperature: float = 0.2,
    json_mode: bool = False,
    max_tokens: int = 512,
) -> str:
    """Sends a chat-style request, Groq first then OpenRouter fallback."""
    return _chat_with_fallback(messages, temperature=temperature, json_mode=json_mode, max_tokens=max_tokens)


def fast_chat(
    messages: list[dict],
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int = 192,
) -> str:
    """Same as chat(), just a lower default max_tokens for quick extraction
    calls (intent classification, transaction extraction)."""
    return _chat_with_fallback(messages, temperature=temperature, json_mode=json_mode, max_tokens=max_tokens)


def qa_chat(messages: list[dict], max_tokens: int = 400) -> str:
    return _chat_with_fallback(messages, temperature=0.2, json_mode=False, max_tokens=max_tokens)


def strip_think_tags(text: str) -> str:
    """Some reasoning-capable free models may emit <think>...</think> blocks
    before the actual answer. Strip them so they never leak into structured
    parsing or user-facing output."""
    import re

    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def safe_json_parse(text: str) -> dict | list | None:
    """Attempts to parse JSON, tolerating markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_candidates = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
        if not start_candidates:
            return None
        start = min(start_candidates)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if end == -1:
            return None
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
