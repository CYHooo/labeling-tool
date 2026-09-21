@echo off
rem Launch the few-shot annotation tool (SAM3/SAM2, needs torch).
rem Double-click, or run from anywhere: run_fewshot.bat [args...]  (arguments are passed through)
rem Uses .venv\Scripts\python.exe when present, otherwise python on PATH.
setlocal

rem Work from the repo root so the package and relative paths (.\checkpoint) resolve.
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

"%PY%" -m annotation_tool.main %*
set "RC=%ERRORLEVEL%"

rem Keep the console open on failure so the error message can be read.
if not "%RC%"=="0" (
    echo.
    echo [ERROR] annotation_tool.main exited with code %RC%.
    echo If python was not found, create the virtualenv first - see README.md.
    pause
)
endlocal & exit /b %RC%
