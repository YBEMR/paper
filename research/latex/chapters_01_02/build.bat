@echo off
rem 编译到独立 build\ 目录，Windows需安装 MiKTeX 或 TeX Live。
setlocal
cd /d "%~dp0"
where xelatex >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 请安装 XeLaTeX 并将其添加到 PATH。
  exit /b 1
)
if not exist build mkdir build
if /I "%~1"=="chapter01" goto one
if /I "%~1"=="chapter02" goto two
if /I "%~1"=="combined" goto combined
if not "%~1"=="" if /I not "%~1"=="all" (
  echo 用法：build.bat [all^|combined^|chapter01^|chapter02]
  exit /b 2
)
call :compile main chapters_01_02_preview
if errorlevel 1 exit /b 1
call :compile chapter01_only chapter01_preview
if errorlevel 1 exit /b 1
call :compile chapter02_only chapter02_preview
exit /b %errorlevel%
:combined
call :compile main chapters_01_02_preview
exit /b %errorlevel%
:one
call :compile chapter01_only chapter01_preview
exit /b %errorlevel%
:two
call :compile chapter02_only chapter02_preview
exit /b %errorlevel%
:compile
for %%P in (1 2) do (
  xelatex -interaction=nonstopmode -halt-on-error -file-line-error -jobname=%2 -output-directory=build %1.tex >"build\%2.compile.log" 2>&1
  if errorlevel 1 (
    type "build\%2.compile.log"
    exit /b 1
  )
)
echo 已生成：build\%2.pdf
exit /b 0
