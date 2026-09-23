"""讀 output/published.json,拿 YouTube Analytics 排出每支片的表現,寫成 output/performance.json。
執行方式:python -m pipeline.stats [--out output] [--days 28]
"""
import argparse
import datetime
import json
import os
from pathlib import Path

ANALYTICS_LAG_DAYS = 3  # Analytics 有幾天延遲,今天的數字不可信


def rank(published, rows, start_date, end_date):
    """純函式。published:[{video_id, topic, title, published(ISO日期字串)}, ...]
    rows:{video_id: {"minutes":..., "views":...}}。
    published 晚於 end_date 的片還沒有數據,直接排除(end_date 當天算在窗口內,保留);
    其餘沒在 rows 裡的記 0。依「窗口內平均每天觀看分鐘」(minutes_per_day)由大到小排序,
    不是累計 minutes、也不是 views —— 片齡不同,累計數字對新片不公平。"""
    result = []
    for p in published:
        pub_date = datetime.date.fromisoformat(p["published"])
        if pub_date > end_date:
            continue
        row = rows.get(p["video_id"], {})
        minutes = row.get("minutes", 0)
        live_days = max((end_date - max(start_date, pub_date)).days + 1, 1)
        result.append({
            "video_id": p["video_id"],
            "topic": p["topic"],
            "title": p["title"],
            "minutes": minutes,
            "views": row.get("views", 0),
            "minutes_per_day": minutes / live_days,
        })
    result.sort(key=lambda r: r["minutes_per_day"], reverse=True)
    return result


def _window(days, today):
    """回傳 (start_date, end_date):end_date 扣掉 Analytics 延遲,start_date 讓窗口剛好是
    days 天(含頭尾兩端,所以是 -(days-1)不是 -days)。"""
    end_date = today - datetime.timedelta(days=ANALYTICS_LAG_DAYS)
    start_date = end_date - datetime.timedelta(days=days - 1)
    return start_date, end_date


def _fetch_rows(video_ids, start_date, end_date):
    from googleapiclient.discovery import build

    from .upload import get_credentials  # 延遲載入:避免只是 import pipeline.stats 就拉進會連外的模組
    creds = get_credentials(os.environ.get("YT_CLIENT_SECRETS") or "client_secrets.json",
                             os.environ.get("YT_TOKEN") or "token.json")
    yt = build("youtubeAnalytics", "v2", credentials=creds)
    resp = yt.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics="estimatedMinutesWatched,views",
        dimensions="video",
        filters="video==" + ",".join(video_ids),
        sort="-estimatedMinutesWatched",  # video 維度的報表要靠 sort+maxResults 才拿得到完整資料
        maxResults=200,
    ).execute()
    rows = {}
    for video_id, minutes, views in resp.get("rows", []):
        rows[video_id] = {"minutes": minutes, "views": views}
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="依觀看分鐘排出過去題目的表現")
    ap.add_argument("--out", default="output")
    ap.add_argument("--days", type=int, default=28)
    a = ap.parse_args(argv)
    if a.days < 1:
        ap.error("--days 至少要 1")

    from .run import load_env
    load_env()  # 跟 pipeline.run 用同一份 .env,否則 YT_TOKEN 設在 .env 會被忽略、查到別的帳號

    out_root = Path(a.out)
    published_file = out_root / "published.json"
    published = json.loads(published_file.read_text(encoding="utf-8")) if published_file.exists() else []

    start_date, end_date = _window(a.days, datetime.date.today())

    # 只查最近 200 支,就只對這一批排名 —— 對查詢範圍外的舊片排名,它們會被誤記成 0
    queried = published[-200:]
    video_ids = [p["video_id"] for p in queried]
    rows = _fetch_rows(video_ids, start_date, end_date) if video_ids else {}

    result = rank(queried, rows, start_date, end_date)

    perf_file = out_root / "performance.json"
    tmp = perf_file.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, perf_file)
    print("已寫入 %s(%d 支)" % (perf_file, len(result)))


if __name__ == "__main__":
    main()
