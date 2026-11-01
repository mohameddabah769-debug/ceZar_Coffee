@echo off
chcp 65001 >nul
title ceZar COFFEE - Standalone POS & Management System
color 06

echo ================================================================
echo               ☕ ceZar COFFEE - نظام سيزر كوفي المتكامل ☕
echo      تطوير المهندس / محمد دباح (Eng. Mohamed Dabah) - 01095744676
echo ================================================================
echo.

cd /d "%~dp0"

:: تحديد مشغل بايثون المتاح
set "PYTHON_EXE="
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "C:\Users\moham\OneDrive\Desktop\AI_Restaurant\venv\Scripts\python.exe" set "PYTHON_EXE=C:\Users\moham\OneDrive\Desktop\AI_Restaurant\venv\Scripts\python.exe"
if not defined PYTHON_EXE (
    where python >nul 2>nul
    if %errorlevel% equ 0 set "PYTHON_EXE=python"
)

:: كشف آي بي الشبكة المحلية (Wi-Fi IP) تلقائياً
set "LOCAL_IP=127.0.0.1"
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch 'Loopback|vEthernet' -and $_.IPAddress -notmatch '^169\.' } | Select-Object -First 1).IPAddress" 2^>nul') do set "LOCAL_IP=%%i"

echo [1/2] جاري تشغيل خادم سيزر كوفي (FastAPI on Port 8000)...
start "ceZar Backend Server" cmd /k ""%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] انتظر 3 ثواني لاكتمال الإقلاع...
ping 127.0.0.1 -n 4 >nul

echo.
echo ================================================================
echo   روابط كافيه سيزر المباشرة:
echo.
echo   1. لوحة تحكم صاحب الكافيه (User: admin / Pass: 123  أو  cezar / 0000):
echo      http://127.0.0.1:8000/admin
echo.
echo   2. منيو الزبائن التفاعلي (ترابيزة 1 تجريبية):
echo      http://127.0.0.1:8000/menu?table=1
echo.
echo   3. طباعة كروت الـ QR للـ 25 ترابيزة:
echo      http://127.0.0.1:8000/qr-cards
echo.
echo   4. الرابط السحابي الدائم أونلاين:
echo      https://Deboo.pythonanywhere.com/menu?table=1
echo.
echo   * للفتح من الموبايل على نفس شبكة الواي فاي:
echo      http://%LOCAL_IP%:8000/menu?table=1
echo ================================================================
echo.
echo جاري فتح لوحة التحكم والمنيو في المتصفح...
start "" "http://127.0.0.1:8000/admin"
start "" "http://127.0.0.1:8000/menu?table=1"
start "" "http://127.0.0.1:8000/qr-cards"

pause
