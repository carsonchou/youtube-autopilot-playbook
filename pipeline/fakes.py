"""--dry-run 與測試用的假 LLM / 假 TTS,不連任何外部服務。"""
import json
import subprocess


def fake_llm(prompt):
    if "JSON" in prompt:
        return json.dumps({
            "title": "範例:新手最常忽略的三件事",
            "description": "這是 dry-run 產生的範例影片。",
            "segments": [
                {"text": "你是不是也以為入門很簡單,結果一開始就踩坑?"},
                {"text": "第一件事是先搞懂規則。這段的結論是:不懂規則就別急著行動。"},
                {"text": "記住一句話:先搞懂再行動。訂閱頻道,下一集告訴你第二件事。"},
            ],
        }, ensure_ascii=False)
    return "範例題目:新手最常忽略的三件事"


def fake_speak(text, path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=24000:cl=mono", "-t", "1",
                    "-c:a", "libmp3lame", str(path)], check=True)
