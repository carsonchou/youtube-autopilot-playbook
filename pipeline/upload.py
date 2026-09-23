from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload(video, title, description, client_secrets, token_path, privacy="private"):
    """用 YouTube Data API 官方上傳。預設 private,公開與否由人自己在 Studio 決定。"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials.from_authorized_user_file(token_path, SCOPES) if Path(token_path).exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES).run_local_server(port=0)
        Path(token_path).write_text(creds.to_json(), encoding="utf-8")
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
