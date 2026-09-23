import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SHORTS_SIZE = (1080, 1920)  # 直式
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


def make_card(text, path, font, size=(W, H)):
    w, h = size
    img = Image.new("RGB", size, (18, 18, 24))
    draw = ImageDraw.Draw(img)
    lines = wrap(text, font, w - 240)
    lh = int(font.size * 1.5)
    y = (h - lh * len(lines)) // 2
    for line in lines:
        draw.text(((w - font.getlength(line)) // 2, y), line, font=font, fill=(235, 235, 235))
        y += lh
    img.save(path)


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + [str(a) for a in args], check=True)


def render(segments, audio_paths, out_dir, size=(W, H)):
    out_dir = Path(out_dir)
    font = load_font(80 if size[0] < size[1] else 64)  # 直式畫面小,字放大
    parts = []
    for i, (seg, audio) in enumerate(zip(segments, audio_paths)):
        card, part = out_dir / ("card%02d.png" % i), out_dir / ("part%02d.mp4" % i)
        make_card(seg["text"], card, font, size)
        _ff("-loop", "1", "-i", card, "-i", audio, "-c:v", "libx264", "-tune", "stillimage",
            "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-shortest", part)
        parts.append(part)
    lst = out_dir / "concat.txt"
    lst.write_text("".join("file '%s'\n" % p.name for p in parts), encoding="utf-8")
    final, tmp = out_dir / "video.mp4", out_dir / "video.tmp.mp4"
    _ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", tmp)
    os.replace(tmp, final)
    return final


def duration(path):
    """影片秒數(ffprobe)。"""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())
