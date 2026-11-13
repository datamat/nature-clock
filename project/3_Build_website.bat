@echo off
rem Analysis, charts plus website in 03_Outputs
cd /d "%~dp002_Analysis"
where py >nul 2>nul
if %errorlevel%==0 (py nature_clock.py) else (python nature_clock.py)
if errorlevel 9009 (echo Python not found. Install it from python.org, tick "Add to PATH". & pause)
