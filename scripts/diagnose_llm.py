"""
diagnose_llm.py
Standalone diagnostic - calls Groq, NVIDIA NIM, and OpenRouter directly
(bypassing the app's fallback logic) and prints the real HTTP status +
error body for each, so you can see exactly why providers are failing
instead of just getting the generic "AI providers are busy" message the
chat UI shows.

Usage:
    GROQ_API_KEY=... NVIDIA_API_KEY=... OPENROUTER_API_KEY=... python3 scripts/diagnose_llm.py

    # Optionally override which model gets tested (defaults match app/ai/llm.py):
    GROQ_MODEL=llama-3.1-8b-instant NVIDIA_MODEL=nvidia/nvidia-nemotron-nano-9b-v2 OPENROUTER_MODEL=openrouter/free python3 scripts/diagnose_llm.py

If you're testing against Render's actual deployed config, pull the exact
env vars from the Render dashboard (Environment tab) and export them
locally before running this - that's the only way to know for certain
what the deployed app is actually sending.
"""

import os
import sys

import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2")
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TEST_MESSAGES = [{"role": "user", "content": "Reply with the single word: ok"}]


def test_provider(name, url, api_key, model, extra_headers=None):
    print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")
    print(f"Model: {model}")

    if not api_key:
        print("RESULT: FAIL - no API key set in this environment")
        return False

    print(f"API key: {api_key[:8]}...{api_key[-4:]} (len={len(api_key)})")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)

    messages = TEST_MESSAGES
    if "nemotron" in model.lower():
        # Matches app/ai/llm.py's default for Nemotron models: disable the
        # hidden reasoning trace so this test reflects real app behavior.
        messages = [{"role": "system", "content": "/no_think"}] + TEST_MESSAGES

    payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 20}

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
            print(f"HTTP status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                print(f"RESULT: SUCCESS - model replied: {content!r}")
                return True
            else:
                print(f"RESULT: FAIL - response body:\n{resp.text[:1000]}")
                return False
    except httpx.TimeoutException:
        print("RESULT: FAIL - request timed out (30s)")
        return False
    except httpx.ConnectError as e:
        print(f"RESULT: FAIL - could not connect: {e}")
        return False
    except Exception as e:
        print(f"RESULT: FAIL - unexpected error: {type(e).__name__}: {e}")
        return False


def main():
    groq_ok = test_provider("GROQ", GROQ_URL, GROQ_API_KEY, GROQ_MODEL)
    nvidia_ok = test_provider("NVIDIA NIM", NVIDIA_URL, NVIDIA_API_KEY, NVIDIA_MODEL)
    or_ok = test_provider(
        "OPENROUTER",
        OPENROUTER_URL,
        OPENROUTER_API_KEY,
        OPENROUTER_MODEL,
        extra_headers={
            "HTTP-Referer": os.getenv("APP_PUBLIC_URL", "https://stash.local"),
            "X-Title": "Stash",
        },
    )

    print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
    print(f"Groq:       {'OK' if groq_ok else 'FAILING'}")
    print(f"NVIDIA NIM: {'OK' if nvidia_ok else 'FAILING'}")
    print(f"OpenRouter: {'OK' if or_ok else 'FAILING'}")

    if not groq_ok and not nvidia_ok and not or_ok:
        print("\nAll three providers failing - this matches the 'AI providers are busy' error users see.")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
