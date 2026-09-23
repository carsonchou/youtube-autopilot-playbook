@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  python --version >nul 2>nul || (
    echo 找不到 Python。請到 https://www.python.org/downloads/ 安裝，安裝時勾選「Add python.exe to PATH」，裝好再雙擊一次這個檔案。
    pause
    exit /b 1
  )
  echo 第一次使用，正在準備環境，約需一兩分鐘……
  python -m venv .venv || (pause & exit /b 1)
)
"%PY%" -c "import yaml, PIL, edge_tts, openai, googleapiclient, google_auth_oauthlib" >nul 2>nul || (
  echo 正在安裝需要的套件……
  "%PY%" -m pip install -q -r requirements.txt || (
    echo 安裝失敗，請把上面的訊息截圖求助。
    pause
    exit /b 1
  )
)
"%PY%" -m pipeline.web
pause
