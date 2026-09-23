import datetime
import json

from pipeline.stats import _window, main, rank

START = datetime.date(2026, 9, 1)
END = datetime.date(2026, 9, 10)

# 三支片的 views / 累計 minutes / minutes_per_day 排名刻意兩兩不同,也都不等於輸入順序,
# 這樣「拿掉排序」「改依 views 排序」「改依累計 minutes 排序」三種突變都會讓下面的
# test_ranked_by_minutes_per_day_desc 失敗。
PUBLISHED = [
    {"video_id": "a", "topic": "topicA", "title": "titleA", "published": "2026-09-01"},  # live 10 天
    {"video_id": "b", "topic": "topicB", "title": "titleB", "published": "2026-09-01"},  # live 10 天
    {"video_id": "c", "topic": "topicC", "title": "titleC", "published": "2026-09-06"},  # live 5 天
    {"video_id": "d", "topic": "topicD", "title": "titleD", "published": "2026-09-11"},  # 太新,排除
]

ROWS = {
    "a": {"minutes": 100.0, "views": 10},   # per-day 10,累計第1,views 第3
    "b": {"minutes": 40.0, "views": 1000},  # per-day 4, 累計第3,views 第1
    "c": {"minutes": 60.0, "views": 50},    # per-day 12,累計第2,views 第2
    # "d" 沒資料,但反正被排除,不會影響其他測試
}


def test_excludes_published_after_end_date():
    result = rank(PUBLISHED, ROWS, START, END)
    assert "d" not in [r["video_id"] for r in result]


def test_missing_data_recorded_as_zero():
    published = PUBLISHED + [{"video_id": "e", "topic": "t", "title": "t", "published": "2026-09-01"}]
    result = rank(published, ROWS, START, END)
    e = next(r for r in result if r["video_id"] == "e")
    assert e["minutes"] == 0 and e["views"] == 0 and e["minutes_per_day"] == 0


def test_ranked_by_minutes_per_day_desc():
    # 正確排序:c(12) > a(10) > b(4)。
    # 若拿掉排序 -> 維持輸入順序 [a, b, c];若依 views -> [b, c, a];
    # 若依累計 minutes -> [a, c, b]。三種都跟正確答案不同。
    result = rank(PUBLISHED, ROWS, START, END)
    assert [r["video_id"] for r in result] == ["c", "a", "b"]
    assert [round(r["minutes_per_day"], 4) for r in result] == [12.0, 10.0, 4.0]


def test_published_on_end_date_is_included_and_counts_as_one_day():
    # endDate 包含當天:published == end_date 要保留,且只算 1 天。
    published = [{"video_id": "x", "topic": "t", "title": "t", "published": END.isoformat()}]
    rows = {"x": {"minutes": 5.0, "views": 5}}
    result = rank(published, rows, START, END)
    assert [r["video_id"] for r in result] == ["x"]
    assert result[0]["minutes_per_day"] == 5.0


def test_published_before_start_date_clamped_to_start():
    # live_days 用 max(start_date, published),不能讓 window 之外的天數拉低平均。
    published = [{"video_id": "y", "topic": "t", "title": "t", "published": "2026-01-01"}]
    rows = {"y": {"minutes": 30.0, "views": 3}}
    result = rank(published, rows, START, END)
    # (END - START).days + 1 == 10
    assert result[0]["minutes_per_day"] == 3.0


def test_window_is_exactly_n_days():
    # --days 28 的窗口要剛好是 28 天(含 start 和 end 兩端),不是 29 天
    start, end = _window(28, datetime.date(2026, 9, 23))
    assert (end - start).days + 1 == 28
    # Analytics 延遲 3 天:end 要往前扣 3 天,今天的數字不可信
    assert end == datetime.date(2026, 9, 20)


def test_main_only_ranks_queried_batch(tmp_path, monkeypatch):
    # 只查最近 200 支,performance.json 也只該有這 200 支的排名
    published = [{"video_id": "v%d" % i, "topic": "t%d" % i, "title": "t",
                  "published": "2026-01-01"} for i in range(205)]
    (tmp_path / "published.json").write_text(json.dumps(published), encoding="utf-8")
    monkeypatch.setattr("pipeline.stats._fetch_rows", lambda ids, s, e: {})
    main(["--out", str(tmp_path), "--days", "28"])
    perf = json.loads((tmp_path / "performance.json").read_text(encoding="utf-8"))
    assert len(perf) == 200
    # S5:要的是最新 200 支(published.json 尾端),不是最舊 200 支
    assert {r["video_id"] for r in perf} == {"v%d" % i for i in range(5, 205)}


def test_main_reads_dotenv_like_run(tmp_path, monkeypatch):
    """YT_TOKEN 設在 .env 時,stats 要跟 run 用同一份設定,不能悄悄退回 token.json。"""
    import pytest
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YT_TOKEN", raising=False)
    (tmp_path / ".env").write_text("YT_TOKEN=my_token.json\n", encoding="utf-8")
    (tmp_path / "published.json").write_text(json.dumps(
        [{"video_id": "a", "topic": "t", "title": "t", "published": "2026-01-01"}]), encoding="utf-8")
    seen = []

    def fake_creds(client_secrets, token_path):
        seen.append(token_path)
        raise RuntimeError("stop")

    monkeypatch.setattr("pipeline.upload.get_credentials", fake_creds)
    with pytest.raises(RuntimeError):
        main(["--out", str(tmp_path)])
    assert seen == ["my_token.json"]


def test_days_must_be_positive(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        main(["--out", str(tmp_path), "--days", "0"])
