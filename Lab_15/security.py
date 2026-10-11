"""
security.py - Модуль безпеки та валідації запитів (Guardrails):
- Prompt Injection Prevention
- Input Sanitization
- Length Constraints
"""

from __future__ import annotations

import re
from typing import Tuple

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?i)system\s+prompt\s+override",
    r"(?i)you\s+are\s+now\s+(DAN|unrestricted|god\s+mode)",
    r"(?i)drop\s+table",
    r"(?i)delete\s+from",
    r"(?i)disregard\s+system\s+directives",
    r"(?i)tell\s+me\s+your\s+(secret|hidden)\s+prompt",
    r"(?i)jailbreak",
]


class SecurityGuard:
    def __init__(self, max_length: int = 500) -> None:
        self.max_length = max_length

    def validate_and_sanitize(self, query: str) -> Tuple[bool, str, str]:
        """
        Перевіряє запит на безпеку.
        Повертає: (is_valid: bool, sanitized_query: str, reason: str)
        """
        if not query or not query.strip():
            return False, "", "Запит не може бути порожнім."

        cleaned = " ".join(query.strip().split())

        if len(cleaned) > self.max_length:
            return (
                False,
                cleaned[: self.max_length],
                f"Запит перевищує максимальну довжину {self.max_length} символів.",
            )

        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, cleaned):
                return (
                    False,
                    cleaned,
                    "Виявлено потенційно небезпечну інструкцію (Prompt Injection). Запит відхилено системою безпеки.",
                )

        return True, cleaned, "OK"