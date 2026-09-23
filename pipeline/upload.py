from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


def _needs_reauth(creds):
    """判斷這組憑證要不要重新走一次授權流程:沒有憑證、憑證記錄的 scopes 不包含 SCOPES
    全部(例如舊 token 只有 youtube.upload),或多了 SCOPES 以外的權限(token.json 外洩時
    損害範圍就不只這條產線)。純函式,方便測試。
    注意:重新授權只會換掉本機的 token,舊 token 在 Google 那邊仍有效,要到
    https://myaccount.google.com/permissions 撤銷。"""
    if creds is None or not creds.has_scopes(SCOPES):
        return True
    return bool(set(creds.scopes or []) - set(SCOPES))


def get_credentials(client_secrets, token_path):
    """回傳有 SCOPES 全部權限的 OAuth 憑證。舊 token 權限不夠(例如只有舊版 youtube.upload)
    時,不能沿用,要重新走一次授權流程。
    讀 token 檔時刻意不傳 scopes 給 from_authorized_user_file:一旦傳了,google-auth
    會直接把 creds.scopes 蓋成傳入值,has_scopes(SCOPES) 就恆為 True,擋不到權限不足的
    舊 token。不傳的話 creds.scopes 才會取 token 檔裡實際記錄的值。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path)
        if _needs_reauth(creds):
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES).run_local_server(port=0)
        Path(token_path).write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload(video, title, description, client_secrets, token_path, privacy="private"):
    """用 YouTube Data API 官方上傳。預設 private,公開與否由人自己在 Studio 決定。"""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_credentials(client_secrets, token_path)
    yt = build("youtube", "v3", credentials=creds)
    req = yt.videos().insert(
        part="snippet,status",
        body={"snippet": {"title": title, "description": description},
              "status": {"privacyStatus": privacy}},
        media_body=MediaFileUpload(str(video), resumable=True),
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


def finish(video_id, client_secrets, token_path, thumbnail=None, playlist_id=None):
    """上傳後的收尾:設縮圖、加進播放清單。錯誤不吞,讓呼叫端知道哪一步失敗。"""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_credentials(client_secrets, token_path)
    yt = build("youtube", "v3", credentials=creds)
    if thumbnail:
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
    if playlist_id:
        yt.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id,
                               "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
        ).execute()
