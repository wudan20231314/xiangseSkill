@echo off
setlocal
if "%~2"=="" (
  echo Usage: %~nx0 ^<input.json^> ^<output.xbs^>
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
%PYTHON_BIN% "%~dp0xbs_tool.py" json2xbs -i "%~1" -o "%~2"
if not %errorlevel%==0 (
  echo ERROR: json2xbs failed.
  exit /b %errorlevel%
)
endlocal
