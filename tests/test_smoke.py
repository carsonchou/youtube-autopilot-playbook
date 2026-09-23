import json
import sys
from pathlib import Path
import pytest
from pipeline.run import main

ROOT = Path(__file__).resolve().parent.parent

def test_dry_run_makes_video_without_network(tmp_path):
    main(["--dry-run", "--niche", str(ROOT / "niche.example.yaml"), "--out", str(tmp_path)])
    videos = list(tmp_path.glob("*/video.mp4"))
    assert len(videos) == 1 and videos[0].stat().st_size > 0
    # 禁令要會產生輸出:dry-run 不得載入會連外的模組
    assert "pipeline.llm" not in sys.modules
    assert "pipeline.upload" not in sys.modules

def test_dry_run_with_upload_refused(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dry-run", "--upload", "--out", str(tmp_path)])

def test_dry_run_really_does_not_touch_network(tmp_path, monkeypatch):
    import socket

    def boom(*a, **k):
        raise AssertionError("dry-run 不該連外")
    monkeypatch.setattr(socket.socket, "connect", boom)
    main(["--dry-run", "--niche", str(ROOT / "niche.example.yaml"), "--out", str(tmp_path)])
    videos = list(tmp_path.glob("*/video.mp4"))
    assert len(videos) == 1 and videos[0].stat().st_size > 0

# 這支測試會 import pipeline.llm / pipeline.upload,刻意放在檔案最後,
# 免得污染前面斷言「dry-run 不拉進這些模組」的測試。
def test_published_json_written_before_finish_runs(tmp_path, monkeypatch):
    """--upload 收尾(縮圖/播放清單)失敗,不能讓已經上傳的片遺失紀錄:
    published.json 要在呼叫 finish() 之前就寫入。用假 LLM/TTS 繞開真實網路。"""
    from pipeline.fakes import fake_llm, fake_speak

    monkeypatch.setattr("pipeline.llm.make_llm", lambda: fake_llm)
    monkeypatch.setattr("pipeline.tts.edge_speak", lambda voice: fake_speak)
    monkeypatch.setattr("pipeline.upload.upload", lambda *a, **k: "FAKEID")

    def boom_finish(*a, **k):
        raise RuntimeError("finish 中途失敗(例如縮圖上傳炸掉)")
    monkeypatch.setattr("pipeline.upload.finish", boom_finish)

    with pytest.raises(RuntimeError):
        main(["--niche", str(ROOT / "niche.example.yaml"), "--upload", "--out", str(tmp_path)])

    published = json.loads((tmp_path / "published.json").read_text(encoding="utf-8"))
    assert published and published[0]["video_id"] == "FAKEID"


def test_run_does_not_request_public_privacy(tmp_path, monkeypatch):
    """run.py 呼叫 upload() 時不該自己傳 privacy="public",要靠 upload() 的預設值(private)。"""
    from pipeline.fakes import fake_llm, fake_speak

    calls = []

    def fake_upload(video, title, description, client_secrets, token_path, privacy="private"):
        calls.append({"privacy": privacy})  # 位置參數或關鍵字傳進來都抓得到
        return "FAKEID"

    monkeypatch.setattr("pipeline.llm.make_llm", lambda: fake_llm)
    monkeypatch.setattr("pipeline.tts.edge_speak", lambda voice: fake_speak)
    monkeypatch.setattr("pipeline.upload.upload", fake_upload)
    monkeypatch.setattr("pipeline.upload.finish", lambda *a, **k: None)

    main(["--niche", str(ROOT / "niche.example.yaml"), "--upload", "--out", str(tmp_path)])

    assert calls and calls[0].get("privacy", "private") == "private"
