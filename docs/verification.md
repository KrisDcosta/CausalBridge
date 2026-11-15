# Verification record

## CI formatting follow-up — 2026-11-14

The first published run for `4c58ad1` failed Ruff's format check on a Python
example in `docs/anm_producer.md`. Pytest did not run in that CI attempt, and
the other matrix job was cancelled. The documentation snippet is now formatted;
local Ruff lint and formatting pass. Runtime implementation is unchanged.
Inspect the follow-up branch workflow for the full Linux test/build result.

## Anish numerical engine and saved ANM originals — 2026-11-14

Base: fresh clone of merged main `48d6cda`, feature branch
`codex/anish-anm-provenance`. Local macOS arm64; locked Python 3.12.16 / NumPy 2.5.4.
These are software/synthetic checks, not live-LLM or Tuebingen benchmark outcomes.

| Check | Result |
| --- | --- |
| `bash scripts/check.sh` | Pass with `anm` extra; 410 tests, 94% overall statement coverage |
| Request persistence module | 100% statement coverage; writes originals without NumPy or any result |
| ANM numerical module | 86% statement coverage; two scores, threshold states, held-out diagnostics, typed errors, and artifact loading checked |
| Same-P(X,Y) witness | All four cells exactly 1/4 with rational arithmetic; effects exactly +3/10 and -3/10; independent engine agrees within 1e-12 |
| Merged pilot numeric labels | All independently checked against rational propensity reweighting; runtime insufficient-evidence calls remain gated |
| Kernel statistic | Mean-centered implementation agrees with an explicit H*K*H matrix reference to 1e-14 absolute tolerance |
| Nonlinear synthetic control | Predicts A_to_B; swapping columns swaps scores/direction with 1e-12 tolerance |
| Linear-Gaussian control | Can abstain with an explicit conservative smoke threshold; no universal identification claim |
| Original receipt binding | Real ANM result passes merged check_prediction with saved ANMRequestBinding; missing original abstains; substitutions fail |
| Immutable-by-API attempts | Originals remain unchanged; duplicate/interrupted attempts require fresh directories; missing request never reconstructed from result |
| Ruff lint and format | Pass; 74 Python files formatted |
| Frozen lockfile consistency | Pass |
| Track A demos | Reference and engine: each 8 traces, 4 verified / 3 unsupported / 1 wrong_operation |
| Synthetic ANM handshake | Computed ANM -> scripted S1 -> saved context -> passing S2; no extra S2 generation/calculation |
| Python 3.13.9 locked environment | All 410 tests pass, optional extra installed |
| Source archive and wheel | Build successfully; wheel contains all new numerical/request modules |
| Isolated wheel without NumPy | Track A engine demo passes; ANM returns numpy_unavailable with the original request saved |
| Isolated wheel with ANM extra | Computes ANM successfully outside the source checkout |

### Reproduce

```bash
uv sync --frozen --dev --extra anm
bash scripts/check.sh
uv lock --check
uv run --extra anm python examples/anm_integration.py --output runs/anm-handshake
```

Use a fresh handshake directory; there is no overwrite flag for trusted originals.
uv was unavailable on PATH in this session and was installed separately at
`/tmp/causalbridge-20261114-tools/bin/uv`. Prefix PATH with that directory if needed.
The full check script uses a new temporary handshake directory for repeatable runs.

Separate Python 3.13 validation, without replacing the checkout's `.venv`:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/causalbridge-anish-py313 uv sync --frozen --dev --extra anm --python 3.13
UV_PROJECT_ENVIRONMENT=/tmp/causalbridge-anish-py313 uv run --python 3.13 --extra anm --frozen pytest -q
```

One synthetic smoke run (seed 261, 256 rows, 128/128 split, uncalibrated tau=0):
score_ab=0.0014467534460217738; score_ba=0.013180269252478557;
margin=0.011733515806456783. Its checker passes. These values demonstrate the
handshake, not real-data accuracy; hardware/dependency changes can change floats.

The isolated wheel check used temporary environments, first with base dependencies
and then with the declared ANM extra. Linux CI is configured; the results above are local checks. Inspect the
feature branch workflow for remote CI status after publication. A frozen scientific tau and actual eligible observations
must come from team development work. See `anm_producer.md` for exact digest,
validation, error, and trust boundaries.

## Historical Vaishak verification — 2026-10-27

Verified on October 27, 2026, with Python 3.12.11 on macOS arm64.

| Check | Result |
| --- | --- |
| `uv sync --frozen --dev` | Locked environment installs successfully |
| `uv lock --check` | Lockfile matches package metadata |
| `uv run ruff check .` | Pass |
| `uv run ruff format --check .` | Pass |
| `uv run pytest --cov=causalbridge --cov-report=term-missing` | 67 tests pass; 88% overall coverage |
| Offline fixture demo | 8 traces: 4 verified, 3 unsupported, 1 wrong operation |
| `uv build` | Source archive and wheel built successfully |
| Isolated wheel installation and `python -m causalbridge demo` | All 8 fixture scenarios run successfully |
| Exported JSON schemas | All 8 parse successfully |
| Source archive contents | Original proposal and idea PDFs excluded |

An independent read-only review identified 2 input-handling defects. Regression
tests reproduced both before fixes: invalid benchmark root types stopped ingestion,
and validation exceptions copied rejected nested values into error traces. Both
are fixed. A pipeline regression test also verifies that operation mismatch is
classified before missing numerical evidence.

The HTTP model adapter is tested with controlled HTTP responses. Live Qwen inference
hasn't run because the machine had no Ollama executable, running server or model
weights at setup time. The fixture demo and coverage counts don't measure model
quality or the project's research hypothesis.
