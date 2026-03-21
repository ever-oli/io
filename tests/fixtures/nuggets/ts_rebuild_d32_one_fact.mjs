/**
 * Standalone rebuild trace: Nuggets core.ts + memory.ts logic for
 * name="parity", D=32, banks=1, ensembles=1, one fact k→v.
 * Run: node ts_rebuild_d32_one_fact.mjs
 * Used to cross-check io_cli.nuggets (Python) float heads vs TypeScript.
 * MIT — algorithm from github.com/NeoVertex1/nuggets
 */

function mulberry32(seed) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFromName(name) {
  const bytes = new TextEncoder().encode(name);
  const padded = new Uint8Array(8);
  padded.set(bytes.subarray(0, 8));
  return (padded[0] | (padded[1] << 8) | (padded[2] << 16) | (padded[3] << 24)) >>> 0;
}

function makeVocabKeys(V, D, rng) {
  const TWO_PI = 2 * Math.PI;
  const keys = [];
  for (let v = 0; v < V; v++) {
    const re = new Float64Array(D);
    const im = new Float64Array(D);
    for (let d = 0; d < D; d++) {
      const phi = TWO_PI * rng();
      re[d] = Math.cos(phi);
      im[d] = Math.sin(phi);
    }
    keys.push({ re, im });
  }
  return keys;
}

function makeRoleKeys(D, L) {
  const TWO_PI = 2 * Math.PI;
  const keys = [];
  for (let k = 0; k < L; k++) {
    const re = new Float64Array(D);
    const im = new Float64Array(D);
    for (let d = 0; d < D; d++) {
      const angle = (k * TWO_PI * d) / D;
      re[d] = Math.cos(angle);
      im[d] = Math.sin(angle);
    }
    keys.push({ re, im });
  }
  return keys;
}

function orthogonalize(keys, iters = 1, step = 0.4) {
  if (iters <= 0) return keys;
  const V = keys.length;
  if (V === 0) return keys;
  const D = keys[0].re.length;
  const D2 = D * 2;
  const K = new Float64Array(V * D2);
  for (let v = 0; v < V; v++) {
    const off = v * D2;
    K.set(keys[v].re, off);
    K.set(keys[v].im, off + D);
  }
  for (let iter = 0; iter < iters; iter++) {
    const G = new Float64Array(V * V);
    for (let i = 0; i < V; i++) {
      for (let j = i; j < V; j++) {
        let dot = 0;
        const offI = i * D2;
        const offJ = j * D2;
        for (let d = 0; d < D2; d++) dot += K[offI + d] * K[offJ + d];
        G[i * V + j] = dot;
        G[j * V + i] = dot;
      }
      G[i * V + i] = 0;
    }
    const correction = new Float64Array(V * D2);
    for (let i = 0; i < V; i++) {
      for (let j = 0; j < V; j++) {
        const g = G[i * V + j];
        if (g === 0) continue;
        const offI = i * D2;
        const offJ = j * D2;
        for (let d = 0; d < D2; d++) correction[offI + d] += g * K[offJ + d];
      }
    }
    const scale = step / D2;
    for (let i = 0; i < V * D2; i++) K[i] -= scale * correction[i];
    for (let v = 0; v < V; v++) {
      const off = v * D2;
      let norm = 0;
      for (let d = 0; d < D2; d++) norm += K[off + d] * K[off + d];
      norm = 1 / (Math.sqrt(norm) + 1e-9);
      for (let d = 0; d < D2; d++) K[off + d] *= norm;
    }
  }
  const result = [];
  for (let v = 0; v < V; v++) {
    const off = v * D2;
    const re = new Float64Array(D);
    const im = new Float64Array(D);
    for (let d = 0; d < D; d++) {
      const r = K[off + d];
      const imv = K[off + D + d];
      const phase = Math.atan2(imv, r);
      re[d] = Math.cos(phase);
      im[d] = Math.sin(phase);
    }
    result.push({ re, im });
  }
  return result;
}

function bind(a, b) {
  const D = a.re.length;
  const re = new Float64Array(D);
  const im = new Float64Array(D);
  for (let d = 0; d < D; d++) {
    re[d] = a.re[d] * b.re[d] - a.im[d] * b.im[d];
    im[d] = a.re[d] * b.im[d] + a.im[d] * b.re[d];
  }
  return { re, im };
}

function bankMemory(D, rng, vocabLen, factsLen, items) {
  let vocabKeys = makeVocabKeys(vocabLen, D, rng);
  vocabKeys = orthogonalize(vocabKeys, 1, 0.4);
  const sentKeys = makeVocabKeys(1, D, rng);
  const roleKeys = makeRoleKeys(D, factsLen);
  const idxW = new Map([["v", 0]]);
  const bindings = [];
  for (const { sid, pos, word } of items) {
    const sKey = sentKeys[sid];
    const rKey = roleKeys[pos];
    const wKey = vocabKeys[idxW.get(word)];
    bindings.push(bind(bind(sKey, rKey), wKey));
  }
  const re = new Float64Array(D);
  const im = new Float64Array(D);
  for (const b of bindings) {
    for (let d = 0; d < D; d++) {
      re[d] += b.re[d];
      im[d] += b.im[d];
    }
  }
  const sc = 1 / Math.sqrt(bindings.length);
  for (let d = 0; d < D; d++) {
    re[d] *= sc;
    im[d] *= sc;
  }
  return re;
}

const D = 32;
const rng = mulberry32(seedFromName("parity"));
const re = bankMemory(D, rng, 1, 1, [{ sid: 0, pos: 0, word: "v" }]);
const head = Array.from(re.subarray(0, 8));
console.log(JSON.stringify(head));
