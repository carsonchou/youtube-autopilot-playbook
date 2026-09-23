import subprocess
import pytest
from pipeline.fakes import fake_speak
from pipeline.render import render, wrap, load_font
from pipeline.tts import synth

SEGS = [{"text": "第一段"}, {"text": "第二段比較長" * 20}]

def test_synth_writes_final_files_only(tmp_path):
    paths = synth(SEGS, tmp_path, fake_speak)
    assert [p.name for p in paths] == ["seg00.mp3", "seg01.mp3"]
    assert all(p.stat().st_size > 0 for p in paths)
    assert not list(tmp_path.glob("*.tmp.*"))

def test_synth_failure_leaves_no_final(tmp_path):
    def boom(text, path):
        open(path, "wb").write(b"half")
        raise RuntimeError("TTS 中途斷線")
    with pytest.raises(RuntimeError):
        synth(SEGS, tmp_path, boom)
    assert not (tmp_path / "seg00.mp3").exists()

def test_wrap_respects_width():
    font = load_font(64)
    assert all(font.getlength(l) <= 800 for l in wrap("很長的句子" * 30, font, 800))

def test_render_produces_playable_mp4(tmp_path):
    video = render(SEGS, synth(SEGS, tmp_path, fake_speak), tmp_path)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True)
    assert float(dur.stdout) > 1.5
