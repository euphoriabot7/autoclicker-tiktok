@echo off
rem Alternativa si el .exe no arranca: usa Python directamente (sin consola)
cd /d "%~dp0"
start "" pythonw "%~dp0autoclicker_tiktok.py"
