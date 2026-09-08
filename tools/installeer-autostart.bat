@echo off
setlocal
cd /d "%~dp0\.."
set "APPDIR=%CD%"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%STARTUP%\Vitalytics.bat" echo @echo off
>> "%STARTUP%\Vitalytics.bat" echo cd /d "%APPDIR%"
>> "%STARTUP%\Vitalytics.bat" echo start "Vitalytics" /min cmd /c run.bat
echo Autostart geinstalleerd: Vitalytics start geminimaliseerd bij het inloggen.
echo App-map: %APPDIR%
echo.
echo Windows Firewall: bij de eerste start voor particuliere netwerken toestaan.
echo Verwijderen: draai verwijder-autostart.bat of wis de bat in de Startup-map.
pause
