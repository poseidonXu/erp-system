@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   华晟 ERP 系统启动器
echo ============================================
echo.
echo [1/2] 检查数据库依赖...
python -c "import psycopg2" 2>nul
if errorlevel 1 (
  echo  installing dependencies...
  python -m pip install -r requirements.txt
)
echo.
echo [2/2] 启动后端服务...
echo 浏览器访问: http://127.0.0.1:5000
echo 按 Ctrl+C 停止服务
echo.
cd backend
if "%ERP_DB_PASSWORD%"=="" set ERP_DB_PASSWORD=highgo5866
python app.py
pause
