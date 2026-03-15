@echo off
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Launching app...
python main.py
pause
