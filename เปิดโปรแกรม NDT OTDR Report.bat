@echo off
where pythonw >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] ไม่พบ Python ในเครื่องนี้
    echo กรุณาติดตั้ง Python จาก https://www.python.org/downloads/
    echo แล้วเลือก "Add Python to PATH" ตอน install ด้วย
    echo.
    pause
    exit /b 1
)
start "" pythonw "%~dp0OTDR_Generator.pyw"
