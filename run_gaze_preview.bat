@echo off
setlocal
cd /d "%~dp0"
echo Live gaze + pupil overlay (same camera rules as the game gaze sidecar).
echo Edit config.json: gaze_camera_index, gaze_opencv_dshow_first, gaze_capture_* 
echo Press Q in the video window to quit.
echo.
python gaze_realtime_preview.py
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" echo Exit code %ERR%
pause
exit /b %ERR%
