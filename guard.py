"""Checks applied to AI-written text BEFORE a student sees it.

The calculators compute the answer. The AI only explains it. So the explanation must not contain
numbers that are not already in the data we gave it. If it does, we drop the AI text and show a
template explanation instead.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .text import extract_numbers

LINK_RE = re.compile(r"(https?://|www\.|\b[\w.-]+@[\w-]+\.[a-z]{2,}\b)", re.I)
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
LETTER = re.compile(r"[A-Za-z\u0900-\u097F]")


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""


def _known(n: float, context_numbers: list[float]) -> bool:
    for c in context_numbers:
        if math.isclose(n, c, rel_tol=1e-3, abs_tol=1e-12):
            return True
        for k in range(0, 8):                    # the AI may round: 16.666667 -> 16.67 -> 16.7
            if round(c, k) == n:
                return True
    return False


def check_explanation(text: str, context_text: str, lang: str, max_chars: int = 1600) -> GuardResult:
    t = (text or "").strip()
    if not t:
        return GuardResult(False, "empty")
    if len(t) > max_chars:
        return GuardResult(False, "too_long")
    if LINK_RE.search(t):
        return GuardResult(False, "link_in_output")
    letters = LETTER.findall(t)
    if letters:
        dev_ratio = len(DEVANAGARI.findall(t)) / len(letters)
        if lang == "hi" and dev_ratio < 0.25:
            return GuardResult(False, "wrong_language")
        if lang == "en" and dev_ratio > 0.10:
            return GuardResult(False, "wrong_language")
    ctx = extract_numbers(context_text)
    for n in extract_numbers(t):
        if abs(n) <= 12 and n == int(n):          # step numbers, squares, small whole numbers
            continue
        if not _known(n, ctx):
            return GuardResult(False, f"unknown_number:{n:g}")
    return GuardResult(True)
