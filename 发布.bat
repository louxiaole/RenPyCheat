@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM 统一 936 代码页，避免中文乱码
for /f "tokens=2 delims=:" %%c in ('chcp') do set "OLDCP=%%c"
set "OLDCP=%OLDCP: =%"
chcp 936 >nul

REM ============================================================
REM  小乐 · 游戏实时修改器 - 一键发布
REM  用法：发布.bat            版本号自动从 core\version.py 读取
REM        发布.bat 1.0.1      指定版本号
REM  产出：发布包\v<版本>\RenPyCheat.exe
REM        发布包\RenPyCheat_v<版本>.zip   ← 上传到 GitHub Release 用这个
REM        备份\<版本>\                   ← 源码快照
REM ============================================================

set "APP_NAME=RenPyCheat"
set "PYTHON=python"
if exist "C:\Python314\python.exe" set "PYTHON=C:\Python314\python.exe"
set "PYTHONIOENCODING=gbk"

set "VER=%~1"
if "%VER%"=="" (
    for /f "delims=" %%v in ('%PYTHON% -c "from core.version import APP_VERSION;print(APP_VERSION)"') do set "VER=%%v"
)
if "%VER%"=="" (
    echo  [失败] 无法读取版本号，请执行：发布.bat 1.0.0
    goto :fail
)

echo.
echo  ============================================
echo   发布 %APP_NAME% v%VER%
echo  ============================================
echo.

tasklist /fi "imagename eq %APP_NAME%.exe" 2>nul | find /i "%APP_NAME%.exe" >nul
if not errorlevel 1 (
    echo  [错误] %APP_NAME%.exe 正在运行，请先关闭程序再发布。
    goto :fail
)

echo  [1/5] PyInstaller 打包中...
"%PYTHON%" -m PyInstaller --clean --noconfirm "%APP_NAME%.spec"
if errorlevel 1 (
    echo  [失败] 打包失败，请查看上方报错。
    goto :fail
)

echo  [2/5] 复制 exe 到工具根目录...
copy /Y "dist\%APP_NAME%.exe" "%APP_NAME%.exe" >nul
if errorlevel 1 (
    echo  [失败] 复制失败，exe 可能被占用。
    goto :fail
)

echo  [3/5] 生成发布包目录 发布包\v%VER% ...
if not exist "发布包" mkdir "发布包"
if not exist "发布包\v%VER%" mkdir "发布包\v%VER%"
copy /Y "%APP_NAME%.exe" "发布包\v%VER%\%APP_NAME%.exe" >nul
if errorlevel 1 (
    echo  [失败] 复制到发布包失败。
    goto :fail
)

echo  [4/5] 生成更新压缩包 RenPyCheat_v%VER%.zip ...
if exist "发布包\%APP_NAME%_v%VER%.zip" del /f /q "发布包\%APP_NAME%_v%VER%.zip" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Force -Path '发布包\v%VER%\%APP_NAME%.exe' -DestinationPath '发布包\%APP_NAME%_v%VER%.zip'"
if errorlevel 1 (
    echo  [失败] 压缩失败。
    goto :fail
)

echo  [5/5] 备份本版源码到 备份\%VER% ...
if not exist "备份" mkdir "备份"
if not exist "备份\%VER%" mkdir "备份\%VER%"
robocopy "." "备份\%VER%" main.py RenPyCheat.spec 打包.bat 发布.bat 小乐工具.ico /NFL /NDL /NJH /NJS >nul
robocopy "core" "备份\%VER%\core" /E /XD __pycache__ /NFL /NDL /NJH /NJS >nul
robocopy "gui" "备份\%VER%\gui" /E /XD __pycache__ /NFL /NDL /NJH /NJS >nul
robocopy "mod" "备份\%VER%\mod" /E /NFL /NDL /NJH /NJS >nul
robocopy "assets" "备份\%VER%\assets" /E /NFL /NDL /NJH /NJS >nul

echo.
echo  ============================================
echo   发布完成
echo   exe     ：%~dp0发布包\v%VER%\%APP_NAME%.exe
echo   zip     ：%~dp0发布包\%APP_NAME%_v%VER%.zip
echo   源码备份：%~dp0备份\%VER%
echo.
echo   上传 GitHub Release 时：tag = v%VER%，附件选上面那个 zip
echo  ============================================
if defined OLDCP chcp %OLDCP% >nul
pause
exit /b 0

:fail
echo.
if defined OLDCP chcp %OLDCP% >nul
pause
exit /b 1
