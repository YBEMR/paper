@echo off
rem ASCII-only batch file for Windows CMD and PowerShell.
setlocal EnableExtensions
cd /d "%~dp0"
if errorlevel 1 exit /b 1

where xelatex >nul 2>nul
if errorlevel 1 (
    echo ERROR: xelatex is not available in PATH. Install MiKTeX or TeX Live.
    exit /b 1
)

if not exist "build" mkdir "build"
if errorlevel 1 exit /b 1

if "%~1"=="" goto :all
if /I "%~1"=="all" goto :all
if /I "%~1"=="combined" goto :combined
if /I "%~1"=="chapter01" goto :chapter01
if /I "%~1"=="chapter02" goto :chapter02

echo Usage: build.bat [all, combined, chapter01, chapter02]
exit /b 2

:all
call :compile main chapters_01_02_preview
if errorlevel 1 exit /b 1
call :compile chapter01_only chapter01_preview
if errorlevel 1 exit /b 1
call :compile chapter02_only chapter02_preview
if errorlevel 1 exit /b 1
exit /b 0

:combined
call :compile main chapters_01_02_preview
exit /b %errorlevel%

:chapter01
call :compile chapter01_only chapter01_preview
exit /b %errorlevel%

:chapter02
call :compile chapter02_only chapter02_preview
exit /b %errorlevel%

:compile
echo [1/2] Compiling %~1.tex
xelatex -interaction=nonstopmode -halt-on-error -file-line-error -jobname=%~2 -output-directory=build "%~1.tex" >"build\%~2.compile.log" 2>&1
if errorlevel 1 goto :compile_failed

echo [2/2] Compiling %~1.tex
xelatex -interaction=nonstopmode -halt-on-error -file-line-error -jobname=%~2 -output-directory=build "%~1.tex" >"build\%~2.compile.log" 2>&1
if errorlevel 1 goto :compile_failed

echo OK: build\%~2.pdf
exit /b 0

:compile_failed
echo ERROR: Compilation of %~1.tex failed. Compiler output:
type "build\%~2.compile.log"
exit /b 1
