#!/usr/bin/env bash
# Runs Command Vault's checks locally (Linux/macOS).
#   scripts/run_tests.sh          syntax check + all tests
#   scripts/run_tests.sh -k mcp   extra arguments go to pytest
# Uses a private virtualenv in .venv-test so nothing is installed system-wide.
set -u
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ ! -x .venv-test/bin/python ]; then
  echo "== Creating .venv-test (first run only)"
  "$PY" -m venv .venv-test || { echo "Could not create a virtualenv."; exit 1; }
fi
VPY=.venv-test/bin/python

if ! "$VPY" -c "import pytest" 2>/dev/null; then
  echo "== Installing pytest"
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r requirements-dev.txt || { echo "Could not install pytest."; exit 1; }
fi
# Optional (pynput needs a compiler + Python headers on some systems); tests don't require them.
for pkg in pystray pynput; do
  "$VPY" -c "import $pkg" 2>/dev/null || "$VPY" -m pip install -q "$pkg" >/dev/null 2>&1 || echo "(optional $pkg not installed; continuing)"
done

if ! "$VPY" -c "import tkinter" 2>/dev/null; then
  echo "tkinter is missing. Fedora: sudo dnf install python3-tkinter   Debian/Ubuntu: sudo apt install python3-tk"
  exit 1
fi

echo "== Syntax check"
"$VPY" -m compileall -q cmdvault main.py tests || { echo "Syntax errors found."; exit 1; }

# GUI smoke tests need a display; use a virtual one when there is none and xvfb is installed.
RUN=("$VPY" -m pytest -q "$@")
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  if command -v xvfb-run >/dev/null 2>&1; then
    echo "== No display found, using xvfb"
    RUN=(xvfb-run -a "${RUN[@]}")
  else
    echo "(no display and no xvfb: GUI smoke tests will be skipped)"
  fi
fi

echo "== Tests"
"${RUN[@]}"
status=$?
if [ $status -eq 0 ]; then echo "ALL GOOD"; else echo "FAILED (exit $status)"; fi
exit $status
