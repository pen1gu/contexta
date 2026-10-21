"""기준 얼굴 선택, Buffalo_L 임베딩, DeepFace cosine 거리."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_NAME = "Buffalo_L"
DETECTOR_BACKEND = "yunet"
YUNET_SCORE_THRESHOLD = 0.8
DISTANCE_METRIC = "cosine"
FALLBACK_COSINE_THRESHOLD = 0.55


class NoFaceError(Exception):
    """기준 사진에서 얼굴을 찾지 못했을 때."""

    def __init__(self) -> None:
        super().__init__(
            "기준 사진에서 얼굴을 찾지 못했습니다. "
            "얼굴이 잘 보이는 사진으로 다시 업로드해 주세요."
        )


class ImageDecodeError(Exception):
    """이미지 바이트를 열지 못했을 때."""


@dataclass(frozen=True)
class ReferenceFace:
    embedding: list[float]
    used_largest_of_many: bool


def face_area(facial_area: dict) -> int:
    return int(facial_area["w"]) * int(facial_area["h"])


def select_largest_face(facial_areas: list[dict]) -> dict:
    """면적(w*h)이 가장 큰 얼굴 하나를 고른다. 비어 있으면 재업로드 예외."""
    if not facial_areas:
        raise NoFaceError()
    return max(facial_areas, key=face_area)


def is_same_person(distance: float, threshold: float) -> bool:
    return distance <= threshold


def any_face_matches(distances: list[float], threshold: float) -> bool:
    """검출된 얼굴 중 하나라도 임계값 안이면 같은 사람이다."""
    return any(is_same_person(distance, threshold) for distance in distances)


def cosine_threshold() -> float:
    """라이브러리의 Buffalo_L cosine 임계값. 읽지 못하면 0.55."""
    try:
        from deepface.modules.verification import find_threshold

        return float(find_threshold(MODEL_NAME, DISTANCE_METRIC))
    except Exception as error:
        logger.warning(
            "Buffalo_L cosine 임계값을 읽지 못해 0.55를 사용합니다.",
            exc_info=error,
        )
        return FALLBACK_COSINE_THRESHOLD


def cosine_distance(source_embedding: list[float], target_embedding: list[float]) -> float:
    """DeepFace find_distance의 cosine. 직접 유사도를 계산하지 않는다."""
    from deepface.modules.verification import find_distance

    distance = find_distance(source_embedding, target_embedding, DISTANCE_METRIC)
    return float(distance)


def matches_target(
    target_embedding: list[float],
    face_embeddings: list[list[float]],
    threshold: float,
) -> bool:
    if not face_embeddings:
        return False
    distances = [
        cosine_distance(target_embedding, embedding) for embedding in face_embeddings
    ]
    return any_face_matches(distances, threshold)


def extract_reference(image_bytes: bytes) -> ReferenceFace:
    """기준 사진에서 얼굴이 하나도 없으면 NoFaceError. 여러 장이면 가장 큰 얼굴."""
    representations = _represent(image_bytes)
    usable = [item for item in representations if _usable_representation(item)]
    if not usable:
        raise NoFaceError()
    areas = [item["facial_area"] for item in usable]
    selected_area = select_largest_face(areas)
    selected = usable[areas.index(selected_area)]
    return ReferenceFace(
        embedding=_as_floats(selected["embedding"]),
        used_largest_of_many=len(usable) > 1,
    )


def extract_embeddings(image_bytes: bytes) -> list[list[float]]:
    """사진에서 검출된 모든 얼굴 임베딩. 없으면 빈 리스트."""
    embeddings: list[list[float]] = []
    for item in _represent(image_bytes):
        raw = item.get("embedding")
        if raw:
            embeddings.append(_as_floats(raw))
    return embeddings


def _patch_deepface_logger() -> None:
    """dump_log를 한 번만 바꿔, 콘솔 인코딩이 못 담는 이모지를 빼고 출력한다."""
    from deepface.commons.logger import Logger

    if getattr(Logger, "_contexta_dump_log_patched", False):
        return

    def dump_log(self, message: object) -> None:
        encoding = sys.stdout.encoding or "utf-8"
        safe_message = str(message).encode(encoding, errors="ignore").decode(encoding)
        print(f"{str(datetime.now())[2:-7]} - {safe_message}")

    Logger.dump_log = dump_log
    Logger._contexta_dump_log_patched = True


def _represent(image_bytes: bytes) -> list[dict]:
    image = _decode_bgr(image_bytes)
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    _patch_deepface_logger()
    os.environ["yunet_score_threshold"] = str(YUNET_SCORE_THRESHOLD)
    from deepface import DeepFace

    try:
        results = DeepFace.represent(
            img_path=image,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR_BACKEND,
            align=True,
            enforce_detection=True,
        )
    except Exception as error:
        if _is_no_face(error):
            return []
        raise
    if not isinstance(results, list):
        raise TypeError("DeepFace.represent 결과가 리스트가 아닙니다.")
    return results


def _decode_bgr(image_bytes: bytes):
    from io import BytesIO

    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            transposed = ImageOps.exif_transpose(image)
            if transposed is None:
                raise ImageDecodeError("이미지를 디코드하지 못했습니다.")
            rgb = np.asarray(transposed.convert("RGB"))
    except ImageDecodeError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ImageDecodeError("이미지를 디코드하지 못했습니다.") from error
    if getattr(rgb, "ndim", 0) != 3 or rgb.shape[2] != 3:
        raise ImageDecodeError("이미지 채널 형식이 올바르지 않습니다.")
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _usable_representation(result: dict) -> bool:
    area = result.get("facial_area")
    if not isinstance(area, dict) or "w" not in area or "h" not in area:
        return False
    embedding = result.get("embedding")
    return bool(embedding)


def _as_floats(embedding) -> list[float]:
    return [float(value) for value in embedding]


def _is_no_face(error: BaseException) -> bool:
    messages = [str(error).lower()]
    if error.__cause__ is not None:
        messages.append(str(error.__cause__).lower())
    return any("could not be detected" in message for message in messages)
