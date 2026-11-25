@echo off
title UniAssist - Policy-Grounded RAG Helpdesk
echo =====================================================================
echo   UniAssist: Policy-Grounded RAG & Intent-Aware Virtual Helpdesk
echo   Dayananda Sagar University - MCA Ready To Deploy (RTD) Project
echo =====================================================================
echo.

set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_CMD%" (
    set "PYTHON_CMD=python"
)

echo Starting Flask server on http://127.0.0.1:5050 ...
start "" http://127.0.0.1:5050
"%PYTHON_CMD%" "%~dp0app.py"
pause
