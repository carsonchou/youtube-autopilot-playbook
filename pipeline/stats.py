"""讀 output/published.json,拿 YouTube Analytics 排出每支片的表現,寫成 output/performance.json。
執行方式:python -m pipeline.stats [--out output] [--days 28]
"""
import argparse
import datetime
import json
import os
from pathlib import Path

ANALYTICS_LAG_DAYS = 3  # Analytics 有幾天延遲,今天的數字不可信


def rank(published, rows, end_date):
    """純函式。published:[{video_id, topic, title, published(ISO日期字串)}, ...]
    rows:{video_id: {"minutes":..., "views":...}}。
    published 晚於 end_date 的片還沒有數據,直接排除;其餘沒在 rows 裡的記 0。
    依 minutes 由大到小排序。"""
    result = []
    for p in published:
        if datetime.date.fromisoformat(p["published"]) > end_date:
            continue
        row = rows.get(p["video_id"], {})
        result.append({
            "video_id": p["video_id"],
            "topic": p["topic"],
            "title": p["title"],
            "minutes": row.get("minutes", 0),
            "views": row.get("views", 0),
        })
    result.sort(key=lambda r: r["minutes"], reverse=True)
    return result


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

    out_root = Path(a.out)
    published_file = out_root / "published.json"
    published = json.loads(published_file.read_text(encoding="utf-8")) if published_file.exists() else []

    end_date = datetime.date.today() - datetime.timedelta(days=ANALYTICS_LAG_DAYS)
    start_date = end_date - datetime.timedelta(days=a.days)

    video_ids = [p["video_id"] for p in published[-200:]]
    rows = _fetch_rows(video_ids, start_date, end_date) if video_ids else {}

    result = rank(published, rows, end_date)

    perf_file = out_root / "performance.json"
    tmp = perf_file.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, perf_file)
    print("已寫入 %s(%d 支)" % (perf_file, len(result)))


if __name__ == "__main__":
    main()
