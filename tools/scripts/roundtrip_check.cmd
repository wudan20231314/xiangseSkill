@echo off
setlocal
if "%~2"=="" (
  echo Usage: %~nx0 ^<input.json^> ^<output_prefix^>
  exit /b 1
)
set "PYTHON_BIN="
where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_BIN=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PYTHON_BIN=python"
  )
)
if "%PYTHON_BIN%"=="" (
  echo ERROR: Python not found. Install Python 3 and ensure ^'py^' or ^'python^' is in PATH.
  exit /b 2
)
%PYTHON_BIN% "%~dp0xbs_tool.py" roundtrip -i "%~1" -p "%~2"
if not %errorlevel%==0 (
  echo ERROR: roundtrip failed.
  exit /b %errorlevel%
)
endlocal
