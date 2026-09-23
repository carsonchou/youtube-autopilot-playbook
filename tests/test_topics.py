import pytest
from pipeline.topics import pick_topic

NICHE = {"channel_name": "頻道", "audience": "新手", "seed_topics": ["入門"]}

def test_returns_first_line_stripped():
    assert pick_topic(NICHE, [], lambda p: "「新手要先懂什麼」\n多的行") == "新手要先懂什麼"

def test_duplicate_rejected():
    with pytest.raises(ValueError):
        pick_topic(NICHE, ["重複題"], lambda p: "重複題")

def test_empty_rejected():
    with pytest.raises(ValueError):
        pick_topic(NICHE, [], lambda p: "  ")

def test_performance_added_to_prompt():
    performance = [
        {"video_id": str(i), "topic": "topic%d" % i, "title": "t", "minutes": 10 - i, "views": 1}
        for i in range(7)
    ]
    seen = []
    pick_topic(NICHE, [], lambda p: seen.append(p) or "新題", performance=performance)
    assert "topic0" in seen[0] and "topic4" in seen[0]  # 前 5 名
    assert "topic5" in seen[0] and "topic6" in seen[0]  # 表現最差(performance[5:][-5:])

def test_no_performance_omits_block():
    seen = []
    pick_topic(NICHE, [], lambda p: seen.append(p) or "新題", performance=None)
    assert "表現最好" not in seen[0]
