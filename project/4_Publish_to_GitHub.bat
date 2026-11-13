@echo off
rem Publishes 03_Outputs\website to the repositories in 02_Analysis\github_targets.csv
cd /d "%~dp002_Analysis"
where py >nul 2>nul
if %errorlevel%==0 (py publish_github.py) else (python publish_github.py)
if errorlevel 9009 (echo Python not found. Install it from python.org, tick "Add to PATH". & pause)
