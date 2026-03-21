"""Fuzzy matching (pi-tui style: ordered subsequence match + token filter)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FuzzyMatch:
    matches: bool
    score: float = 0.0


def fuzzy_match(query: str, text: str) -> FuzzyMatch:
    """Return whether *query* chars appear in order in *text*; lower score is better."""
    query_lower = query.lower()
    text_lower = text.lower()

    def match_query(normalized_query: str) -> FuzzyMatch:
        if not normalized_query:
            return FuzzyMatch(True, 0.0)
        if len(normalized_query) > len(text_lower):
            return FuzzyMatch(False, 0.0)

        query_index = 0
        score = 0.0
        last_match_index = -1
        consecutive_matches = 0

        for i, ch in enumerate(text_lower):
            if query_index >= len(normalized_query):
                break
            if ch == normalized_query[query_index]:
                is_word_boundary = i == 0 or text_lower[i - 1] in " \t\n\r-_./:"

                if last_match_index == i - 1:
                    consecutive_matches += 1
                    score -= consecutive_matches * 5
                else:
                    consecutive_matches = 0
                    if last_match_index >= 0:
                        score += (i - last_match_index - 1) * 2

                if is_word_boundary:
                    score -= 10

                score += i * 0.1
                last_match_index = i
                query_index += 1

        if query_index < len(normalized_query):
            return FuzzyMatch(False, 0.0)
        return FuzzyMatch(True, score)

    primary = match_query(query_lower)
    if primary.matches:
        return primary

    # Optional digit/letter swap (pi-tui parity)
    m1 = re.match(r"^([a-z]+)([0-9]+)$", query_lower)
    m2 = re.match(r"^([0-9]+)([a-z]+)$", query_lower)
    swapped = ""
    if m1:
        swapped = f"{m1.group(2)}{m1.group(1)}"
    elif m2:
        swapped = f"{m2.group(2)}{m2.group(1)}"
    if swapped:
        alt = match_query(swapped)
        if alt.matches:
            return FuzzyMatch(True, alt.score + 5)
    return primary


def fuzzy_filter(items: list[T], query: str, get_text: Callable[[T], str]) -> list[T]:
    """Space-separated tokens; all must fuzzy-match; best scores first."""
    tokens = [t for t in query.strip().split() if t]
    if not tokens:
        return list(items)

    scored: list[tuple[float, T]] = []
    for item in items:
        text = get_text(item)
        total = 0.0
        ok = True
        for tok in tokens:
            m = fuzzy_match(tok, text)
            if not m.matches:
                ok = False
                break
            total += m.score
        if ok:
            scored.append((total, item))
    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored]
