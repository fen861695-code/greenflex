@echo off
chcp 65001 >nul
echo ========================================
echo   GreenFlex 启动脚本
echo ========================================
echo.

cd /d "%~dp0"

echo [1/5] 检查 Git 分支...
git branch --show-current
echo.

echo [2/5] 拉取最新代码...
git pull
echo.

echo [3/5] 运行数据库迁移...
cd backend
uv run alembic upgrade head
cd ..
echo.

echo [4/5] 启动后端服务 (端口 8000)...
start "GreenFlex Backend" cmd /k "cd /d %~dp0backend && uv run uvicorn greenflex.api:app --reload --port 8000"
timeout /t 3 /nobreak >nul

echo [5/5] 启动前端服务 (端口 5173)...
cd apps\web
start "GreenFlex Frontend" cmd /k "pnpm install && pnpm dev"
cd ..\..
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo.
echo   前端地址: http://localhost:5173
echo   后端地址: http://localhost:8000
echo   API文档:  http://localhost:8000/docs
echo.
echo   会自动打开浏览器...
echo.
start http://localhost:5173

pause
