import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msjh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size=64):
    path = os.environ.get("FONT_FILE") or next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    if not path:
        raise RuntimeError("找不到中文字型,請在 .env 設 FONT_FILE=字型檔路徑")
    return ImageFont.truetype(path, size)


def wrap(text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if cur and font.getlength(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + [cur] if cur else lines


def make_card(text, path, font):
    img = Image.new("RGB", (W, H), (18, 18, 24))
    draw = ImageDraw.Draw(img)
    lines = wrap(text, font, W - 240)
    lh = int(font.size * 1.5)
    y = (H - lh * len(lines)) // 2
    for line in lines:
        draw.text(((W - font.getlength(line)) // 2, y), line, font=font, fill=(235, 235, 235))
        y += lh
    img.save(path)


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + [str(a) for a in args], check=True)


def render(segments, audio_paths, out_dir):
    out_dir = Path(out_dir)
    font = load_font()
    parts = []
    for i, (seg, audio) in enumerate(zip(segments, audio_paths)):
        card, part = out_dir / ("card%02d.png" % i), out_dir / ("part%02d.mp4" % i)
        make_card(seg["text"], card, font)
        _ff("-loop", "1", "-i", card, "-i", audio, "-c:v", "libx264", "-tune", "stillimage",
            "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-shortest", part)
        parts.append(part)
    lst = out_dir / "concat.txt"
    lst.write_text("".join("file '%s'\n" % p.name for p in parts), encoding="utf-8")
    final, tmp = out_dir / "video.mp4", out_dir / "video.tmp.mp4"
    _ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", tmp)
    os.replace(tmp, final)
    return final
