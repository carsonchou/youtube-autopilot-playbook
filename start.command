#!/bin/bash
# macOS:雙擊開啟設定精靈。第一次會建立 .venv 並安裝套件。
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "找不到 Python 3。請到 https://www.python.org/downloads/ 安裝，裝好再雙擊一次這個檔案。"
    read -r -p "按 Enter 關閉"; exit 1
  fi
  echo "第一次使用，正在準備環境，約需一兩分鐘……"
  python3 -m venv .venv || { read -r -p "建立環境失敗，按 Enter 關閉"; exit 1; }
fi
if ! "$PY" -c "import yaml, PIL, edge_tts, openai, googleapiclient, google_auth_oauthlib" >/dev/null 2>&1; then
  echo "正在安裝需要的套件……"
  "$PY" -m pip install -q -r requirements.txt || { read -r -p "安裝失敗，請把上面的訊息截圖求助。按 Enter 關閉"; exit 1; }
fi
"$PY" -m pipeline.web
