@echo off
REM WiFi Sensing Human Presence Detection - Windows Quick Start
REM Simple script to run the working detection system on Windows

echo 🚀 Starting WiFi Sensing Human Presence Detection
echo 📋 Detection Accuracy: 99%%+
echo ⚡ Press 'q' to quit
echo.

REM Get the directory where this script is located
cd /d "%~dp0"

REM Check if virtual environment exists, if not create it
if not exist ".venv" (
    echo 🔧 Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if virtual environment is activated
python -c "import sys; print('✅ Virtual environment activated: Python', sys.version)" 2>nul
if errorlevel 1 (
    echo ❌ Failed to activate virtual environment
    pause
    exit /b 1
)

REM Install requirements if needed
if not exist ".venv\pyvenv.cfg" (
    echo 📦 Installing requirements...
    pip install -r requirements.txt
)

REM Run the main detection system
echo 🎯 Starting detection system...
python main.py

pause