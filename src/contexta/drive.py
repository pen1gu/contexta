"""내 드라이브 폴더의 직계 이미지 목록과 썸네일 다운로드."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

PAGE_SIZE = 100
MAX_WORKERS = 4
MAX_DOWNLOAD_ATTEMPTS = 5
_REQUEST_TIMEOUT_SECONDS = 30
_SIZE_SUFFIX = re.compile(r"=s\d+")
_RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}


class TokenExpiredError(Exception):
    """썸네일 요청이 401일 때. 호출자가 토큰을 갱신한 뒤 다시 받는다."""


class ThumbnailDownloadError(Exception):
    """한 장의 썸네일을 받지 못했을 때."""


def rewrite_thumbnail_url(url: str) -> str:
    """`=s220` 같은 크기 접미사를 `=s800`으로 바꾼다. 없으면 붙인다."""
    if _SIZE_SUFFIX.search(url):
        return _SIZE_SUFFIX.sub("=s800", url, count=1)
    return f"{url}=s800"


def list_image_files(service, folder_id: str) -> list[dict]:
    """폴더 직계 파일만 가져온다. 공유 드라이브 옵션은 쓰지 않는다."""
    query = _folder_query(folder_id.strip())
    files: list[dict] = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=query,
                pageSize=PAGE_SIZE,
                fields="nextPageToken, files(id, name, mimeType, md5Checksum, thumbnailLink)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def download_thumbnail(
    url: str,
    access_token: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Authorization 헤더를 붙여 썸네일을 받는다.

    429와 rate limit 계열 403은 1, 2, 4, 8초 간격으로 최대 5회 시도한다.
    """
    import requests

    sized_url = rewrite_thumbnail_url(url)
    headers = {"Authorization": f"Bearer {access_token}"}
    for attempt in range(MAX_DOWNLOAD_ATTEMPTS):
        with requests.get(
            sized_url,
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code == 401:
                raise TokenExpiredError("액세스 토큰이 만료되었습니다.")
            if _is_rate_limited(response):
                if attempt == MAX_DOWNLOAD_ATTEMPTS - 1:
                    raise ThumbnailDownloadError(
                        f"썸네일 다운로드가 속도 제한으로 실패했습니다: HTTP {response.status_code}"
                    )
                delay = float(2**attempt)
            elif response.status_code >= 400:
                raise ThumbnailDownloadError(
                    f"썸네일 다운로드 실패: HTTP {response.status_code}"
                )
            else:
                content = response.content
                delay = None
        if delay is not None:
            sleep(delay)
            continue
        if not content:
            raise ThumbnailDownloadError("썸네일 응답이 비어 있습니다.")
        return content
    raise ThumbnailDownloadError("썸네일 다운로드에 실패했습니다.")


def download_thumbnails(
    items: list[tuple[str, str]],
    access_token: str,
    *,
    max_workers: int = MAX_WORKERS,
) -> dict[str, bytes | BaseException]:
    """제한된 스레드풀로 썸네일을 받는다. 장별 예외는 값으로 돌려 스캔이 멈추지 않게 한다."""
    results: dict[str, bytes | BaseException] = {}
    if not items:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_thumbnail, url, access_token): key
            for key, url in items
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as error:
                results[key] = error
    return results


def _folder_query(folder_id: str) -> str:
    escaped = folder_id.replace("\\", "\\\\").replace("'", "\\'")
    return (
        f"'{escaped}' in parents "
        "and mimeType contains 'image/' "
        "and trashed = false"
    )


def _is_rate_limited(response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    body = response.text.lower()
    if "rate limit" in body or "ratelimit" in body.replace(" ", ""):
        return True
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    reasons = {
        str(item.get("reason", ""))
        for item in error.get("errors", [])
        if isinstance(item, dict)
    }
    return bool(reasons & _RATE_LIMIT_REASONS)
