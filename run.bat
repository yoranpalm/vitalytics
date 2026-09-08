@echo off
cd /d "%~dp0"
rem hosting op het thuisnetwerk: bereikbaar voor telefoon/tablet/laptop
set VITALYTICS_HOST=0.0.0.0
echo [%date% %time%] app gestart > data\app.log
:loop
python app.py >> data\app.log 2>&1
echo [%date% %time%] server gestopt - herstart in 3 sec >> data\app.log
timeout /t 3 /nobreak >nul
goto loop