# youtube-autopilot-playbook

把一個題材變成每天能穩定產出的 YouTube 長片頻道 —— 方法手冊 + 可直接跑的精簡產線。

## 出處

這是 [量化阿森](https://www.youtube.com/@CarsonQuant) 頻道實際在用的做法,抽成通用版。覺得有用,歡迎來頻道看看成品。

## 它做什麼

選題 → 腳本 → 事實閘門 → 配音 → 字卡渲染 → 上傳(private)

## 5 分鐘上手

1. `pip install -r requirements.txt`(另需安裝 [ffmpeg](https://ffmpeg.org/))
2. 先跑一次假資料,確認環境沒問題:`python -m pipeline.run --dry-run`
3. 複製 `.env.example` → `.env`、`niche.example.yaml` → `niche.yaml`,填入你自己的設定
4. 正式產一支:`python -m pipeline.run`
5. 要直接上傳到 YouTube 就加 `--upload`(需先到 Google Cloud Console 建立 OAuth 桌面應用程式用戶端,下載成 `client_secrets.json` 放在專案根目錄)

## 合規警告

這只是工具。YouTube 會把「大量範本化、缺少人的價值」的內容排除在營利之外;請加入你自己的觀點、審稿與原創分析,發布前一定要人工看過。詳見 `PLAYBOOK.md` 第 8 章。

## 延伸方向(沒做)

- 縮圖生成
- 排程 / cron 自動化
- 多頻道切換
- Analytics 數據回饋迴圈
- 字幕軌

## 授權

MIT,詳見 `LICENSE`。
