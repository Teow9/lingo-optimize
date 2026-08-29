# lingo-optimize

A [ZCode](https://zcode.ai) skill that turns **LINGO 18** into a high-precision
solver callable from **Python** — for mathematical-modeling workflows
(mathematical modeling contests / operations research).

The skill's core value: LLMs routinely produce broken LINGO syntax. This skill
bundles a battle-tested syntax reference (LINGO vs legacy LINDO, 11 common
errors), verified model templates, and a zero-compilation ctypes runner, so
models are written correctly the first time — and every solve exports
structured CSVs ready for pandas/matplotlib analysis.

## What you get

| Solve produces | Content |
|---|---|
| `summary.csv` | status, objective, MIP bound/gap, iterations, model class, timing |
| `variables.csv` | every variable/attribute with value + reduced cost |
| `constraints.csv` | row names, slack/surplus, dual prices |
| `trace.csv` | solver callback trace (objective, MIP bound, incumbent) for convergence plots |
| `sensitivity.csv` | LP ranging report (objective coefficients + RHS) via `RANGES` |
| `lingo_run.log` | raw LINGO log (model echo + full solver report) |

## Requirements

- Windows + LINGO 18 installed, `LINGO64_18_HOME` set (any license that loads
  `Lingd64_18.dll`; tested with a full Site license)
- Python ≥ 3.8, standard library only (numpy not required)

## Install (as a ZCode skill)

```bash
# user-level, available in every project
cp -r lingo-optimize ~/.agents/skills/
```

Then just ask ZCode naturally, e.g. "用 LINGO 求解这个运输问题并画图" /
"solve this LP with LINGO and export CSVs". Or run the solver directly:

```bash
python lingo-optimize/scripts/lingo_runner.py model.lng \
    [--out DIR] [--inputs ptr.json] [--vars X,Y] \
    [--no-trace] [--no-sensitivity] [--global] [--timeout 300]
```

## Layout

```
SKILL.md                  # trigger + workflow + 8 hard rules + troubleshooting
scripts/lingo_runner.py   # ctypes -> Lingd64_18.dll, CSV export, subprocess timeout guard
references/
  lingo_syntax.md         # grammar reference + 11 common errors (anti-hallucination core)
  functions.md            # 127 built-in @functions with official descriptions
  data_bridge.md          # Python <-> LINGO data: inline DATA / @POINTER / @TEXT-@FILE
  model_library.md        # topic index of 120+ official sample models
assets/templates/         # verified templates: transport LP, 0-1 MIP, @POINTER bridge
```

## How it works

`lingo_runner.py` loads `Lingd64_18.dll` via `ctypes` (no compilation, no
pyLingo build needed), registers `@POINTER(n)` slots, executes a LINGO command
script (`SET ECHOIN/TERSEO/DUALCO` → `TAKE model.lng` → `GO` → `RANGES` →
`QUIT`) in a **timeout-guarded subprocess**, parses the solver report, and
writes the CSV bundle. See `SKILL.md` for the hard-won pitfalls (unquoted
`TAKE` paths, consecutive pointer slots, the `Parameter?` hang, …).

## Notes

- Sensitivity analysis applies to pure LPs only; MIP/NLP models skip it
  gracefully (LINGO error 121 is expected there).
- Non-convex NLPs: pass `--global` to `SET GLOBAL 1` (LINGO's global solver).
- Tested against LINGO 18.0.44 (LINGO DLL API `Lingd64_18`, LINDO API 12.0).
