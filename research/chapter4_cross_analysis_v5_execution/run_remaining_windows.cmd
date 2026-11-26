@echo off
setlocal
pushd "%~dp0..\..\.."
if errorlevel 1 exit /b 1
"F:\Anaconda3\python.exe" -B -u "%~dp0continue_unopened.py" --repo "Ch3_final_worktree" --run "Ch4_cross_v5_runs_20261126" --after-continuation-02
set "ch4_exit=%errorlevel%"
popd
echo.
echo Chapter 4 runner exit code: %ch4_exit%
pause
exit /b %ch4_exit%
