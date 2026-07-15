"""
response.py
Generates natural-language answers (financial Q&A) and smart suggestions,
given a context dict assembled by services/analytics.py.
"""

import json

from . import llm
from .prompts import QA_SYSTEM_PROMPT, SUGGESTION_SYSTEM_PROMPT


def answer_question(question: str, context: dict) -> str:
    user_content = (
        f"DATA:\n{json.dumps(context, default=str)}\n\n"
        f"QUESTION:\n{question}"
    )
    messages = [
        {"role": "system", "content": QA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        return llm.qa_chat(messages, max_tokens=500)
    except llm.LLMUnavailableError:
        return "Both AI providers are unreachable right now (rate-limited or down) - try again in a minute."


def generate_suggestion(context: dict) -> str:
    user_content = f"CONTEXT:\n{json.dumps(context, default=str)}"
    messages = [
        {"role": "system", "content": SUGGESTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        return llm.fast_chat(messages, temperature=0.2, max_tokens=80)
    except llm.LLMUnavailableError:
        return ""
