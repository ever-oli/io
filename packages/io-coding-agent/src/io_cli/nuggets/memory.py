"""Nugget — single holographic memory unit (port of Nuggets `memory.ts`, MIT)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import hrr_core
from .nuggets_fuzzy import sequence_match_ratio


@dataclass
class _Fact:
    key: str
    value: str
    hits: int = 0
    last_hit_session: str = ""


@dataclass
class _BankData:
    memory: hrr_core.ComplexVec
    vocab_keys: list[hrr_core.ComplexVec]
    vocab_norm: list[np.ndarray]
    sent_keys: list[hrr_core.ComplexVec]
    role_keys: list[hrr_core.ComplexVec]


@dataclass
class _EnsembleData:
    banks: list[_BankData]


class Nugget:
    """Topic-scoped HRR memory; JSON on disk compatible with Nuggets v3 schema."""

    def __init__(
        self,
        name: str,
        *,
        d: int = 16384,
        banks: int = 4,
        ensembles: int = 1,
        auto_save: bool = True,
        save_dir: Path | None = None,
        max_facts: int = 0,
    ) -> None:
        self.name = name
        self.D = d
        self.banks = banks
        self.ensembles = ensembles
        self.auto_save = auto_save
        self.save_dir = save_dir
        self.max_facts = max_facts
        self._sharpen_p = 1.0
        self._corvacs_a = 0.0
        self._temp_t = 0.9
        self._orth_iters = 1
        self._orth_step = 0.4
        self._fuzzy_threshold = 0.55
        self._facts: list[_Fact] = []
        self._E: list[_EnsembleData] | None = None
        self._vocab_words: list[str] = []
        self._tag_to_pos: dict[str, int] = {}
        self._dirty = True

    def remember(self, key: str, value: str) -> None:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return
        found = False
        for f in self._facts:
            if f.key.lower() == key.lower():
                f.value = value
                found = True
                break
        if not found:
            self._facts.append(_Fact(key=key, value=value))
        if self.max_facts > 0 and len(self._facts) > self.max_facts:
            self._facts = self._facts[-self.max_facts :]
        self._dirty = True
        if self.auto_save:
            self.save()

    def recall(
        self, query: str, session_id: str = ""
    ) -> dict[str, Any]:
        empty = {"answer": None, "confidence": 0.0, "margin": 0.0, "found": False, "key": ""}
        if not self._facts:
            return empty
        if self._dirty or self._E is None:
            self._rebuild()
            self._dirty = False
        tag = self._resolve_tag(query)
        if not tag or tag not in self._tag_to_pos:
            return empty
        word, probs = self._decode(tag)
        top1 = top2 = float("-inf")
        for p in probs:
            if p > top1:
                top2, top1 = top1, p
            elif p > top2:
                top2 = p
        confidence = float(top1)
        margin = float(top1) if top2 == float("-inf") else float(top1 - top2)
        if session_id:
            pos = self._tag_to_pos[tag]
            fact = self._facts[pos]
            if fact.last_hit_session != session_id:
                fact.hits = (fact.hits or 0) + 1
                fact.last_hit_session = session_id
                if self.auto_save:
                    self.save()
        return {
            "answer": word,
            "confidence": confidence,
            "margin": margin,
            "found": True,
            "key": tag,
        }

    def forget(self, key: str) -> bool:
        lower = key.lower().strip()
        before = len(self._facts)
        self._facts = [f for f in self._facts if f.key.lower() != lower]
        removed = len(self._facts) < before
        if removed:
            self._dirty = True
            if self.auto_save:
                self.save()
        return removed

    def facts(self) -> list[dict[str, Any]]:
        return [{"key": f.key, "value": f.value, "hits": f.hits or 0} for f in self._facts]

    def clear(self) -> None:
        self._facts = []
        self._E = None
        self._vocab_words = []
        self._tag_to_pos = {}
        self._dirty = False
        if self.auto_save:
            self.save()

    def status(self) -> dict[str, Any]:
        # Match Nuggets TS: capacityEst = banks * Math.floor(Math.sqrt(D))
        cap_est = self.banks * int(math.floor(math.sqrt(float(self.D))))
        used_pct = (len(self._facts) / cap_est * 100) if cap_est > 0 else 0.0
        warn = ""
        if used_pct > 90:
            warn = "CRITICAL: nearly full"
        elif used_pct > 80:
            warn = "WARNING: approaching capacity"
        # Match Nuggets TS: Math.round(usedPct * 10) / 10 (half-away-from-zero for positives)
        cap_round = math.floor(used_pct * 10.0 + 0.5) / 10.0
        return {
            "name": self.name,
            "fact_count": len(self._facts),
            "dimension": self.D,
            "banks": self.banks,
            "ensembles": self.ensembles,
            "capacity_used_pct": cap_round,
            "capacity_warning": warn,
            "max_facts": self.max_facts,
        }

    def save(self, path: Path | None = None) -> str:
        assert self.save_dir is not None
        self.save_dir.mkdir(parents=True, exist_ok=True)
        if path is None:
            path = self.save_dir / f"{self.name}.nugget.json"
        data = {
            "version": 3,
            "name": self.name,
            "D": self.D,
            "banks": self.banks,
            "ensembles": self.ensembles,
            "max_facts": self.max_facts,
            "facts": [
                {
                    "key": f.key,
                    "value": f.value,
                    "hits": f.hits,
                    "last_hit_session": f.last_hit_session,
                }
                for f in self._facts
            ],
            "config": {
                "sharpen_p": self._sharpen_p,
                "corvacs_a": self._corvacs_a,
                "temp_T": self._temp_t,
                "orth_iters": self._orth_iters,
            },
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
        return str(path)

    @classmethod
    def load(cls, path: Path, *, auto_save: bool = True) -> Nugget:
        raw = json.loads(path.read_text(encoding="utf-8"))
        n = cls(
            name=str(raw["name"]),
            d=int(raw.get("D", 16384)),
            banks=int(raw.get("banks", 4)),
            ensembles=int(raw.get("ensembles", 1)),
            auto_save=auto_save,
            save_dir=path.parent,
            max_facts=int(raw.get("max_facts", 0)),
        )
        cfg = raw.get("config") or {}
        n._sharpen_p = float(cfg.get("sharpen_p", n._sharpen_p))
        n._corvacs_a = float(cfg.get("corvacs_a", n._corvacs_a))
        n._temp_t = float(cfg.get("temp_T", n._temp_t))
        n._orth_iters = int(cfg.get("orth_iters", n._orth_iters))
        n._facts = []
        for f in raw.get("facts") or []:
            n._facts.append(
                _Fact(
                    key=str(f["key"]),
                    value=str(f["value"]),
                    hits=int(f.get("hits", 0)),
                    last_hit_session=str(f.get("last_hit_session", "")),
                )
            )
        n._dirty = True
        if n._facts:
            n._rebuild()
            n._dirty = False
        return n

    def _rebuild(self) -> None:
        if not self._facts:
            self._E = None
            self._vocab_words = []
            self._tag_to_pos = {}
            return
        seen: set[str] = set()
        vocab: list[str] = []
        for f in self._facts:
            if f.value not in seen:
                vocab.append(f.value)
                seen.add(f.value)
        self._vocab_words = vocab
        self._tag_to_pos = {self._facts[i].key: i for i in range(len(self._facts))}
        l_count = len(self._facts)
        seed = hrr_core.seed_from_name(self.name)
        rng = hrr_core.mulberry32(seed)
        v = len(vocab)
        idx_w = {w: i for i, w in enumerate(vocab)}
        items_by_bank: list[list[dict[str, Any]]] = [[] for _ in range(self.banks)]
        for i in range(len(self._facts)):
            items_by_bank[i % self.banks].append({"sid": 0, "pos": i, "word": self._facts[i].value})
        ensembles: list[_EnsembleData] = []
        for _e in range(self.ensembles):
            vocab_keys = hrr_core.make_vocab_keys(v, self.D, rng)
            if self._orth_iters > 0:
                vocab_keys = hrr_core.orthogonalize(vocab_keys, self._orth_iters, self._orth_step)
            vocab_norm = hrr_core.stack_and_unit_norm(vocab_keys)
            sent_keys = hrr_core.make_vocab_keys(1, self.D, rng)
            role_keys = hrr_core.make_role_keys(self.D, l_count)
            banks_out: list[_BankData] = []
            for b in range(self.banks):
                items = items_by_bank[b]
                bindings: list[hrr_core.ComplexVec] = []
                for it in items:
                    s_key = sent_keys[it["sid"]]
                    r_key = role_keys[it["pos"]]
                    w_key = vocab_keys[idx_w[it["word"]]]
                    bindings.append(hrr_core.bind(hrr_core.bind(s_key, r_key), w_key))
                if bindings:
                    re = np.zeros(self.D, dtype=np.float64)
                    im = np.zeros(self.D, dtype=np.float64)
                    for br, bi in bindings:
                        re += br
                        im += bi
                    scale = 1.0 / np.sqrt(len(bindings))
                    re *= scale
                    im *= scale
                    memory = (re, im)
                else:
                    memory = (np.zeros(self.D), np.zeros(self.D))
                banks_out.append(
                    _BankData(
                        memory=memory,
                        vocab_keys=vocab_keys,
                        vocab_norm=vocab_norm,
                        sent_keys=sent_keys,
                        role_keys=role_keys,
                    )
                )
            ensembles.append(_EnsembleData(banks=banks_out))
        self._E = ensembles

    def _decode(self, tag: str) -> tuple[str, np.ndarray]:
        pos = self._tag_to_pos[tag]
        sid = 0
        v = len(self._vocab_words)
        sims_sum = np.zeros(v, dtype=np.float64)
        assert self._E is not None
        for ens in self._E:
            for bank in ens.banks:
                rec = hrr_core.unbind(hrr_core.unbind(bank.memory, bank.sent_keys[sid]), bank.role_keys[pos])
                rec = hrr_core.corvacs_lite(hrr_core.sharpen(rec, self._sharpen_p), self._corvacs_a)
                d = self.D
                rec2 = np.zeros(d * 2, dtype=np.float64)
                rec2[:d] = rec[0]
                rec2[d:] = rec[1]
                rec2 /= np.linalg.norm(rec2) + 1e-12
                for vi in range(v):
                    sims_sum[vi] += float(np.dot(bank.vocab_norm[vi], rec2))
        probs = hrr_core.softmax_temp(sims_sum, self._temp_t)
        best_idx = int(np.argmax(probs))
        return self._vocab_words[best_idx], probs

    def _resolve_tag(self, query: str) -> str:
        if not self._tag_to_pos:
            return ""
        text = query.lower().strip()
        tags = list(self._tag_to_pos.keys())
        for t in tags:
            if t.lower() == text:
                return t
        for t in tags:
            tl, tx = t.lower(), text
            if tl in tx or tx in tl:
                return t
        best = ""
        best_score = 0.0
        for t in tags:
            s = sequence_match_ratio(text, t.lower())
            if s > best_score:
                best_score = s
                best = t
        return best if best_score >= self._fuzzy_threshold else ""
