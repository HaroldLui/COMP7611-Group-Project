#!/usr/bin/env bash
# One-command demo. Offline by default (fake model, no API key, no cost).
#   ./demo.sh                 offline demo
#   ./demo.sh deepseek        also check a real profile from configs/models.toml (2-3 tiny API calls)
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null || { echo "python3 not found. Install it from python.org or: brew install python"; exit 1; }
$PY -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11+ needed (have $($PY -V))."; exit 1; }

if [ ! -d .venv ]; then
  echo "== creating virtual environment (.venv)"
  $PY -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip >/dev/null
pip install -q -r requirements.txt

echo; echo "== 1. generating scenarios"
python data/make_scenarios.py

echo; echo "== 2. running tests"
python -m unittest discover -s tests 2>&1 | tail -3

echo; echo "== 3. running all 5 configurations on the dev split (fake model)"
rm -rf results/demo
python -m harness.run --profile fake --split dev --out results/demo 2>/dev/null

echo; echo "== 4. results table"
python -m harness.analyze results/demo | sed -n '/## By configuration/,/## Primary/p' | sed '$d'

echo; echo "== 5. trace: free-text pipeline (M1) laundering a redirect attack"
python -m harness.show results/demo --config M1 --goal G1 | tail -25

echo; echo "== 6. trace: JSON pipeline (M2) on the same kind of attack"
python -m harness.show results/demo --config M2 --goal G1 | tail -8

if [ "${1:-}" != "" ]; then
  echo; echo "== 7. checking real profile '$1'"
  [ -f .env ] || { echo "No .env file: run 'cp .env.example .env' and add your key."; exit 1; }
  python -m harness.check --profile "$1"
fi

echo; echo "Done. Full summary: results/demo/summary.md"
echo "Reminder: the fake model is a rule-based stand-in; its numbers are not results."
