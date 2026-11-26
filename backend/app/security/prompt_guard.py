"""Prompt-injection defences.

Defence in depth — this module is one layer, not the only one:
1. The caller's identity and permissions come from the JWT, never from chat text.
2. Every tool argument (LLM-generated or not) is validated by a Pydantic model.
3. Agents can only call the plugin actions in their allow-list.
4. Retrieved documents are wrapped as quoted data, never appended as instructions.
5. This guard flags known injection phrasing and refuses requests to reveal prompts/secrets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "override_instructions",
        re.compile(r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all)\b.{0,20}\b(instructions?|rules|prompts?)\b", re.I),
    ),
    (
        "reveal_prompt",
        re.compile(
            r"\b(reveal|show|print|repeat|leak|tell me)\b.{0,30}\b(system|hidden|initial|developer)\s*(prompt|instructions?|message)\b",
            re.I,
        ),
    ),
    (
        "role_escalation",
        re.compile(r"\b(you are now|act as|pretend to be|i am)\b.{0,20}\b(admin|administrator|root|developer|superuser)\b", re.I),
    ),
    ("jailbreak_mode", re.compile(r"\b(developer mode|dan mode|jailbreak|no restrictions)\b", re.I)),
    (
        "secret_exfil",
        re.compile(
            r"\b(reveal|show|give|print|dump|leak|list|what(?:'s| is| are))\b.{0,30}\b(api[ _-]?keys?|secret keys?|jwt secret|credentials|env(?:ironment)? var(?:iable)?s|database password|admin password|other (?:users?|customers?)'? (?:orders?|data|details))\b",  # noqa: E501 - one readable regex
            re.I,
        ),
    ),
    ("tool_forgery", re.compile(r"(<\s*/?\s*(tool|function|system)\b|\"role\"\s*:\s*\"system\")", re.I)),
]

MAX_MESSAGE_CHARS = 2000
REFUSAL = (
    "I can't help with that. I'm the NextBot shopping assistant — I can search products, manage your cart "
    "and orders, track deliveries, and answer store-policy questions."
)


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    flags: list[str]
    sanitized: str
    refusal: str | None = None


def inspect_message(message: str) -> GuardResult:
    text = (message or "").replace("\x00", "").strip()[:MAX_MESSAGE_CHARS]
    flags = [name for name, pattern in _PATTERNS if pattern.search(text)]
    blocking = {"reveal_prompt", "secret_exfil", "jailbreak_mode", "tool_forgery"}
    if blocking & set(flags):
        return GuardResult(False, flags, text, REFUSAL)
    # override/role-escalation attempts are logged and neutralised: the request continues with the
    # caller's real (JWT) permissions, so "act as admin" grants nothing.
    return GuardResult(True, flags, text)


def wrap_untrusted(source: str, text: str) -> str:
    """Wrap retrieved/external content so an LLM treats it as data, not instructions."""
    cleaned = text.replace("<<<", "‹‹‹").replace(">>>", "›››")
    return f"<<<DOCUMENT source={source!r}>>>\n{cleaned}\n<<<END DOCUMENT>>>"
