"""HRR primitives — NumPy port of Nuggets `src/nuggets/core.ts` (MIT)."""

from __future__ import annotations

from typing import Callable

import numpy as np

ComplexVec = tuple[np.ndarray, np.ndarray]  # (re, im) float64 shape (D,)


def _i32(x: int) -> int:
    x = int(x) & 0xFFFFFFFF
    if x >= 2**31:
        return x - 2**32
    return x


def _imul(a: int, b: int) -> int:
    return _i32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))


def mulberry32(seed: int) -> Callable[[], float]:
    """Same PRNG stream as Nuggets TypeScript `mulberry32`."""

    s = _i32(seed)

    def _next() -> float:
        nonlocal s
        s = _i32(s + 0x6D2B79F5)
        su = s & 0xFFFFFFFF
        t = _imul(su ^ (su >> 15), 1 | su)
        tu = t & 0xFFFFFFFF
        t = _i32(t + _imul(tu ^ (tu >> 7), 61 | tu) ^ t)
        tu = t & 0xFFFFFFFF
        return (tu ^ (tu >> 14)) / 4294967296.0

    return _next


def seed_from_name(name: str) -> int:
    """Derive u32 seed from string (matches Nuggets / TS)."""
    b = name.encode("utf-8")[:8]
    padded = bytearray(8)
    padded[: len(b)] = b
    return int.from_bytes(padded[:4], "little", signed=False)


def make_vocab_keys(v: int, d: int, rng: Callable[[], float]) -> list[ComplexVec]:
    """V unit-magnitude complex keys, shape (d,) each."""
    two_pi = 2.0 * np.pi
    keys: list[ComplexVec] = []
    for _ in range(v):
        phi = two_pi * np.array([rng() for _ in range(d)], dtype=np.float64)
        keys.append((np.cos(phi), np.sin(phi)))
    return keys


def make_role_keys(d: int, l_count: int) -> list[ComplexVec]:
    """Role keys: exp(2π i * k * arange(d) / d) for k in 0..L-1."""
    two_pi = 2.0 * np.pi
    idx = np.arange(d, dtype=np.float64)
    keys: list[ComplexVec] = []
    for k in range(l_count):
        angle = (k * two_pi * idx) / max(d, 1)
        keys.append((np.cos(angle), np.sin(angle)))
    return keys


def orthogonalize(keys: list[ComplexVec], iters: int = 1, step: float = 0.4) -> list[ComplexVec]:
    if iters <= 0 or not keys:
        return keys
    d = keys[0][0].size
    d2 = d * 2
    v = len(keys)
    k_mat = np.zeros((v, d2), dtype=np.float64)
    for i, (re, im) in enumerate(keys):
        k_mat[i, :d] = re
        k_mat[i, d:] = im

    for _ in range(iters):
        g = np.zeros((v, v), dtype=np.float64)
        for i in range(v):
            for j in range(i, v):
                dot = float(np.dot(k_mat[i], k_mat[j]))
                g[i, j] = dot
                g[j, i] = dot
        np.fill_diagonal(g, 0.0)
        correction = g @ k_mat
        k_mat -= (step / d2) * correction
        norms = np.linalg.norm(k_mat, axis=1, keepdims=True) + 1e-9
        k_mat /= norms

    out: list[ComplexVec] = []
    for i in range(v):
        re_flat = k_mat[i, :d]
        im_flat = k_mat[i, d:]
        phase = np.arctan2(im_flat, re_flat)
        out.append((np.cos(phase), np.sin(phase)))
    return out


def sharpen(z: ComplexVec, p: float = 1.0, eps: float = 1e-12) -> ComplexVec:
    re, im = z
    if p == 1.0:
        return z
    mag = np.sqrt(re * re + im * im) + eps
    scale = np.power(mag, p - 1.0)
    return (re * scale, im * scale)


def corvacs_lite(z: ComplexVec, a: float = 0.0) -> ComplexVec:
    re, im = z
    if a <= 0:
        return z
    mag = np.sqrt(re * re + im * im) + 1e-12
    scale = np.tanh(a * mag) / mag
    return (re * scale, im * scale)


def softmax_temp(sims: np.ndarray, t: float = 1.0) -> np.ndarray:
    t = max(float(t), 1e-6)
    z = sims / t
    z = z - np.max(z)
    e = np.exp(z)
    return e / (np.sum(e) + 1e-12)


def stack_and_unit_norm(keys: list[ComplexVec]) -> list[np.ndarray]:
    if not keys:
        return []
    d = keys[0][0].size
    d2 = d * 2
    rows: list[np.ndarray] = []
    for re, im in keys:
        row = np.zeros(d2, dtype=np.float64)
        row[:d] = re
        row[d:] = im
        n = np.linalg.norm(row) + 1e-12
        rows.append(row / n)
    return rows


def bind(a: ComplexVec, b: ComplexVec) -> ComplexVec:
    ar, ai = a
    br, bi = b
    return (ar * br - ai * bi, ar * bi + ai * br)


def unbind(m: ComplexVec, key: ComplexVec) -> ComplexVec:
    """m * conj(key)."""
    mr, mi = m
    kr, ki = key
    return (mr * kr + mi * ki, -mr * ki + mi * kr)
