@echo off
rem Runs Command Vault's checks locally on Windows. Extra arguments go to pytest.
cd /d "%~dp0\.."
if not exist .venv-test\Scripts\python.exe (
  echo == Creating .venv-test (first run only)
  py -3 -m venv .venv-test || python -m venv .venv-test || (echo Could not create a virtualenv. & exit /b 1)
  .venv-test\Scripts\python -m pip install -q --upgrade pip
)
.venv-test\Scripts\python -c "import pytest" 2>nul || (
  echo == Installing pytest
  .venv-test\Scripts\python -m pip install -q -r requirements-dev.txt || (echo Could not install pytest. & exit /b 1)
)
.venv-test\Scripts\python -c "import pystray" 2>nul || .venv-test\Scripts\python -m pip install -q pystray pynput >nul 2>&1
echo == Syntax check
.venv-test\Scripts\python -m compileall -q cmdvault main.py tests || (echo Syntax errors found. & exit /b 1)
echo == Tests
.venv-test\Scripts\python -m pytest -q %*
if errorlevel 1 (echo FAILED & exit /b 1)
echo ALL GOOD
