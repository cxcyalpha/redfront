@echo off
rem redfront: campaign window in the browser. First run creates .venv and installs requirements.
rem Text menu instead of the window: run.bat menu [campaign.json]
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: creating .venv in %CD% ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Could not create .venv: install Python 3.10+ from python.org with "Add to PATH".
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Could not install requirements: pydcs is installed from GitHub, git is required - git-scm.com
    pause
    exit /b 1
  )
)
rem new requirements (Pillow - kneeboard) for an existing .venv
".venv\Scripts\python.exe" -c "import PIL" 2>nul || ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if /i "%~1"=="menu" (
  ".venv\Scripts\python.exe" -m redfront menu %2
) else (
  ".venv\Scripts\python.exe" -m redfront gui %*
)
pause
