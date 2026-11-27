@echo off
setlocal
pushd "%~dp0..\..\.."
if errorlevel 1 exit /b 1
if exist "Ch4_cross_v5_runs_20261126\windows_26300\registration.json" (
    if not exist "Ch4_cross_v5_runs_20261126\windows_26300\formal\batch_start.json" (
        "F:\Anaconda3\python.exe" -B -u "%~dp0windows_26300.py" prepare --repo "Ch3_final_worktree" --run "Ch4_cross_v5_runs_20261126"
        if errorlevel 1 goto finish
    )
    "F:\Anaconda3\python.exe" -B -u "%~dp0windows_26300.py" remaining --repo "Ch3_final_worktree" --run "Ch4_cross_v5_runs_20261126"
) else if exist "Ch4_cross_v5_runs_20261126\continuation_03\continuation.json" (
    "F:\Anaconda3\python.exe" -B -u "%~dp0pending_cells.py" --repo "Ch3_final_worktree" --run "Ch4_cross_v5_runs_20261126" --loop
) else (
    "F:\Anaconda3\python.exe" -B -u "%~dp0continue_unopened.py" --repo "Ch3_final_worktree" --run "Ch4_cross_v5_runs_20261126" --after-continuation-02
)
:finish
set "ch4_exit=%errorlevel%"
popd
echo.
echo Chapter 4 runner exit code: %ch4_exit%
pause
exit /b %ch4_exit%
