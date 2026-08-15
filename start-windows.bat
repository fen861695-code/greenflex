@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GreenFlex 启动脚本
echo ========================================
echo.
cd /d "%~dp0"

REM === 端口配置（可通过环境变量覆盖）===
if not defined BACKEND_PORT set BACKEND_PORT=8000
if not defined FRONTEND_PORT set FRONTEND_PORT=5173

REM === [1/6] 检查端口占用 ===
echo [1/6] 检查端口占用...
set PORT_OK=1

netstat -aon | findstr ":%BACKEND_PORT% " | findstr LISTENING >nul 2>&1
if %errorlevel%==0 (
    echo   [警告] 后端端口 %BACKEND_PORT% 已被占用
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%BACKEND_PORT% " ^| findstr LISTENING') do (
        for /f "tokens=1" %%p in ('tasklist /fi "PID eq %%a" /nh ^| findstr /v "信息:"') do (
            echo          占用进程: %%p ^(PID: %%a^)
        )
    )
    choice /c YN /m "  是否终止该进程并继续? (Y=终止, N=换端口)"
    if !errorlevel!==1 (
        for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%BACKEND_PORT% " ^| findstr LISTENING') do (
            taskkill /f /pid %%a >nul 2>&1
        )
        echo   已终止占用进程
    ) else (
        set /a BACKEND_PORT+=1
        echo   将使用端口 !BACKEND_PORT!
    )
)

netstat -aon | findstr ":%FRONTEND_PORT% " | findstr LISTENING >nul 2>&1
if %errorlevel%==0 (
    echo   [提示] 前端端口 %FRONTEND_PORT% 已被占用，Vite 将自动切换到下一个可用端口
)

timeout /t 1 /nobreak >nul

echo.
echo [2/6] 检查 Git 分支...
git branch --show-current
echo.
echo [3/6] 拉取最新代码...
git pull
echo.
echo [4/6] 运行数据库迁移...
cd backend
uv run alembic upgrade head
cd ..
echo.
echo [5/6] 启动后端服务 (端口 %BACKEND_PORT%)...
start "GreenFlex Backend" cmd /k "cd /d %~dp0backend && set GREENFLEX_API_PORT=%BACKEND_PORT% && uv run uvicorn greenflex.api:app --reload --port %BACKEND_PORT%"
timeout /t 3 /nobreak >nul
echo [6/6] 启动前端服务 (端口 %FRONTEND_PORT%)...
cd apps\web
start "GreenFlex Frontend" cmd /k "set GREENFLEX_API_PORT=%BACKEND_PORT% && pnpm install && pnpm dev"
cd ..\..
timeout /t 5 /nobreak >nul
echo.
echo ========================================
echo   启动完成！
echo ========================================
echo.
echo   前端地址: http://localhost:%FRONTEND_PORT%
echo   后端地址: http://localhost:%BACKEND_PORT%
echo   API文档:  http://localhost:%BACKEND_PORT%/docs
echo.
echo   会自动打开浏览器...
echo   ^(如果前端端口被占，Vite 会自动切换，请注意前端窗口的提示^)
echo.
start http://localhost:%FRONTEND_PORT%
pause
