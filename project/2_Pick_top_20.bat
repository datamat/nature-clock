@echo off
rem Ranks the candidate words, rewrites topics.csv (only when candidates change)
cd /d "%~dp002_Analysis"
where py >nul 2>nul
if %errorlevel%==0 (py rank_candidates.py) else (python rank_candidates.py)
if errorlevel 9009 (echo Python not found. Install it from python.org, tick "Add to PATH". & pause)
