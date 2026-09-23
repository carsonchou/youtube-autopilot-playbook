import http.client
import json
import shutil
import threading
import time
from pathlib import Path

import pytest
import yaml

from pipeline.web import make_server

ROOT = Path(__file__).resolve().parent.parent
ENV = ".env"


@pytest.fixture
def srv(tmp_path):
    s = make_server(tmp_path, port=0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s
    s.shutdown()
    s.server_close()


def req(srv, method, path, body=None, token=True, host=None):
    port = srv.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or "127.0.0.1:%d" % port, "Content-Type": "application/json"}
    if token:
        headers["X-Token"] = srv.RequestHandlerClass.studio.token
    c.request(method, path, json.dumps(body) if body is not None else None, headers)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


NICHE = {"channel_name": "貓奴研究所", "theme": "新手養貓", "audience": "新手", "tone": "溫柔",
         "minutes": 5, "playlist_id": "", "seed_topics": ["餵食"],
         "facts": [{"subject": "貓", "value": "3 公斤", "source": ""}, {"subject": "", "value": ""}]}


def test_api_needs_token(srv):
    assert req(srv, "GET", "/api/state", token=False)[0] == 403
    assert req(srv, "POST", "/api/niche", NICHE, token=False)[0] == 403
    assert not (srv.RequestHandlerClass.studio.root / "niche.yaml").exists()


def test_foreign_host_rejected_even_with_token(srv):
    assert req(srv, "GET", "/api/state", host="evil.example:%d" % srv.server_address[1])[0] == 403
    assert req(srv, "GET", "/", host="evil.example")[0] == 403


def test_page_has_token_injected(srv):
    code, body = req(srv, "GET", "/", token=False)
    assert code == 200 and srv.RequestHandlerClass.studio.token.encode() in body


def test_state_never_returns_api_key(srv):
    root = srv.RequestHandlerClass.studio.root
    (root / ENV).write_text("OPENROUTER_API_KEY=sk-secret-xyz\nLLM_MODEL=a/b\n", encoding="utf-8")
    code, body = req(srv, "GET", "/api/state")
    assert code == 200 and b"sk-secret-xyz" not in body
    env = json.loads(body)["env"]
    assert env["OPENROUTER_API_KEY"] is True and env["LLM_MODEL"] == "a/b"


def test_env_save_keeps_other_lines_and_empty_means_unchanged(srv):
    root = srv.RequestHandlerClass.studio.root
    (root / ENV).write_text("# note\nOPENROUTER_API_KEY=old\nFONT_FILE=x.ttf\n", encoding="utf-8")
    assert req(srv, "POST", "/api/env", {"OPENROUTER_API_KEY": "", "LLM_MODEL": "m/n", "TTS_VOICE": "v"})[0] == 200
    text = (root / ENV).read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=old" in text and "FONT_FILE=x.ttf" in text and "# note" in text
    assert "LLM_MODEL=m/n" in text and "TTS_VOICE=v" in text


@pytest.mark.parametrize("sep", ["\n", "\r", "\x0b", "\x0c", "\x1c", "\x85", "\u2028", "\u2029"])
def test_env_value_with_line_break_refused(srv, sep):
    # splitlines() 會把這些都當換行切開,放行就能注入別的 key(例如把 YT_CLIENT_SECRETS 指到 root 外)
    root = srv.RequestHandlerClass.studio.root
    code, _ = req(srv, "POST", "/api/env", {"LLM_MODEL": "x" + sep + "YT_CLIENT_SECRETS=../pwned.json"})
    assert code == 400 and not (root / ENV).exists()


def test_files_need_token(srv):
    root = srv.RequestHandlerClass.studio.root
    (root / "output" / "20260101-000000").mkdir(parents=True)
    (root / "output" / "20260101-000000" / "video.mp4").write_bytes(b"x" * 10)
    assert req(srv, "GET", "/files/20260101-000000/video.mp4", token=False)[0] == 403
    assert req(srv, "GET", "/files/20260101-000000/video.mp4?t=" + srv.RequestHandlerClass.studio.token,
               token=False)[0] == 200


@pytest.mark.parametrize("length", ["-1", "abc", str((1 << 20) + 1)])
def test_bad_content_length_refused(srv, length):
    port = srv.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.putrequest("POST", "/api/niche", skip_host=True)
    c.putheader("Host", "127.0.0.1:%d" % port)
    c.putheader("X-Token", srv.RequestHandlerClass.studio.token)
    c.putheader("Content-Length", length)
    c.endheaders()
    assert c.getresponse().status == 413
    c.close()


def test_topic_starting_with_dash_passed_as_value(srv, monkeypatch):
    studio = srv.RequestHandlerClass.studio
    shutil.copy(ROOT / "niche.example.yaml", studio.root / "niche.yaml")
    import subprocess
    import sys
    cmds = []
    real = subprocess.Popen

    def fake_popen(cmd, **k):
        cmds.append(cmd)
        return real([sys.executable, "-c", ""], **k)  # 不真的產片
    monkeypatch.setattr("pipeline.web.subprocess.Popen", fake_popen)
    req(srv, "POST", "/api/run", {"mode": "dry", "topic": "-貓咪為什麼暴衝"})
    assert cmds and "--topic=-貓咪為什麼暴衝" in cmds[0]
    assert req(srv, "POST", "/api/run", {"mode": "dry", "topic": "貓\u2028咪"})[0] == 400


@pytest.mark.parametrize("topic", ["貓咪\u3000為什麼暴衝", "👨\u200d👩\u200d👧 一家人養貓", "貓\t咪"])
def test_topic_with_fullwidth_space_or_emoji_accepted(srv, monkeypatch, topic):
    # 中文輸入法常打出全形空白,不能被當成換行擋掉
    studio = srv.RequestHandlerClass.studio
    shutil.copy(ROOT / "niche.example.yaml", studio.root / "niche.yaml")
    import subprocess
    import sys
    real = subprocess.Popen
    monkeypatch.setattr("pipeline.web.subprocess.Popen",
                        lambda cmd, **k: real([sys.executable, "-c", ""], **k))
    assert req(srv, "POST", "/api/run", {"mode": "dry", "topic": topic})[0] == 200


def test_niche_round_trip_and_readable_by_pipeline(srv):
    assert req(srv, "POST", "/api/niche", NICHE)[0] == 200
    saved = yaml.safe_load((srv.RequestHandlerClass.studio.root / "niche.yaml").read_text(encoding="utf-8"))
    assert saved["theme"] == "新手養貓" and saved["minutes"] == 5
    assert saved["facts"] == [{"subject": "貓", "value": "3 公斤", "source": ""}]  # 空白列丟掉
    state = json.loads(req(srv, "GET", "/api/state")[1])
    assert state["niche_saved"] and state["niche"]["channel_name"] == "貓奴研究所"


@pytest.mark.parametrize("bad", [
    {"channel_name": " "},
    {"seed_topics": []},
    {"minutes": 0},
    {"minutes": "8"},
    {"facts": [{"subject": "貓", "value": ""}]},
])
def test_invalid_niche_refused(srv, bad):
    code, body = req(srv, "POST", "/api/niche", dict(NICHE, **bad))
    assert code == 400 and json.loads(body)["error"]
    assert not (srv.RequestHandlerClass.studio.root / "niche.yaml").exists()


def test_client_secrets_must_be_desktop_app(srv):
    root = srv.RequestHandlerClass.studio.root
    assert req(srv, "POST", "/api/client_secrets", {"web": {}})[0] == 400
    assert req(srv, "POST", "/api/client_secrets", {"installed": {"client_id": "x"}})[0] == 200
    assert json.loads((root / "client_secrets.json").read_text(encoding="utf-8"))["installed"]["client_id"] == "x"


def test_files_cannot_escape_output(srv):
    root = srv.RequestHandlerClass.studio.root
    (root / ENV).write_text("OPENROUTER_API_KEY=sk-secret-xyz\n", encoding="utf-8")
    (root / "output" / "20260101-000000").mkdir(parents=True)
    for path in ["/files/20260101-000000/..%2F..%2F" + ENV, "/files/../" + ENV,
                 "/files/20260101-000000/../../" + ENV, "/files/x/" + ENV]:
        code, body = req(srv, "GET", path + "?t=" + srv.RequestHandlerClass.studio.token)
        assert code == 404 and b"sk-secret" not in body


def test_models_keeps_priced_text_models_only(srv, monkeypatch):
    fake = {"data": [
        {"id": "a/cheap", "name": "Cheap", "pricing": {"prompt": "0.000001", "completion": "0.000002"},
         "architecture": {"output_modalities": ["text"]}},
        {"id": "a/router", "name": "Router", "pricing": {"prompt": "-1", "completion": "-1"},
         "architecture": {"output_modalities": ["text"]}},
        {"id": "a/img", "name": "Img", "pricing": {"prompt": "0", "completion": "0"},
         "architecture": {"output_modalities": ["image"]}},
        {"id": "a/free", "name": "Free", "pricing": {"prompt": "0", "completion": "0"},
         "architecture": {"output_modalities": ["text"]}},
    ]}
    monkeypatch.setattr("pipeline.web._get_json", lambda url, key=None: fake)
    code, body = req(srv, "GET", "/api/models")
    models = json.loads(body)["models"]
    assert code == 200 and [m["id"] for m in models] == ["a/cheap", "a/free"]
    assert models[0]["in"] == pytest.approx(1.0) and models[0]["out"] == pytest.approx(2.0)  # 每百萬 token


def test_test_key_uses_saved_key_and_never_echoes_it(srv, monkeypatch):
    root = srv.RequestHandlerClass.studio.root
    (root / ENV).write_text("OPENROUTER_API_KEY=sk-saved\n", encoding="utf-8")
    seen = []
    monkeypatch.setattr("pipeline.web._get_json",
                        lambda url, key=None: seen.append(key) or {"data": {"usage": 0.5, "limit": None}})
    code, body = req(srv, "POST", "/api/test_key", {"key": ""})
    assert code == 200 and seen == ["sk-saved"] and b"sk-saved" not in body
    req(srv, "POST", "/api/test_key", {"key": " sk-typed "})
    assert seen[-1] == "sk-typed"


def test_test_key_reports_bad_key(srv, monkeypatch):
    import urllib.error

    def reject(req_, timeout):
        raise urllib.error.HTTPError(req_.full_url, 401, "no", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", reject)
    code, body = req(srv, "POST", "/api/test_key", {"key": "sk-bad"})
    assert code == 400 and "無效" in json.loads(body)["error"]
    assert req(srv, "POST", "/api/test_key", {"key": ""})[0] == 400  # 沒存也沒填


def test_run_refused_before_niche_saved(srv):
    assert req(srv, "POST", "/api/run", {"mode": "dry"})[0] == 400


def test_dry_run_job_end_to_end(srv):
    studio = srv.RequestHandlerClass.studio
    shutil.copy(ROOT / "niche.example.yaml", studio.root / "niche.yaml")
    assert req(srv, "POST", "/api/run", {"mode": "dry", "topic": "貓為什麼踩踏", "shorts": True})[0] == 200
    assert req(srv, "POST", "/api/run", {"mode": "dry"})[0] == 409  # 一次只做一支
    deadline = time.time() + 90
    while time.time() < deadline:
        job = json.loads(req(srv, "GET", "/api/job")[1])["job"]
        if not job["running"]:
            break
        time.sleep(0.5)
    assert job["returncode"] == 0, "\n".join(job["log"])
    assert job["summary"]["video"] and job["summary"]["segments"]
    code, body = req(srv, "GET", "/files/%s/video.mp4?t=%s" % (job["name"], studio.token))
    assert code == 200 and len(body) > 1000
    assert not (studio.root / "output" / "topics_used.json").exists()  # dry-run 不記題目
