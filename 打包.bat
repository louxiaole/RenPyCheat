@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM 统一 936 代码页，避免中文乱码
for /f "tokens=2 delims=:" %%c in ('chcp') do set "OLDCP=%%c"
set "OLDCP=%OLDCP: =%"
chcp 936 >nul

REM ============================================================
REM  小乐 · Ren'Py 实时修改器 - 一键打包
REM ============================================================

set "APP_NAME=RenPyCheat"
set "PYTHON=python"
if exist "C:\Python314\python.exe" set "PYTHON=C:\Python314\python.exe"
set "PYTHONIOENCODING=gbk"

echo.
echo  ============================================
echo   Ren'Py 实时修改器 - 打包
echo  ============================================
echo.

tasklist /fi "imagename eq %APP_NAME%.exe" 2>nul | find /i "%APP_NAME%.exe" >nul
if not errorlevel 1 (
    echo  [错误] %APP_NAME%.exe 正在运行，请先关闭程序。
    goto :fail
)

echo  [1/3] PyInstaller 打包中...
"%PYTHON%" -m PyInstaller --clean --noconfirm "%APP_NAME%.spec"
if errorlevel 1 (
    echo.
    echo  [失败] 打包失败，请查看上方报错。
    goto :fail
)

echo.
echo  [2/3] 复制到工具根目录...
copy /Y "dist\%APP_NAME%.exe" "%APP_NAME%.exe" >nul
if errorlevel 1 (
    echo  [失败] 复制失败，exe 可能被占用。
    goto :fail
)

echo.
echo  [3/3] 启动测试...
start "" "%APP_NAME%.exe"
set /a TRY=0
:wait_start
timeout /t 1 /nobreak >nul
set /a TRY+=1
tasklist /fi "imagename eq %APP_NAME%.exe" 2>nul | find /i "%APP_NAME%.exe" >nul
if errorlevel 1 (
    if !TRY! lss 20 goto wait_start
    echo  [失败] 启动测试失败。
    goto :fail
)
taskkill /f /im "%APP_NAME%.exe" >nul 2>nul
echo  [3/3] 启动测试通过

echo.
echo  ============================================
echo   完成：%~dp0%APP_NAME%.exe
echo  ============================================
if defined OLDCP chcp %OLDCP% >nul
pause
exit /b 0

:fail
echo.
if defined OLDCP chcp %OLDCP% >nul
pause
exit /b 1
