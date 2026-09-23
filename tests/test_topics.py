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
