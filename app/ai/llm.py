"""
llm.py
Cloud LLM client: Groq (llama-3.1-8b-instant) as primary, NVIDIA NIM
(meta/llama-3.3-70b-instruct) as second fallback, OpenRouter (openrouter/free)
as third/last-resort fallback. All three speak the same OpenAI-style
/chat/completions shape, so this is one small client with three base URLs,
not three separate integrations.

Note: llama-3.3-70b-versatile was Groq's default here previously, but Groq
returned model_not_found for it on this account (deprecated/removed access,
regardless of what Groq's general docs list). Tried openai/gpt-oss-120b
next, but that's a reasoning model - it burns tokens on hidden
chain-of-thought before writing JSON, which caused json_validate_failed /
empty-output errors on the short structured calls this app makes (intent
classification, extraction). Settled on llama-3.1-8b-instant: still free,
still on Groq, genuinely non-reasoning, so no hidden-token surprises.

Note: meta-llama/llama-3.3-70b-instruct:free (the original OpenRouter
fallback) was pulled from OpenRouter's free tier entirely - free-model
availability on OpenRouter rotates often and specific :free model IDs get
retired without notice. Using openrouter/free, OpenRouter's own router
that always picks whatever free model is currently available, so this
fallback stops breaking every time one specific free model gets pulled.

Added NVIDIA NIM (build.nvidia.com) as a middle tier between Groq and
OpenRouter: free API key, no card required, OpenAI-compatible endpoint,
and meta/llama-3.3-70b-instruct there is a stable non-reasoning model
NVIDIA hosts directly (not subject to OpenRouter's free-tier churn).

Why a 3-way fallback instead of just picking one: every free tier here
has hit an outage or a pulled/deprecated model at some point during this
project. If all three are down, callers should treat that as a real
"unavailable" state (see LLMUnavailableError) rather than silently
returning nothing - the chat parser uses that distinction to queue the
message instead of losing it.
"""

from __future__ import annotations

import json
import os
import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
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

    # openai/gpt-oss-* models on Groq are reasoning models - they spend
    # tokens on a hidden chain-of-thought before writing the actual answer.
    # At "medium" (the default) that reasoning can eat the whole max_tokens
    # budget on short calls, leaving nothing for the real JSON output -
    # Groq then rejects it with json_validate_failed and an empty
    # failed_generation. "low" trims that reasoning pass down so short,
    # structured calls (intent classification, extraction) actually have
    # room left to write their answer.
    if provider_name == "Groq" and model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"

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
                base_url=NVIDIA_BASE_URL,
                api_key=NVIDIA_API_KEY,
                model=NVIDIA_MODEL,
                messages=messages,
                temperature=temperature,
                json_mode=json_mode,
                max_tokens=max_tokens,
                provider_name="NVIDIA",
            )
        except LLMError as nvidia_error:
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
                    f"Groq failed ({groq_error}); NVIDIA fallback also failed ({nvidia_error}); "
                    f"OpenRouter fallback also failed ({openrouter_error})"
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
    max_tokens: int = 400,
) -> str:
    """Same as chat(), just a lower default max_tokens for quick extraction
    calls (intent classification, transaction extraction). Bumped from the
    original 192 -> 400: the extraction schema now includes
    clarification_needed/clarification_question, and a truncated JSON
    response here silently breaks parsing further up the chain."""
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