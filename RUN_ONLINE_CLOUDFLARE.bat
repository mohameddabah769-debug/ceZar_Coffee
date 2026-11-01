@echo off
chcp 65001 >nul
title ceZar COFFEE - Cloudflare Online Live System
color 0b

echo ================================================================
echo          ☕ ceZar COFFEE - تشغيل النظام أونلاين عبر الإنترنت ☕
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

echo [1/2] التأكد من تشغيل خادم سيزر كوفي المحلي...
netstat -ano | findstr :8000 >nul
if %errorlevel% neq 0 (
    start "ceZar Backend Server" cmd /k ""%PYTHON_EXE%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    ping 127.0.0.1 -n 4 >nul
)

echo [2/2] جاري تشغيل نفق Cloudflare المباشر...
echo ----------------------------------------------------------------
echo هام: نافذة Cloudflare ستعرض لك الرابط الجديد https://xxx.trycloudflare.com
echo اترك هذه النافذة مفتوحة طالما تريد إتاحة السيستم عبر الإنترنت لأي موبايل!
echo ----------------------------------------------------------------
echo.
"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000
pause
