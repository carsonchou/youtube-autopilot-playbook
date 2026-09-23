import argparse
import json
import os
import time
from pathlib import Path

import yaml

from . import factguard, render, script, topics, tts


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
    a = ap.parse_args(argv)
    if a.dry_run and a.upload:
        ap.error("--dry-run 不能搭 --upload")
    load_env()

    niche_path = Path(a.niche)
    if a.dry_run and not niche_path.exists():
        niche_path = Path("niche.example.yaml")
    niche = yaml.safe_load(niche_path.read_text(encoding="utf-8"))
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

    topic = topics.pick_topic(niche, used, llm, performance=performance)
    job = out_root / time.strftime("%Y%m%d-%H%M%S")
    job.mkdir()
    s = script.write_script(topic, niche, llm)
    (job / "script.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    problems = factguard.check(s, niche.get("facts") or [])
    if problems:
        (job / "factguard.txt").write_text("\n".join(problems), encoding="utf-8")
        raise SystemExit("事實閘門擋下 %d 處,見 %s" % (len(problems), job / "factguard.txt"))
    video = render.render(s["segments"], tts.synth(s["segments"], job, speak), job)
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
                           "published": time.strftime("%Y-%m-%d")})
        tmp = published_file.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(published, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, published_file)
        print("已上傳(private):https://youtu.be/%s" % vid)
        finish(vid, client_secrets, token_path,
               thumbnail=job / "card00.png",
               playlist_id=niche.get("playlist_id") or None)


if __name__ == "__main__":
    main()
