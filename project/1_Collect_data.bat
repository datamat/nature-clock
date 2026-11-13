@echo off
rem Pulls the top-20 words from Google Trends into 01_Data_raw
cd /d "%~dp002_Analysis"
where py >nul 2>nul
if %errorlevel%==0 (py collect_trends.py) else (python collect_trends.py)
if errorlevel 9009 (echo Python not found. Install it from python.org, tick "Add to PATH". & pause)
