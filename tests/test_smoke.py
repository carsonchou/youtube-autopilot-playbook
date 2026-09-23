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


def test_thumbnail_is_first_card(tmp_path, monkeypatch):
    from pipeline.fakes import fake_llm, fake_speak

    got = {}
    monkeypatch.setattr("pipeline.llm.make_llm", lambda: fake_llm)
    monkeypatch.setattr("pipeline.tts.edge_speak", lambda voice: fake_speak)
    monkeypatch.setattr("pipeline.upload.upload", lambda *a, **k: "FAKEID")
    monkeypatch.setattr("pipeline.upload.finish", lambda *a, **k: got.update(k))

    main(["--niche", str(ROOT / "niche.example.yaml"), "--upload", "--out", str(tmp_path)])

    assert got["thumbnail"].name == "card00.png" and got["thumbnail"].exists()


def test_fact_missing_subject_is_rejected_with_message(tmp_path):
    niche = tmp_path / "niche.yaml"
    niche.write_text((ROOT / "niche.example.yaml").read_text(encoding="utf-8")
                     .replace('subject: "範例主體"', 'name: "範例主體"'), encoding="utf-8")
    with pytest.raises(SystemExit, match="第 1 筆缺少 subject"):
        main(["--dry-run", "--niche", str(niche), "--out", str(tmp_path)])


def _fake_network(monkeypatch, uploads):
    from pipeline.fakes import fake_llm, fake_speak

    monkeypatch.setattr("pipeline.llm.make_llm", lambda: fake_llm)
    monkeypatch.setattr("pipeline.tts.edge_speak", lambda voice: fake_speak)
    monkeypatch.setattr("pipeline.upload.upload",
                        lambda video, title, *a, **k: uploads.append(title) or "FAKEID")
    monkeypatch.setattr("pipeline.upload.finish", lambda *a, **k: uploads.append(k))


def test_topic_flag_skips_llm_topic_pick(tmp_path, monkeypatch):
    import pipeline.fakes

    prompts = []
    real = pipeline.fakes.fake_llm
    monkeypatch.setattr(pipeline.fakes, "fake_llm", lambda p: prompts.append(p) or real(p))
    main(["--dry-run", "--topic", "定存跟ETF哪個適合新手", "--out", str(tmp_path)])
    assert len(prompts) == 1  # 只剩寫腳本那一次,沒有選題
    assert "定存跟ETF哪個適合新手" in prompts[0]


def test_empty_topic_refused(tmp_path):
    with pytest.raises(SystemExit):
        main(["--dry-run", "--topic", "  ", "--out", str(tmp_path)])


def test_shorts_is_vertical_and_prompts_for_short_script(tmp_path, monkeypatch):
    import subprocess
    import pipeline.fakes

    prompts = []
    real = pipeline.fakes.fake_llm
    monkeypatch.setattr(pipeline.fakes, "fake_llm", lambda p: prompts.append(p) or real(p))
    main(["--dry-run", "--shorts", "--out", str(tmp_path)])
    video = next(tmp_path.glob("*/video.mp4"))
    wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height", "-of", "csv=p=0", str(video)],
                        capture_output=True, text=True, check=True).stdout.strip()
    assert wh == "1080,1920"
    from pipeline.render import duration
    assert 2 < duration(video) < 5  # 假配音 1 秒 x 3 段
    assert "Shorts" in prompts[-1] and "分鐘的長片" not in prompts[-1]


def test_long_video_stays_horizontal_prompt(tmp_path, monkeypatch):
    import pipeline.fakes

    prompts = []
    real = pipeline.fakes.fake_llm
    monkeypatch.setattr(pipeline.fakes, "fake_llm", lambda p: prompts.append(p) or real(p))
    main(["--dry-run", "--out", str(tmp_path)])
    assert "分鐘的長片" in prompts[-1] and "Shorts" not in prompts[-1]


def test_shorts_upload_adds_hashtag_and_skips_thumbnail(tmp_path, monkeypatch):
    uploads = []
    _fake_network(monkeypatch, uploads)
    main(["--niche", str(ROOT / "niche.example.yaml"), "--shorts", "--upload", "--out", str(tmp_path)])
    title, finish_kwargs = uploads
    assert title.endswith(" #Shorts") and len(title) <= 100
    assert finish_kwargs["thumbnail"] is None
    published = json.loads((tmp_path / "published.json").read_text(encoding="utf-8"))
    assert published[0]["format"] == "shorts"


def test_shorts_title_truncated_to_fit_hashtag(tmp_path, monkeypatch):
    import pipeline.fakes

    real = pipeline.fakes.fake_llm

    def long_title_llm(p):
        s = json.loads(real(p)) if "JSON" in p else None
        if s is None:
            return real(p)
        s["title"] = "長" * 100
        return json.dumps(s, ensure_ascii=False)
    uploads = []
    _fake_network(monkeypatch, uploads)
    monkeypatch.setattr("pipeline.llm.make_llm", lambda: long_title_llm)
    main(["--niche", str(ROOT / "niche.example.yaml"), "--shorts", "--upload", "--out", str(tmp_path)])
    assert len(uploads[0]) == 100 and uploads[0].endswith(" #Shorts")


def test_too_long_shorts_refused_before_upload(tmp_path, monkeypatch):
    uploads = []
    _fake_network(monkeypatch, uploads)
    monkeypatch.setattr("pipeline.render.duration", lambda path: 181.0)
    with pytest.raises(SystemExit, match="超過 180 秒"):
        main(["--niche", str(ROOT / "niche.example.yaml"), "--shorts", "--upload", "--out", str(tmp_path)])
    assert uploads == []


def _title_llm(title):
    import pipeline.fakes
    real = pipeline.fakes.fake_llm

    def llm(p):
        if "JSON" not in p:
            return real(p)
        s = json.loads(real(p))
        s["title"] = title
        return json.dumps(s, ensure_ascii=False)
    return llm


@pytest.mark.parametrize("title, expected", [
    ("貓咪 #shorts", "貓咪 #shorts"),                    # 小寫也算已經有
    ("貓咪 ＃Shorts", "貓咪 ＃Shorts"),                  # 全形 # 不重複加
    ("貓咪 #shortsvideo", "貓咪 #shortsvideo #Shorts"),  # 別的 hashtag 不算
    ("長" * 91 + " " + "尾" * 8, "長" * 91 + " #Shorts"),  # 截斷處的空白不留成兩格
])
def test_shorts_hashtag_cases(tmp_path, monkeypatch, title, expected):
    uploads = []
    _fake_network(monkeypatch, uploads)
    monkeypatch.setattr("pipeline.llm.make_llm", lambda: _title_llm(title))
    main(["--niche", str(ROOT / "niche.example.yaml"), "--shorts", "--upload", "--out", str(tmp_path)])
    assert uploads[0] == expected


def test_too_long_shorts_does_not_burn_topic(tmp_path, monkeypatch):
    _fake_network(monkeypatch, [])
    monkeypatch.setattr("pipeline.render.duration", lambda path: 181.0)
    with pytest.raises(SystemExit):
        main(["--niche", str(ROOT / "niche.example.yaml"), "--shorts", "--upload", "--out", str(tmp_path)])
    assert not (tmp_path / "topics_used.json").exists()


def test_long_upload_records_format(tmp_path, monkeypatch):
    _fake_network(monkeypatch, [])
    main(["--niche", str(ROOT / "niche.example.yaml"), "--upload", "--out", str(tmp_path)])
    assert json.loads((tmp_path / "published.json").read_text(encoding="utf-8"))[0]["format"] == "long"
