import argparse
import json
import os
import time
from pathlib import Path

import yaml

from . import factguard, render, script, topics, tts

SHORTS_MAX_SECONDS = 180  # YouTube Shorts 上限 3 分鐘(直式或方形)


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description="一條指令產出一支影片")
    ap.add_argument("--niche", default="niche.yaml")
    ap.add_argument("--dry-run", action="store_true", help="假 LLM/假 TTS,不連任何外部服務")
    ap.add_argument("--upload", action="store_true", help="產完上傳 YouTube(private)")
    ap.add_argument("--out", default="output")
    ap.add_argument("--topic", help="直接指定題目,跳過 LLM 選題")
    ap.add_argument("--shorts", action="store_true", help="產直式短片(1080x1920,約 50 秒)")
    a = ap.parse_args(argv)
    if a.dry_run and a.upload:
        ap.error("--dry-run 不能搭 --upload")
    if a.topic is not None and not a.topic.strip():
        ap.error("--topic 不能是空字串")
    load_env()

    niche_path = Path(a.niche)
    if a.dry_run and not niche_path.exists():
        niche_path = Path("niche.example.yaml")
    niche = yaml.safe_load(niche_path.read_text(encoding="utf-8"))
    for i, f in enumerate(niche.get("facts") or []):
        if not isinstance(f, dict) or "subject" not in f or "value" not in f:
            raise SystemExit("%s 的 facts 第 %d 筆缺少 subject 或 value" % (niche_path, i + 1))
    if a.dry_run:
        from .fakes import fake_llm as llm, fake_speak as speak
    else:
        from .llm import make_llm
        llm = make_llm()
        speak = tts.edge_speak(os.environ.get("TTS_VOICE") or "zh-TW-HsiaoChenNeural")

    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)
    used_file = out_root / "topics_used.json"
    used = [] if a.dry_run or not used_file.exists() else json.loads(used_file.read_text(encoding="utf-8"))
    performance_file = out_root / "performance.json"
    performance = None
    if not a.dry_run and performance_file.exists():
        performance = json.loads(performance_file.read_text(encoding="utf-8"))

    topic = a.topic.strip() if a.topic else topics.pick_topic(niche, used, llm, performance=performance)
    job = out_root / time.strftime("%Y%m%d-%H%M%S")
    job.mkdir()
    s = script.write_script(topic, niche, llm, shorts=a.shorts)
    if a.shorts and "#shorts" not in s["title"].lower():
        s["title"] = s["title"][:100 - len(" #Shorts")] + " #Shorts"
    (job / "script.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    problems = factguard.check(s, niche.get("facts") or [])
    if problems:
        (job / "factguard.txt").write_text("\n".join(problems), encoding="utf-8")
        raise SystemExit("事實閘門擋下 %d 處,見 %s" % (len(problems), job / "factguard.txt"))
    size = render.SHORTS_SIZE if a.shorts else (render.W, render.H)
    video = render.render(s["segments"], tts.synth(s["segments"], job, speak), job, size)
    if a.shorts and render.duration(video) > SHORTS_MAX_SECONDS:
        # 超過上限 YouTube 會當成一般影片,不會進 Shorts
        raise SystemExit("短片 %.0f 秒,超過 %d 秒上限:%s" % (render.duration(video), SHORTS_MAX_SECONDS, video))
    if not a.dry_run:
        tmp = used_file.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(used + [topic], ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, used_file)  # 寫到一半中斷不會留下半截檔、把去重紀錄整份弄丟
    print("影片:%s" % video)
    if a.upload:
        from .upload import finish, upload
        client_secrets = os.environ.get("YT_CLIENT_SECRETS") or "client_secrets.json"
        token_path = os.environ.get("YT_TOKEN") or "token.json"
        vid = upload(video, s["title"], s["description"], client_secrets, token_path)
        # 先落紀錄再收尾:縮圖/播放清單失敗時,已上傳的片不會失去紀錄
        published_file = out_root / "published.json"
        published = json.loads(published_file.read_text(encoding="utf-8")) if published_file.exists() else []
        published.append({"video_id": vid, "topic": topic, "title": s["title"],
                           "published": time.strftime("%Y-%m-%d"),
                           "format": "shorts" if a.shorts else "long"})
        tmp = published_file.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(published, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, published_file)
        print("已上傳(private):https://youtu.be/%s" % vid)
        finish(vid, client_secrets, token_path,
               thumbnail=None if a.shorts else job / "card00.png",  # 短片不設自訂縮圖
               playlist_id=niche.get("playlist_id") or None)


if __name__ == "__main__":
    main()
