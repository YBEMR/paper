@echo off
rem ASCII-only for Windows code page compatibility.
setlocal EnableExtensions
cd /d "%~dp0"
where xelatex >nul 2>nul
if errorlevel 1 (
  echo ERROR: xelatex not found. Install TeX Live or MiKTeX.
  exit /b 1
)
if not exist build mkdir build
for %%P in (1 2) do (
  echo XeLaTeX pass %%P/2
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error -jobname=chapter03_revised -output-directory=build main.tex >"build\chapter03_revised.compile.log" 2>&1
  if errorlevel 1 (
    echo ERROR: XeLaTeX failed. See build\chapter03_revised.compile.log
    type "build\chapter03_revised.compile.log"
    exit /b 1
  )
)
echo OK: build\chapter03_revised.pdf
exit /b 0
