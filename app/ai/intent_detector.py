"""
intent_detector.py
Classifies a user message into one of: transaction, correction, question,
report, chat.
"""

from . import llm
from .prompts import INTENT_SYSTEM_PROMPT

VALID_INTENTS = {"transaction", "correction", "delete", "question", "report", "chat"}


def detect_intent(message: str, recent_chat: str | None = None) -> str:
    lowered = message.strip()
    if not lowered:
        return "chat"

    user_content = lowered
    if recent_chat:
        user_content = f"RECENT CHAT MEMORY:\n{recent_chat.strip()}\n\nMESSAGE:\n{lowered}"

    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    # Deliberately NOT caught here: llm.LLMUnavailableError propagates up to
    # ai/parser.py, which queues the raw message into pending_entries instead
    # of silently mis-classifying it as "chat" and losing it.
    raw = llm.fast_chat(messages, json_mode=True, max_tokens=32)

    parsed = llm.safe_json_parse(raw)

    if not parsed or "intent" not in parsed or parsed["intent"] not in VALID_INTENTS:
        return "chat"

    return parsed["intent"]
