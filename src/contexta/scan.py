"""드라이브 목록, 임베딩 캐시, 거리 비교를 한 흐름으로 묶는다."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from contexta.auth import access_token as current_access_token
from contexta.auth import refresh_access_token
from contexta.drive import TokenExpiredError, download_thumbnails, list_image_files
from contexta.face import ReferenceFace, cosine_threshold, extract_embeddings, matches_target

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = PROJECT_ROOT / ".cache" / "embeddings.json"
DOWNLOAD_BATCH_SIZE = 8
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class MatchThumbnail:
    filename: str
    content: bytes


@dataclass
class ScanResult:
    matches: list[MatchThumbnail]
    matched_count: int
    mismatched_count: int
    undetected_count: int
    skipped_count: int
    error_count: int
    total_count: int
    used_largest_of_many: bool


@dataclass
class _Tally:
    matched: int = 0
    mismatched: int = 0
    undetected: int = 0
    skipped: int = 0
    errors: int = 0
    done: int = 0


@dataclass
class _GalleryItem:
    file_id: str
    filename: str
    url: str
    content: bytes | None = None


@dataclass
class _ScanState:
    tally: _Tally = field(default_factory=_Tally)
    gallery: list[_GalleryItem] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)


def cache_key(file_id: str, md5_checksum: str) -> str:
    return f"{file_id}:{md5_checksum}"


def scan_folder(
    service,
    credentials,
    folder_id: str,
    reference: ReferenceFace,
    on_progress: ProgressCallback,
) -> ScanResult:
    """미캐시 사진은 여덟 장씩 받아 메인 스레드에서 한 장씩 추론한다."""
    threshold = cosine_threshold()
    cache = _load_cache()
    files = list_image_files(service, folder_id)
    total = len(files)
    state = _ScanState()
    on_progress(0, total)

    for drive_file in files:
        _consume_file(
            drive_file,
            cache=cache,
            credentials=credentials,
            reference=reference,
            threshold=threshold,
            state=state,
            total=total,
            on_progress=on_progress,
        )
    _flush_pending(
        state,
        cache=cache,
        credentials=credentials,
        reference=reference,
        threshold=threshold,
        total=total,
        on_progress=on_progress,
    )
    _fill_match_thumbnails(state, credentials)
    matches = [
        MatchThumbnail(filename=item.filename, content=item.content)
        for item in state.gallery
        if item.content
    ]
    tally = state.tally
    logger.info(
        "스캔을 마쳤습니다. folder_id=%s matched=%s mismatched=%s undetected=%s skipped=%s errors=%s",
        folder_id,
        tally.matched,
        tally.mismatched,
        tally.undetected,
        tally.skipped,
        tally.errors,
    )
    return ScanResult(
        matches=matches,
        matched_count=tally.matched,
        mismatched_count=tally.mismatched,
        undetected_count=tally.undetected,
        skipped_count=tally.skipped,
        error_count=tally.errors,
        total_count=total,
        used_largest_of_many=reference.used_largest_of_many,
    )


def _consume_file(
    drive_file: dict,
    *,
    cache: dict,
    credentials,
    reference: ReferenceFace,
    threshold: float,
    state: _ScanState,
    total: int,
    on_progress: ProgressCallback,
) -> None:
    file_id = drive_file.get("id")
    if not file_id:
        _count_error(state, total, on_progress, "파일 id가 없습니다.", drive_file)
        return
    mime_type = str(drive_file.get("mimeType") or "").lower()
    if mime_type not in SUPPORTED_MIME_TYPES:
        state.tally.skipped += 1
        _advance(state, total, on_progress)
        return
    if not drive_file.get("thumbnailLink"):
        _count_error(state, total, on_progress, "thumbnailLink가 없습니다.", drive_file)
        return
    key = cache_key(file_id, str(drive_file.get("md5Checksum") or ""))
    cached = cache.get(key)
    if _is_embedding_list(cached):
        try:
            _apply_embeddings(state, drive_file, cached, reference, threshold, content=None)
        except Exception as error:
            _log_file("얼굴 비교에 실패했습니다.", drive_file, error)
            state.tally.errors += 1
        _advance(state, total, on_progress)
        return
    state.pending.append(drive_file)
    if len(state.pending) >= DOWNLOAD_BATCH_SIZE:
        _flush_pending(
            state,
            cache=cache,
            credentials=credentials,
            reference=reference,
            threshold=threshold,
            total=total,
            on_progress=on_progress,
        )


def _flush_pending(
    state: _ScanState,
    *,
    cache: dict,
    credentials,
    reference: ReferenceFace,
    threshold: float,
    total: int,
    on_progress: ProgressCallback,
) -> None:
    if not state.pending:
        return
    downloaded = _download_batch(
        credentials,
        [(item["id"], item["thumbnailLink"]) for item in state.pending],
    )
    wrote = False
    for item in state.pending:
        payload = downloaded.get(item["id"])
        if isinstance(payload, bytes) and payload:
            try:
                embeddings = extract_embeddings(payload)
            except Exception as error:
                _log_file("얼굴 추론에 실패했습니다.", item, error)
                state.tally.errors += 1
            else:
                cache[cache_key(item["id"], str(item.get("md5Checksum") or ""))] = embeddings
                wrote = True
                try:
                    _apply_embeddings(
                        state,
                        item,
                        embeddings,
                        reference,
                        threshold,
                        content=payload if embeddings else None,
                    )
                except Exception as error:
                    _log_file("얼굴 비교에 실패했습니다.", item, error)
                    state.tally.errors += 1
        else:
            error = payload if isinstance(payload, BaseException) else None
            _log_file("썸네일을 받지 못했습니다.", item, error)
            state.tally.errors += 1
        _advance(state, total, on_progress)
    if wrote:
        _save_cache(cache)
    state.pending.clear()


def _apply_embeddings(
    state: _ScanState,
    drive_file: dict,
    embeddings: list[list[float]],
    reference: ReferenceFace,
    threshold: float,
    content: bytes | None,
) -> None:
    if not embeddings:
        state.tally.undetected += 1
        return
    if not matches_target(reference.embedding, embeddings, threshold):
        state.tally.mismatched += 1
        return
    state.tally.matched += 1
    state.gallery.append(
        _GalleryItem(
            file_id=drive_file["id"],
            filename=str(drive_file.get("name") or drive_file["id"]),
            url=drive_file["thumbnailLink"],
            content=content,
        )
    )


def _fill_match_thumbnails(state: _ScanState, credentials) -> None:
    missing = [item for item in state.gallery if item.content is None]
    for batch in _chunks(missing, DOWNLOAD_BATCH_SIZE):
        downloaded = _download_batch(
            credentials,
            [(item.file_id, item.url) for item in batch],
        )
        for item in batch:
            payload = downloaded.get(item.file_id)
            if isinstance(payload, bytes) and payload:
                item.content = payload
                continue
            error = payload if isinstance(payload, BaseException) else None
            _log_file(
                "매칭 썸네일을 받지 못했습니다.",
                {"id": item.file_id, "name": item.filename},
                error,
            )
            state.tally.errors += 1


def _download_batch(credentials, items: list[tuple[str, str]]) -> dict[str, bytes | BaseException]:
    if not items:
        return {}
    token = current_access_token(credentials)
    downloaded = download_thumbnails(items, token)
    expired = [
        (key, url)
        for key, url in items
        if isinstance(downloaded.get(key), TokenExpiredError)
    ]
    if not expired:
        return downloaded
    token = refresh_access_token(credentials)
    downloaded.update(download_thumbnails(expired, token))
    return downloaded


def _advance(state: _ScanState, total: int, on_progress: ProgressCallback) -> None:
    state.tally.done += 1
    on_progress(state.tally.done, total)


def _count_error(
    state: _ScanState,
    total: int,
    on_progress: ProgressCallback,
    message: str,
    drive_file: dict,
) -> None:
    _log_file(message, drive_file, None)
    state.tally.errors += 1
    _advance(state, total, on_progress)


def _log_file(message: str, drive_file: dict, error: BaseException | None) -> None:
    logger.warning(
        "%s file_id=%s name=%s",
        message,
        drive_file.get("id"),
        drive_file.get("name"),
        exc_info=error,
    )


def _load_cache() -> dict:
    if not CACHE_PATH.is_file():
        return {}
    try:
        loaded = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"임베딩 캐시를 읽지 못했습니다. {CACHE_PATH} 를 삭제한 뒤 다시 검색해 주세요."
        ) from error
    if not isinstance(loaded, dict):
        raise RuntimeError(
            f"임베딩 캐시 형식이 올바르지 않습니다. {CACHE_PATH} 를 삭제한 뒤 다시 검색해 주세요."
        )
    return loaded


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(cache, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(CACHE_PATH)


def _is_embedding_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    for face in value:
        if not isinstance(face, list) or not face:
            return False
        for number in face:
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                return False
    return True


def _chunks(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
