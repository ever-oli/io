# Nuggets memory parity (IO ↔ NeoVertex1/nuggets)

IO’s `io_cli.nuggets` package targets **behavioral parity** with
[Nuggets](https://github.com/NeoVertex1/nuggets) `src/nuggets/` (MIT):

| Area | Notes |
|------|--------|
| **PRNG** | `mulberry32` + `seedFromName` — golden vectors in `tests/test_nuggets_parity.py` (cross-checked with Node). |
| **HRR core** | `bind` / `unbind` / `orthogonalize` / `sharpen` / `corvacsLite` / `softmaxTemp` / `stackAndUnitNorm` — same formulas as `core.ts`; float ops use NumPy vs JS `Float64Array` (not bitwise-identical at large `D`). |
| **Nugget** | Rebuild layout, bank sharding, recall path, hit tracking — aligned with `memory.ts`. |
| **Fuzzy keys** | Uses `nuggets_fuzzy.sequence_match_ratio` (port of Nuggets `sequenceMatchRatio` / `countMatches`), **not** Python `difflib.SequenceMatcher`. |
| **Status** | `capacity_used_pct` uses `floor(sqrt(D))` and JS-style `round(x*10)/10` like `memory.ts`. |
| **Promote** | `MEMORY.md` header and `renderMemoryMd`-style join match `promote.ts` text/layout (IO still writes under configurable `memories_dir`, not Claude Code’s `.claude/projects/...`). |

## Floating-point: is “bit-identical at D=16384” a big deal?

**Usually no.** Nuggets only **serializes facts + config** in JSON; vectors are **rebuilt** from the same PRNG and formulas. Recall picks an argmax over softmax similarities—tiny float noise almost never flips the winner unless two values are nearly tied.

**JS vs NumPy** can differ by a **few ulps** even at small `D` (same algorithm, different codegen / `fma` / reduction order). We verified **Python vs Node** on the same trace (`tests/fixtures/nuggets/ts_rebuild_d32_one_fact.mjs`): all 8 head components match within **~1e‑15** relative error; one component can differ in the last decimal printed (ULP-level).

**Practical equivalents** (pick what you need):

| Goal | Approach |
|------|-----------|
| Same **decisions** (recall answer) | Already likely; add **tolerance goldens** on `probs` / `argmax` if you want CI to enforce it. |
| Same **vectors** cross-runtime | Treat as **equivalent within ε** (`numpy.allclose` / `rtol=1e-12`, `atol=1e-14` for `float64`). |
| True **bit-identical** everywhere | Single artifact: **WASM** build from one source, or **call one runtime** (e.g. subprocess Node) for the tensor core—heavy, rarely worth it. |

IO locks **Python-internal** bit reproducibility (same inputs → same arrays) in tests; optional subprocess test checks **TS vs Py** head with tight `allclose`.

Regenerate PRNG goldens (optional):

```bash
node -e "const te=new TextEncoder();function seedFromName(name){const b=te.encode(name);const p=new Uint8Array(8);p.set(b.subarray(0,8));return (p[0]|(p[1]<<8)|(p[2]<<16)|(p[3]<<24))>>>0}
function mulberry32(seed){let s=seed|0;return()=>{s=(s+0x6d2b79f5)|0;let t=Math.imul(s^(s>>>15),1|s);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;}}
const rng=mulberry32(seedFromName('golden'));console.log(JSON.stringify([...Array(8)].map(()=>rng())));"
```
