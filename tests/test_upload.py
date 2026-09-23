import inspect
import json

# pipeline.upload 刻意不在模組層級 import:test_smoke.py 斷言 dry-run 不會把它拉進
# sys.modules,module 層級 import 會在 collection 階段就把它載進整個 pytest session。
FUTURE_EXPIRY = "2099-01-01T00:00:00Z"


def _write_token(path, scopes):
    path.write_text(json.dumps({
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "refresh_token": "test-refresh-token",
        "token": "test-access-token",
        "scopes": scopes,
        "expiry": FUTURE_EXPIRY,
    }), encoding="utf-8")


def test_upload_default_privacy_is_private():
    from pipeline.upload import upload
    assert inspect.signature(upload).parameters["privacy"].default == "private"


def test_scopes_are_exactly_upload_and_analytics_readonly():
    from pipeline.upload import SCOPES
    assert SCOPES == ["https://www.googleapis.com/auth/youtube.force-ssl",
                       "https://www.googleapis.com/auth/yt-analytics.readonly"]


def test_needs_reauth_when_token_missing_a_scope(tmp_path):
    from google.oauth2.credentials import Credentials
    from pipeline.upload import _needs_reauth

    token_path = tmp_path / "token.json"
    _write_token(token_path, ["https://www.googleapis.com/auth/youtube.upload"])
    creds = Credentials.from_authorized_user_file(str(token_path))
    assert _needs_reauth(creds) is True


def test_needs_reauth_false_when_token_has_all_scopes(tmp_path):
    from google.oauth2.credentials import Credentials
    from pipeline.upload import SCOPES, _needs_reauth

    token_path = tmp_path / "token.json"
    _write_token(token_path, list(SCOPES))
    creds = Credentials.from_authorized_user_file(str(token_path))
    assert _needs_reauth(creds) is False


def test_get_credentials_reauthorizes_insufficient_scope_token(tmp_path, monkeypatch):
    from pipeline.upload import get_credentials

    token_path = tmp_path / "token.json"
    _write_token(token_path, ["https://www.googleapis.com/auth/youtube.upload"])

    calls = []

    class FakeCreds:
        def to_json(self):
            return "{}"

    class FakeFlow:
        def run_local_server(self, port=0):
            return FakeCreds()

    def fake_from_client_secrets_file(client_secrets, scopes):
        calls.append((client_secrets, scopes))
        return FakeFlow()

    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        staticmethod(fake_from_client_secrets_file),
    )

    get_credentials("client_secrets.json", str(token_path))
    assert calls, "權限不足的舊 token 應該觸發 InstalledAppFlow 重新授權"
    # U8:重新授權要一次要齊全部 SCOPES,不能只要其中一個
    from pipeline.upload import SCOPES
    assert list(calls[0][1]) == SCOPES


def test_get_credentials_reuses_token_with_full_scopes(tmp_path, monkeypatch):
    from pipeline.upload import SCOPES, get_credentials

    token_path = tmp_path / "token.json"
    _write_token(token_path, list(SCOPES))

    def boom(*a, **k):
        raise AssertionError("擁有全部 scope 時不該重新授權")

    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        staticmethod(boom),
    )

    creds = get_credentials("client_secrets.json", str(token_path))
    assert creds.has_scopes(SCOPES)


def test_upload_request_body_is_private(tmp_path, monkeypatch):
    """不只看預設參數,要看真正送給 API 的 body。"""
    from pipeline import upload as up
    bodies = []

    class Req:
        def next_chunk(self):
            return None, {"id": "VID"}

    class Videos:
        def insert(self, **kw):
            bodies.append(kw["body"])
            return Req()

    class YT:
        def videos(self):
            return Videos()

    monkeypatch.setattr(up, "get_credentials", lambda *a: None)
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **k: YT())
    monkeypatch.setattr("googleapiclient.http.MediaFileUpload", lambda *a, **k: None)
    assert up.upload(tmp_path / "v.mp4", "t", "d", "cs.json", "tok.json") == "VID"
    assert bodies[0]["status"]["privacyStatus"] == "private"


def test_needs_reauth_when_token_has_only_one_of_the_scopes(tmp_path):
    # U9:只有 force-ssl、缺 Analytics 的 token 也要重新授權(不能「有任一個就好」)
    from google.oauth2.credentials import Credentials
    from pipeline.upload import SCOPES, _needs_reauth

    token_path = tmp_path / "token.json"
    _write_token(token_path, [SCOPES[0]])
    assert _needs_reauth(Credentials.from_authorized_user_file(str(token_path))) is True


def test_needs_reauth_when_token_has_extra_scopes(tmp_path):
    # 多出來的權限(例如 Gmail)不能照用,token 外洩時損害會超出這條產線
    from google.oauth2.credentials import Credentials
    from pipeline.upload import SCOPES, _needs_reauth

    token_path = tmp_path / "token.json"
    _write_token(token_path, list(SCOPES) + ["https://www.googleapis.com/auth/gmail.readonly"])
    assert _needs_reauth(Credentials.from_authorized_user_file(str(token_path))) is True
