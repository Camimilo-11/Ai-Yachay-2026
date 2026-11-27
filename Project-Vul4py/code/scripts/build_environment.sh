#!/usr/bin/env bash
# build_environment.sh (v2) -- build and validate the Vul4Py test environment. No API calls.
#
#   bash scripts/build_environment.sh [JOBS] [ROUNDS]
#
# Run it inside tmux, with the repository's .venv activated. Resumable: re-running skips the steps
# whose output already exists. On a 2-vCPU / 8-GiB machine expect several hours; time is not an issue.
#
# Steps (the benchmark's own scripts, plus the harness fixes documented in each wrapper):
#   1. prepare_robust.py   = prepare.py + fetch-by-SHA when a fix commit is only on a PR ref
#   2. apply_overrides.py  per-case fixes in dataset/meta_overrides: the benchmark's own, plus the
#                          environment fixes found case by case (test dependencies, era-appropriate
#                          Python and library versions, env-noise deselects); each one has a _note
#   3. scan_wrapper.py     = vul4py.py scan + a snapshot of what each install builds in the checkout
#   4. ROUNDS times        auto_skip.py (deselect tests that fail on the FIXED version) -> rescan
#   5. preflight.py        oracle control on every OK case (report only)
#   6. oracle_repair.py    deselect baseline tests that assert the vulnerable behaviour (they fail
#                          with the upstream fix itself) -> oracle control again -> samples
#
# Environment variables (for tests): CSV, WS, PREFLIGHT_DIR, MAIN_SIZE, PILOT_SIZE.
set -euo pipefail
cd "$(dirname "$0")/.."

JOBS="${1:-$(nproc)}"
ROUNDS="${2:-3}"
CSV="${CSV:-dataset/vul4py.csv}"
WS="${WS:-workspaces}"
PREFLIGHT_DIR="${PREFLIGHT_DIR:-runs/preflight}"
MAIN_SIZE="${MAIN_SIZE:-all}"
PILOT_SIZE="${PILOT_SIZE:-5}"
REPORT="$WS/scan_report.tsv"

command -v python >/dev/null || { echo "Activate the virtual environment first: source .venv/bin/activate"; exit 1; }
python -c "import openai" 2>/dev/null || { echo "Missing package: python -m pip install openai"; exit 1; }
# The era-level overrides (old projects) install their dependencies with uv; the case venvs find it on PATH.
command -v uv >/dev/null || { echo "Missing tool: python -m pip install uv==0.11.32"; exit 1; }

summary() { awk -F'\t' 'NR>1{c[$2]++} END{for(k in c) printf "%s=%d ", k, c[k]; print ""}' "$REPORT"; }
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# pytest 9 turned several old practices into errors; every test environment uses the last 8.x.
mkdir -p "$WS"
echo "pytest<9" > "$WS/pip_constraints.txt"
export PIP_CONSTRAINT="$(cd "$WS" && pwd)/pip_constraints.txt"
# Per pytest run cap (Vul4Py's default is 900 s): gradio's suite takes about 35 min on 2 vCPU.
export VUL4PY_TEST_TIMEOUT="${VUL4PY_TEST_TIMEOUT:-3600}"
# As in the validation: no uv cache (the era-level installs would otherwise keep every wheel, 10+ GB).
export UV_NO_CACHE=1
# Disk: about 11 GB of clones, 35 GB of venvs kept for evaluation (gradio and smolagents install the
# full torch, ~5 GB each), and a build peak near 65 GB.
FREE_GB=$(df -BG --output=avail . | tail -1 | tr -dc 0-9)
if [ ! -f "$WS/prepare_done" ] && [ "${FREE_GB:-0}" -lt 70 ]; then
  echo "[!] Only ${FREE_GB} GB free here; the build peaks near 65 GB. Grow the volume before going on."
fi

if [ ! -f "$WS/prepare_done" ]; then
  echo "[$(stamp)] 1/6 prepare (100 cases, two clones each)"
  python scripts/prepare_robust.py --csv "$CSV" --workspace-root "$WS" --jobs 4
  touch "$WS/prepare_done"
fi
echo "[$(stamp)] 2/6 apply_overrides"
python scripts/apply_overrides.py --workspaces "$WS" | tail -1

if [ ! -f "$WS/scan_report_round0.tsv" ]; then
  echo "[$(stamp)] 3/6 scan ($JOBS jobs)"
  python scripts/scan_wrapper.py --workspace-root "$WS" scan --jobs "$JOBS" --timeout 10800
  cp "$REPORT" "$WS/scan_report_round0.tsv"
fi
echo "[$(stamp)] round 0: $(summary)"

for k in $(seq 1 "$ROUNDS"); do
  [ -f "$WS/scan_report_round$k.tsv" ] && { echo "[round $k] already done"; continue; }
  NOK=$(awk -F'\t' 'NR>1 && $2!="OK"{print $1}' "$REPORT" | paste -sd, -)
  [ -z "$NOK" ] && break
  echo "[$(stamp)] 4/6 round $k: auto_skip + rescan of the cases that are not OK"
  python scripts/auto_skip.py --workspaces "$WS" | tail -1
  python scripts/apply_overrides.py --workspaces "$WS" | tail -1
  # fresh environments, as in the validation: vul4py.py would otherwise install on top of the old venv
  for v in $(echo "$NOK" | tr ',' ' '); do rm -rf "$WS/$v/vulnerable/.venv" "$WS/$v/fixed/.venv"; done
  python scripts/scan_wrapper.py --workspace-root "$WS" scan --jobs "$JOBS" --only "$NOK" --timeout 10800
  cp "$REPORT" "$WS/scan_report_round$k.tsv"
  echo "[$(stamp)] round $k: $(summary)"
done

# Disk: evaluations only use vulnerable/.venv (exploit tests run in the target's venv), so the
# fixed-side venvs and the download caches go (tens of GB with the torch-based cases).
for d in "$WS"/*/fixed/.venv; do [ -d "$d" ] && rm -rf "$d"; done
python -m pip cache purge >/dev/null 2>&1 || true
uv cache prune >/dev/null 2>&1 || true
echo "[$(stamp)] disk after cleanup: $(df -h . | awk 'NR==2{print $4" free of "$2}')"

# One oracle-control session for the whole build: re-running reuses every check already done.
SESSION_FILE="$PREFLIGHT_DIR/.session"
mkdir -p "$PREFLIGHT_DIR"
[ -f "$SESSION_FILE" ] || echo "preflight-$(date -u +%Y%m%dT%H%M%SZ)" > "$SESSION_FILE"
SESSION=$(cat "$SESSION_FILE")
echo "[$(stamp)] 5/6 oracle control (report only, session $SESSION)"
python scripts/preflight.py --workspaces "$WS" --runs "$PREFLIGHT_DIR" --jobs 1 --report-only --session "$SESSION"
echo "[$(stamp)] 6/6 oracle repair, re-check of the repaired cases, samples"
python scripts/oracle_repair.py --runs "$PREFLIGHT_DIR" --workspaces "$WS"
while read -r v; do [ -n "$v" ] && rm -f "$PREFLIGHT_DIR/_baseline/$v/env_check.json"; done < "$PREFLIGHT_DIR/oracle_repaired.txt"
python scripts/preflight.py --workspaces "$WS" --runs "$PREFLIGHT_DIR" --jobs 1 --session "$SESSION" \
  --main-size "$MAIN_SIZE" --pilot-size "$PILOT_SIZE"

# Reproducibility record, kept next to the samples.
rm -rf "$PREFLIGHT_DIR/meta_overrides_used"
cp -r dataset/meta_overrides "$PREFLIGHT_DIR/meta_overrides_used"
cp "$WS"/scan_report*.tsv "$WS/pip_constraints.txt" "$PREFLIGHT_DIR/"
{
  echo "built_at_utc: $(stamp)"
  echo "vul4py_commit: $(git rev-parse HEAD)"
  echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "kernel: $(uname -sr)  arch: $(uname -m)  cpus: $(nproc)  mem: $(free -g | awk '/Mem:/{print $2}') GiB"
  echo "python: $(python --version 2>&1)"
  echo "pip_constraint: $(cat "$WS/pip_constraints.txt")"
  echo "auto_skip_rounds: $ROUNDS"
  echo "scan: $(summary)"
} > "$PREFLIGHT_DIR/environment.txt"

echo
echo "=========================== ENVIRONMENT READY ==========================="
cat "$PREFLIGHT_DIR/environment.txt"
python - "$PREFLIGHT_DIR/split.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print(f"scan OK: {s['candidates']}   oracle-valid: {s['oracle_valid']}   "
      f"main sample: {s['main']['size']}   pilot sample: {s['pilot']['size']}")
PY
echo "Not valid, and why: $PREFLIGHT_DIR/oracle_report.tsv"
echo "Samples: $PREFLIGHT_DIR/main_ids.txt and $PREFLIGHT_DIR/pilot_ids.txt"
