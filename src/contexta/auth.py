"""데스크톱 OAuth. import만으로는 브라우저를 열지 않는다."""

from __future__ import annotations

from pathlib import Path

import httplib2
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"
_DRIVE_HTTP_TIMEOUT_SECONDS = 60


class CredentialsMissingError(FileNotFoundError):
    """루트에 credentials.json이 없을 때."""

    def __init__(self) -> None:
        super().__init__(
            "credentials.json 이 프로젝트 루트에 없습니다. "
            "Google Cloud에서 Drive API를 켜고, OAuth 클라이언트를 데스크톱 앱으로 만든 뒤 "
            "받은 JSON을 루트의 credentials.json 으로 저장해 주세요."
        )


def ensure_credentials_file() -> None:
    if not CREDENTIALS_PATH.is_file():
        raise CredentialsMissingError()


def load_credentials() -> Credentials:
    """token.json이 유효하면 브라우저를 열지 않는다. 없거나 만료·취소면 로컬 서버로 동의받는다."""
    ensure_credentials_file()
    credentials = _read_token()
    if credentials and credentials.valid:
        return credentials
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError:
            credentials = None
        else:
            _write_token(credentials)
            return credentials
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent")
    _write_token(credentials)
    return credentials


def access_token(credentials: Credentials) -> str:
    if credentials.valid and credentials.token:
        return credentials.token
    return refresh_access_token(credentials)


def refresh_access_token(credentials: Credentials) -> str:
    if not credentials.refresh_token:
        raise RefreshError("리프레시 토큰이 없어 액세스 토큰을 갱신할 수 없습니다.")
    credentials.refresh(Request())
    if not credentials.token:
        raise RefreshError("갱신된 액세스 토큰이 비어 있습니다.")
    _write_token(credentials)
    return credentials.token


def build_drive_service(credentials: Credentials):
    authorized_http = AuthorizedHttp(
        credentials,
        http=httplib2.Http(timeout=_DRIVE_HTTP_TIMEOUT_SECONDS),
    )
    return build("drive", "v3", http=authorized_http, cache_discovery=False)


def _read_token() -> Credentials | None:
    if not TOKEN_PATH.is_file():
        return None
    try:
        return Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except ValueError:
        return None


def _write_token(credentials: Credentials) -> None:
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
