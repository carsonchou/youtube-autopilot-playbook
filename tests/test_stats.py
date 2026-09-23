import datetime

from pipeline.stats import rank

END = datetime.date(2026, 9, 1)

PUBLISHED = [
    {"video_id": "a", "topic": "topicA", "title": "titleA", "published": "2026-08-01"},
    {"video_id": "b", "topic": "topicB", "title": "titleB", "published": "2026-08-15"},
    {"video_id": "c", "topic": "topicC", "title": "titleC", "published": "2026-09-05"},  # 太新
]

ROWS = {
    "a": {"minutes": 10.0, "views": 100},
    # "b" 沒有資料 -> 記 0
}


def test_excludes_too_new():
    result = rank(PUBLISHED, ROWS, END)
    assert "c" not in [r["video_id"] for r in result]


def test_missing_data_recorded_as_zero():
    result = rank(PUBLISHED, ROWS, END)
    b = next(r for r in result if r["video_id"] == "b")
    assert b["minutes"] == 0 and b["views"] == 0


def test_sorted_by_minutes_desc():
    result = rank(PUBLISHED, ROWS, END)
    assert [r["video_id"] for r in result] == ["a", "b"]
