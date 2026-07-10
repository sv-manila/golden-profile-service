@echo off
REM Start the Golden Profile Service for the local StreamlineVerify VM.
REM Binds to 0.0.0.0 so the Vagrant VM can reach it at http://192.168.56.1:8137
cd /d "%~dp0"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8137
