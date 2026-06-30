#!/usr/bin/env bash
# Lance toute la suite de tests : backend (pytest) + E2E (Playwright) + unitaire JS (Node).
set -u
cd "$(dirname "$0")/.."

# venv
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "== Dépendances de test =="
pip install -q -r requirements-dev.txt || { echo "échec pip"; exit 1; }

# Navigateur Playwright (pour l'E2E). Sans lui, les tests E2E se skippent proprement.
python -m playwright install chromium >/dev/null 2>&1 || \
  echo "(playwright install chromium indisponible — E2E skippé)"

rc=0

echo
echo "== Backend + E2E (pytest) =="
python -m pytest tests/ -q || rc=1

echo
echo "== Unitaire JS (Node) =="
if command -v node >/dev/null 2>&1; then
  node tests/test_engine.js || rc=1
else
  echo "(node absent — test JS skippé)"
fi

echo
[ "$rc" -eq 0 ] && echo "✅ TOUT VERT" || echo "❌ ÉCHECS (voir ci-dessus)"
exit "$rc"
