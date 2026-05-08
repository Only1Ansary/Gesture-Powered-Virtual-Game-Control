@echo off
setlocal
cd /d "%~dp0"

echo Launching C# FruitNinjaGame GUI...
echo.
echo reacTIVision: GUI kills any previous session, then writes camera.xml (reactvision_camera_index / reactvision_camera_name_contains).
echo reacTIVision saves camera.xml on exit — do not Sync before Kill or shutdown will overwrite your laptop cam choice.
echo Camera list: reacTIVision-1.5.1-win64\reacTIVision.exe -l
echo.

where dotnet >nul 2>nul
if errorlevel 1 (
  echo ERROR: .NET SDK is not installed or not in PATH.
  echo Install .NET SDK and try again.
  pause
  exit /b 1
)

if not exist "config.json" (
  echo WARNING: config.json was not found in repo root.
  echo The app will start, but TUIO/reacTIVision config may fail.
  echo.
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$cfg = Get-Content -Raw 'config.json' | ConvertFrom-Json; " ^
    "$rx = [string]$cfg.reactvision_exe; " ^
    "if ([string]::IsNullOrWhiteSpace($rx)) { Write-Host 'WARNING: reactvision_exe is empty in config.json.'; exit 0 }; " ^
    "$full = if ([System.IO.Path]::IsPathRooted($rx)) { $rx } else { Join-Path (Get-Location) $rx }; " ^
    "if (-not (Test-Path $full)) { Write-Host ('WARNING: reacTIVision not found at: ' + $full); Write-Host 'TUIO may not work until this path is fixed.' } else { Write-Host ('reacTIVision found: ' + $full) }"
  echo.
)

dotnet run --project "FruitNinjaGame\FruitNinjaGame.csproj"
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo C# FruitNinjaGame GUI exited with code %ERR%.
) else (
  echo C# FruitNinjaGame GUI exited normally.
)
pause
exit /b %ERR%
