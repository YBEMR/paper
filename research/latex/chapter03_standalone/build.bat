@echo off
rem ASCII-only batch script, works from Windows PowerShell or CMD.
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 exit /b 1
where xelatex >nul 2>nul
if errorlevel 1 (
  echo ERROR: xelatex not found in PATH. Install TeX Live or MiKTeX.
  exit /b 1
)
if not exist build mkdir build
if errorlevel 1 exit /b 1
for %%P in (1 2) do (
  echo Running XeLaTeX pass %%P of 2...
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error -jobname=chapter03_preview -output-directory=build main.tex >"build\chapter03_preview.compile.log" 2>&1
  if errorlevel 1 (
    echo ERROR: XeLaTeX failed. See build\chapter03_preview.compile.log
    type "build\chapter03_preview.compile.log"
    exit /b 1
  )
)
echo OK: build\chapter03_preview.pdf
exit /b 0
