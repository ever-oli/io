"""Fuzzy key matching — verbatim port of Nuggets `memory.ts` (sequenceMatchRatio / countMatches).

Nuggets does *not* use Python's ``difflib.SequenceMatcher``; it uses this greedy
longest-block matcher so recall tag resolution matches TypeScript behavior.
"""

from __future__ import annotations


def count_matches(a: str, b: str) -> int:
    """Count matching characters using greedy longest-common-substring blocks (Nuggets TS)."""
    m, n = len(a), len(b)
    total = 0
    used_a: set[int] = set()
    used_b: set[int] = set()

    while True:
        best_len = best_i = best_j = 0
        for i in range(m):
            if i in used_a:
                continue
            for j in range(n):
                if j in used_b:
                    continue
                length = 0
                while (
                    i + length < m
                    and j + length < n
                    and (i + length) not in used_a
                    and (j + length) not in used_b
                    and a[i + length] == b[j + length]
                ):
                    length += 1
                if length > best_len:
                    best_len = length
                    best_i = i
                    best_j = j

        if best_len == 0:
            break

        for k in range(best_len):
            used_a.add(best_i + k)
            used_b.add(best_j + k)
        total += best_len

    return total


def sequence_match_ratio(a: str, b: str) -> float:
    """Port of Nuggets ``sequenceMatchRatio`` (ratio vs stored key, ``b`` lowercased by caller)."""
    if len(a) == 0 and len(b) == 0:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0
    matches = count_matches(a, b)
    return (2.0 * matches) / (len(a) + len(b))
