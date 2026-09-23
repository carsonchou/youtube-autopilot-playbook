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
