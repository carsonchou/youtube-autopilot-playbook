"""引導式設定精靈:在瀏覽器裡一步步設定頻道、產片、上傳,不用碰終端機或設定檔。
執行方式:雙擊 start.bat(Windows)/ start.command(macOS),或 python -m pipeline.web

安全:只綁 127.0.0.1;每個 /api 與 /files 請求都要帶啟動時隨機產生的 token;Host 標頭
必須是本機位址(擋 DNS rebinding)。API 金鑰只寫不讀,狀態只回「有沒有設定」。
"""
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from .render import FONT_CANDIDATES

UI = Path(__file__).parent / "ui" / "index.html"
PKG_PARENT = str(Path(__file__).resolve().parent.parent)
JOB_RE = re.compile(r"^\d{8}-\d{6}$")
FILE_RE = re.compile(r"^[\w.-]+$")
SECRET_KEYS = {"OPENROUTER_API_KEY"}
ENV_KEYS = ["OPENROUTER_API_KEY", "LLM_MODEL", "TTS_VOICE"]
MAX_BODY = 1 << 20
OPENROUTER = "https://openrouter.ai/api/v1"


def read_env(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def write_env(path, updates):
    """只改 updates 裡的 key,其他行(含註解)原樣保留;空字串 = 不改。"""
    updates = {k: v.strip() for k, v in updates.items() if v.strip()}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], set()
    for line in lines:
        k = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if k in updates:
            out.append("%s=%s" % (k, updates[k]))
            done.add(k)
        else:
            out.append(line)
    out += ["%s=%s" % (k, v) for k, v in updates.items() if k not in done]
    _atomic_write(path, "\n".join(out) + "\n")


def _atomic_write(path, text):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:  # Python 3.9 的 write_text 沒有 newline 參數
        f.write(text)
    os.replace(tmp, path)


def _get_json(url, key=None):
    """GET 一個 OpenRouter 端點;失敗一律轉成給使用者看的 ValueError。"""
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("OpenRouter 說這把金鑰無效,請重新複製一次(前後不要有空白)")
        raise ValueError("OpenRouter 回應錯誤(%d),稍後再試" % e.code)
    except (OSError, ValueError):
        raise ValueError("連不上 OpenRouter,請確認網路")


def _text(d, key, required=False, limit=500):
    v = d.get(key, "")
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ValueError("%s 要是文字" % key)
    v = v.strip()
    if required and not v:
        raise ValueError("%s 不能空白" % key)
    if len(v) > limit:
        raise ValueError("%s 太長(上限 %d 字)" % (key, limit))
    return v


def clean_niche(d):
    """把表單送來的 niche 驗證並整理成 niche.yaml 的內容;不合格丟 ValueError(訊息給使用者看)。"""
    if not isinstance(d, dict):
        raise ValueError("格式錯誤")
    minutes = d.get("minutes", 8)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 60:
        raise ValueError("長片長度要是 1~60 的整數分鐘")
    seeds = d.get("seed_topics") or []
    if not isinstance(seeds, list) or not all(isinstance(s, str) for s in seeds):
        raise ValueError("種子主題格式錯誤")
    seeds = [s.strip() for s in seeds if s.strip()]
    if not seeds:
        raise ValueError("至少要一個種子主題")
    facts = []
    for i, f in enumerate(d.get("facts") or []):
        if not isinstance(f, dict):
            raise ValueError("第 %d 筆事實格式錯誤" % (i + 1))
        subject, value = _text(f, "subject"), _text(f, "value")
        if not subject and not value:
            continue  # 表單上留空的列
        if not subject or not value:
            raise ValueError("第 %d 筆事實的「主體」和「數值」都要填" % (i + 1))
        facts.append({"subject": subject, "value": value, "source": _text(f, "source")})
    return {
        "channel_name": _text(d, "channel_name", required=True, limit=100),
        "theme": _text(d, "theme"),
        "audience": _text(d, "audience", required=True),
        "tone": _text(d, "tone", required=True),
        "minutes": minutes,
        "playlist_id": _text(d, "playlist_id", limit=100),
        "seed_topics": seeds,
        "facts": facts,
    }


class Studio:
    """精靈的狀態:工作目錄、token、目前這一個產片工作。"""

    def __init__(self, root):
        self.root = Path(root)
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()
        self.job = None  # {"mode","running","log","returncode","name"}
        self._models = None

    # ---- 狀態 ----
    def env(self):
        return read_env(self.root / ".env")

    def niche(self):
        saved = self.root / "niche.yaml"
        src = saved if saved.exists() else self.root / "niche.example.yaml"
        data = yaml.safe_load(src.read_text(encoding="utf-8")) if src.exists() else {}
        return data or {}, saved.exists()

    def state(self):
        env = self.env()
        niche, saved = self.niche()
        font = env.get("FONT_FILE") or os.environ.get("FONT_FILE") or \
            next((p for p in FONT_CANDIDATES if os.path.exists(p)), "")
        return {
            "niche": niche,
            "niche_saved": saved,
            "env": {
                "OPENROUTER_API_KEY": bool(env.get("OPENROUTER_API_KEY")),  # 只回有沒有,不回值
                "LLM_MODEL": env.get("LLM_MODEL", ""),
                "TTS_VOICE": env.get("TTS_VOICE", ""),
            },
            "checks": {
                "python": sys.version.split()[0],
                "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
                "font": bool(font and os.path.exists(font)),
                "client_secrets": (self.root / (env.get("YT_CLIENT_SECRETS") or "client_secrets.json")).exists(),
                "token": (self.root / (env.get("YT_TOKEN") or "token.json")).exists(),
            },
            "jobs": self.recent_jobs(),
        }

    def recent_jobs(self, n=8):
        out = self.root / "output"
        if not out.is_dir():
            return []
        dirs = sorted((p for p in out.iterdir() if p.is_dir() and JOB_RE.match(p.name)), reverse=True)
        return [self.summary(p.name, brief=True) for p in dirs[:n]]

    def summary(self, name, brief=False):
        d = self.root / "output" / name
        s = {"name": name, "video": (d / "video.mp4").exists()}
        try:
            script = json.loads((d / "script.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            script = {}
        s["title"] = script.get("title", "")
        if brief:
            return s
        s["description"] = script.get("description", "")
        s["segments"] = [seg.get("text", "") for seg in script.get("segments", [])]
        fg = d / "factguard.txt"
        s["factguard"] = fg.read_text(encoding="utf-8").splitlines() if fg.exists() else []
        s["cards"] = sorted(p.name for p in d.glob("card*.png"))
        return s

    # ---- 寫入 ----
    def save_niche(self, d):
        data = clean_niche(d)
        _atomic_write(self.root / "niche.yaml",
                      yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

    def save_env(self, d):
        if not isinstance(d, dict):
            raise ValueError("格式錯誤")
        updates = {}
        for k in ENV_KEYS:
            v = d.get(k, "")
            if not isinstance(v, str) or "\n" in v or "\r" in v:
                raise ValueError("%s 格式錯誤" % k)
            updates[k] = v
        write_env(self.root / ".env", updates)

    def save_client_secrets(self, d):
        if not isinstance(d, dict) or not isinstance(d.get("installed"), dict):
            raise ValueError("這不是「電腦版應用程式」的 OAuth 用戶端檔案(JSON 裡要有 installed)")
        name = self.env().get("YT_CLIENT_SECRETS") or "client_secrets.json"
        _atomic_write(self.root / name, json.dumps(d, ensure_ascii=False, indent=2))

    # ---- OpenRouter(只讀) ----
    def models(self):
        """OpenRouter 公開的模型清單(不需要金鑰),只留輸出文字、有標價的,給表單當下拉選單。"""
        if self._models is None:
            data = _get_json(OPENROUTER + "/models")
            out = []
            for m in data.get("data", []):
                p = m.get("pricing") or {}
                try:
                    pin, pout = float(p.get("prompt")), float(p.get("completion"))
                except (TypeError, ValueError):
                    continue
                if pin < 0 or pout < 0 or "text" not in ((m.get("architecture") or {}).get("output_modalities") or []):
                    continue
                out.append({"id": m.get("id", ""), "name": m.get("name", ""), "in": pin * 1e6, "out": pout * 1e6,
                            "created": m.get("created") or 0})
            self._models = sorted(out, key=lambda m: -m["created"])  # 新的在前
        return self._models

    def test_key(self, d):
        """用 .env 裡(或表單剛填、還沒存)的金鑰問 OpenRouter 這把金鑰是否有效;不回傳金鑰本身。"""
        key = d.get("key") if isinstance(d, dict) else None
        key = (key.strip() if isinstance(key, str) else "") or self.env().get("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("還沒填金鑰")
        if "\n" in key or "\r" in key:
            raise ValueError("金鑰格式錯誤")
        info = _get_json(OPENROUTER + "/key", key).get("data") or {}
        return {"ok": True, "usage": info.get("usage"), "limit": info.get("limit"),
                "is_free_tier": info.get("is_free_tier")}

    # ---- 產片 ----
    def start_job(self, d):
        mode = d.get("mode")
        if mode not in ("dry", "make", "upload"):
            raise ValueError("mode 錯誤")
        topic = d.get("topic") or ""
        if not isinstance(topic, str) or "\n" in topic or len(topic) > 200:
            raise ValueError("題目格式錯誤")
        if not (self.root / "niche.yaml").exists():
            raise ValueError("還沒儲存頻道設定")
        cmd = [sys.executable, "-m", "pipeline.run", "--out", "output"]
        cmd += {"dry": ["--dry-run"], "make": [], "upload": ["--upload"]}[mode]
        if topic.strip():
            cmd += ["--topic", topic.strip()]
        if d.get("shorts"):
            cmd += ["--shorts"]
        with self.lock:
            if self.job and self.job["running"]:
                return False
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
                       PYTHONPATH=os.pathsep.join(filter(None, [PKG_PARENT, os.environ.get("PYTHONPATH")])))
            before = set(self._job_dirs())
            proc = subprocess.Popen(cmd, cwd=str(self.root), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            self.job = {"mode": mode, "running": True, "log": [], "returncode": None, "name": None}
            threading.Thread(target=self._watch, args=(proc, self.job, before), daemon=True).start()
        return True

    def _job_dirs(self):
        out = self.root / "output"
        return [p.name for p in out.iterdir() if p.is_dir() and JOB_RE.match(p.name)] if out.is_dir() else []

    def _watch(self, proc, job, before):
        for line in proc.stdout:
            job["log"].append(line.rstrip("\n"))
            del job["log"][:-400]
            if job["name"] is None:
                new = sorted(set(self._job_dirs()) - before)
                job["name"] = new[-1] if new else None
        job["returncode"] = proc.wait()
        new = sorted(set(self._job_dirs()) - before)
        job["name"] = new[-1] if new else job["name"]
        job["running"] = False

    def job_status(self):
        job = self.job
        if not job:
            return {"job": None}
        res = {k: job[k] for k in ("mode", "running", "returncode", "name")}
        res["log"] = list(job["log"])
        if job["name"]:
            res["summary"] = self.summary(job["name"])
        return {"job": res}


class Handler(BaseHTTPRequestHandler):
    studio = None  # 由 make_server 設定
    server_version = "playbook"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def _token_ok(self, query):
        got = self.headers.get("X-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(got.encode(), self.studio.token.encode())

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        """回 (path, query);不合格時已回應錯誤並回 None。"""
        url = urlparse(self.path)
        if not self._host_ok():
            self._send(403, {"error": "Host 不允許"})
            return None
        query = parse_qs(url.query)
        if url.path != "/" and not self._token_ok(query):
            self._send(403, {"error": "token 錯誤"})
            return None
        return url.path, query

    def do_GET(self):
        g = self._guard()
        if not g:
            return
        path, _ = g
        st = self.studio
        if path == "/":
            html = UI.read_text(encoding="utf-8").replace("__TOKEN__", st.token)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/state":
            return self._send(200, st.state())
        if path == "/api/job":
            return self._send(200, st.job_status())
        if path == "/api/models":
            try:
                return self._send(200, {"models": st.models()})
            except ValueError as e:
                return self._send(502, {"error": str(e)})
        m = re.match(r"^/files/([^/]+)/([^/]+)$", path)
        if m and JOB_RE.match(m.group(1)) and FILE_RE.match(m.group(2)):
            out = (st.root / "output").resolve()
            f = (out / m.group(1) / m.group(2)).resolve()
            if f.is_file() and out in f.parents:
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ctype)
        self._send(404, {"error": "找不到"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "資料太大"})
        raw = self.rfile.read(n)  # 先讀完再拒絕,否則 Windows 上客戶端會被 reset 而收不到 403
        g = self._guard()
        if not g:
            return
        path, _ = g
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return self._send(400, {"error": "不是 JSON"})
        st = self.studio
        actions = {"/api/niche": st.save_niche, "/api/env": st.save_env,
                   "/api/client_secrets": st.save_client_secrets}
        try:
            if path in actions:
                actions[path](data)
                return self._send(200, {"ok": True})
            if path == "/api/run":
                if not st.start_job(data if isinstance(data, dict) else {}):
                    return self._send(409, {"error": "已經有一支片在做了,等它完成"})
                return self._send(200, {"ok": True})
            if path == "/api/test_key":
                return self._send(200, st.test_key(data))
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "找不到"})


def make_server(root, port=8765):
    handler = type("BoundHandler", (Handler,), {"studio": Studio(root)})
    try:
        return ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        return ThreadingHTTPServer(("127.0.0.1", 0), handler)  # 8765 被占用就隨便挑一個


def main():
    srv = make_server(Path.cwd())
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("設定精靈已啟動:%s\n瀏覽器沒自動打開的話,把上面網址貼到瀏覽器。關掉這個視窗就會停止。" % url)
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
