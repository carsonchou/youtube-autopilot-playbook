import asyncio
import os
from pathlib import Path


def edge_speak(voice):
    import edge_tts

    def speak(text, path):
        asyncio.run(edge_tts.Communicate(text, voice).save(str(path)))
    return speak


def synth(segments, out_dir, speak):
    """逐段配音。先寫 .tmp.mp3 再 os.replace —— 中途失敗不會留下看起來完整的半截檔。"""
    paths = []
    for i, seg in enumerate(segments):
        final = Path(out_dir) / ("seg%02d.mp3" % i)
        tmp = final.with_suffix(".tmp.mp3")
        speak(seg["text"], tmp)
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise RuntimeError("第 %d 段配音是空檔" % i)
        os.replace(tmp, final)
        paths.append(final)
    # 只擋「例外」與「空檔」;不報錯卻截短的配音擋不到,要擋就用 ffprobe 比時長與字數
    return paths
