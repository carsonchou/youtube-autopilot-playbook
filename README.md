# youtube-autopilot-playbook

把一個題材變成每天能穩定產出的 YouTube 長片頻道 —— 方法手冊 + 可直接跑的精簡產線。

## 出處

這是 [量化阿森](https://www.youtube.com/@CarsonQuant) 頻道實際在用的做法,抽成通用版。覺得有用,歡迎來頻道看看成品。

## 它做什麼

選題 → 腳本 → 事實閘門 → 配音 → 字卡渲染 → 上傳(private)

## 5 分鐘上手

1. `pip install -r requirements.txt`(另需安裝 [ffmpeg](https://ffmpeg.org/))
2. 先跑一次假資料:`python -m pipeline.run --dry-run`(只驗證 ffmpeg、字型和產線串接有沒有裝對;正式執行還需要 API key 和網路,這一步驗不到)
3. 複製 `.env.example` → `.env`、`niche.example.yaml` → `niche.yaml`,填入你自己的設定
4. 正式產一支:`python -m pipeline.run`
5. 要直接上傳到 YouTube 就加 `--upload`(需先到 Google Cloud Console 建立 OAuth 桌面應用程式用戶端,下載成 `client_secrets.json` 放在專案根目錄)
6. 上傳過一段時間後,可以跑 `python -m pipeline.stats` 抓 Analytics 數據,回饋給下一次選題(見下)

## 授權範圍

`--upload` 會走 OAuth 跟你要兩個權限:

- `youtube.force-ssl`:上傳影片、設縮圖、把片加進播放清單。
- `yt-analytics.readonly`:讀你自己頻道的 Analytics 數據(觀看分鐘、觀看次數),給 `pipeline.stats` 用。

**不會**要 Gmail 權限 —— 這條產線不需要寄信或讀信,不多要用不到的權限。

⚠️ `token.json` 拿到手等於拿到你頻道的管理權,可以刪片、改設定。它已經被 `.gitignore` 擋住,**絕對不要**分享或 commit 這個檔案。

要讓這兩個權限生效,記得先到 Google Cloud 專案啟用 **YouTube Data API v3** 和 **YouTube Analytics API**。

⚠️ YouTube 政策規定,2020-07-28 之後建立的 API 專案如果沒有通過稽核,用這個專案上傳的影片會被鎖成 private,想公開需要先申請 [YouTube API Services 稽核](https://support.google.com/youtube/contact/yt_api_form)。實際規則以 YouTube 官方最新說明為準。

⚠️ `output/published.json` 記的是**上傳日**,不是公開日。如果影片先以 private 上傳,過幾天才手動改成公開,中間那幾天會被算進 `pipeline.stats` 的每日平均分母,把該片的 `minutes_per_day` 拉低。

## Analytics 回饋選題

`python -m pipeline.stats [--out output] [--days 28]` 會讀 `output/published.json`,呼叫 YouTube Analytics API 抓每支片最近幾天的觀看分鐘,寫成 `output/performance.json`。下次 `pipeline.run` 選題時,如果這個檔案存在,會自動把「過去表現最好/最差的題目」放進選題 prompt 給 LLM 參考。這一步會連網,不要在 `--dry-run` 或不想連外時執行。

## 合規警告

這只是工具。YouTube 會把「大量範本化、缺少人的價值」的內容排除在營利之外;請加入你自己的觀點、審稿與原創分析,發布前一定要人工看過。詳見 `PLAYBOOK.md` 第 8 章。

## 延伸方向(沒做)

- 縮圖生成的自動化美術(目前縮圖是用第一張字卡)
- 排程 / cron 自動化
- 多頻道切換
- 字幕軌

## 授權

MIT,詳見 `LICENSE`。
