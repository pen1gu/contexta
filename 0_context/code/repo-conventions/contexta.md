# contexta 레포 관례 캐시

- 최종 수정일: 2026-10-15
- 티어: FULL (이전 FastAPI/Next 캐시는 재개발로 삭제됨. 이 스냅샷은 현재 소스만 근거)
- 근거 파일:
  - `app.py`
  - `src/contexta/__init__.py`
  - `src/contexta/auth.py`
  - `src/contexta/drive.py`
  - `src/contexta/face.py`
  - `src/contexta/scan.py`
  - `tests/test_drive.py`
  - `tests/test_face.py`
  - `pyproject.toml`
  - `README.md`
  - `.gitignore`

삭제된 `api/`, `web/`, Docker, FastAPI, Next.js 관례는 이 캐시에 넣지 않는다.

## 패키지 구조

- Poetry 패키지 `contexta`, 소스 루트 `src/` (`packages = [{include = "contexta", from = "src"}]`).
- 라이브러리는 `src/contexta/` 모듈 분할: `auth`(OAuth·Drive 서비스), `drive`(목록·썸네일), `face`(검출·임베딩·거리), `scan`(목록·캐시·비교 오케스트레이션).
- Streamlit 진입점은 저장소 루트 `app.py`. 패키지로 넣지 않는다. 실행은 `poetry run streamlit run app.py`.
- `__init__.py`는 한 줄 모듈 docstring만. re-export·`__all__` 없음.
- 테스트는 루트 `tests/`. `pytest` `pythonpath = ["src"]`, `testpaths = ["tests"]`.
- 프로젝트 루트 경로는 `Path(__file__).resolve().parents[2]` (`auth.py`, `scan.py`).
- 런타임 파일은 루트 기준: `credentials.json`, `token.json`, `.cache/embeddings.json`.
- DB·API 서버·프론트 패키지 없음.

## 네이밍

- 모듈·함수·변수: 영어 `snake_case`. 비공개는 `_` 접두.
- 상수: `SCREAMING_SNAKE`. 모듈 내부 상수도 `_` 접두 (`_DRIVE_HTTP_TIMEOUT_SECONDS`, `_SIZE_SUFFIX`).
- 예외: 영어 `*Error`. 사용자에게 고정 문구를 주는 예외는 `__init__`에서 한국어 메시지 (`CredentialsMissingError`, `NoFaceError`). 호출부 메시지가 달라지는 예외는 `Exception` 상속 후 raise 인자 (`ImageDecodeError`, `TokenExpiredError`, `ThumbnailDownloadError`).
- 데이터 객체: 영어 PascalCase dataclass. 공개 값 중 `ReferenceFace`, `MatchThumbnail`은 `frozen=True`. 스캔 중 변하는 상태는 `_Tally`, `_GalleryItem`, `_ScanState`처럼 비공개·가변.
- UI 전용 함수(`app.py`)는 `_search`, `_drive_client`, `_render_result`처럼 비공개.
- 사용자 노출 문자열·로그 메시지는 한국어. 식별자는 영어.
- 타입 별칭은 필요한 곳에만 (`ProgressCallback`). Google API `service`·`credentials` 인자는 주석 없이 비타입으로 둔다.

## DTO·팩토리

- pydantic·전용 팩토리 클래스 없음.
- 결과·참조는 dataclass. Drive 파일은 `dict` 그대로 (`id`, `name`, `mimeType`, `md5Checksum`, `thumbnailLink`).
- 임베딩 캐시 키는 `cache_key` → `"{file_id}:{md5_checksum}"`. 캐시 값은 `list[list[float]]`.
- 테스트 주입은 키워드 전용 인자 (`sleep=`, `max_workers=`).
- 무거운 의존(DeepFace, PIL, numpy, requests)은 순수 함수 import가 끌고 오지 않도록 함수 안에서 import.

## 에러 처리·로깅

- 로거: `logger = logging.getLogger(__name__)`. 설정은 진입점 `app.py`의 `logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")` 한 곳.
- `auth`·`drive`는 로깅하지 않고 예외를 올린다. `download_thumbnails`는 장별 예외를 값으로 넣어 배치가 멈추지 않게 한다.
- `scan`은 파일 단위 실패를 `logger.warning(..., exc_info=error)`로 남기고 카운트한 뒤 계속한다. 캐시 JSON 손상은 `RuntimeError`로 올려 삼키지 않는다.
- `face.cosine_threshold`만 넓은 `Exception`을 잡고 `logger.warning` 후 상수 `FALLBACK_COSINE_THRESHOLD`(0.55)로 폴백한다. 얼굴 없음은 빈 리스트 또는 `NoFaceError`.
- UI 경계(`app.py`)는 `CredentialsMissingError`, `NoFaceError`, `ImageDecodeError`를 먼저 잡고, 나머지는 `logger.exception` 후 한국어 `st.error`.

## 테스트 네이밍·구조

- 파일: `tests/test_{모듈}.py`. 현재 `test_drive.py`, `test_face.py`. 클래스·fixture·mock 없음.
- 함수: `test_{대상}_{기대_동작을_한국어로}`. 언더스코어로 잇는다.
- 순수 함수만 assert. 예외는 `pytest.raises(예외, match="한국어 일부")`.
- 테스트 모듈 docstring·`from __future__ import annotations` 없음. 기대값은 리터럴.

## 주석 밀도

- 라이브러리 모듈과 `app.py`는 한국어 한 줄 모듈 docstring.
- 공개 함수는 이름만으로 계약이 안 보일 때 한국어 docstring 한 블록. 한 줄로 끝나는 함수(`face_area`, `is_same_person`, `cache_key`)는 docstring 없이 둔다.
- 비공개 함수와 테스트에는 docstring을 달지 않는다. 인라인 주석 almost 없음.
- 모든 라이브러리 모듈과 `app.py`는 `from __future__ import annotations`.

## 포맷·도구

- 따옴표는 쌍따옴표. 최상위 정의 사이 빈 줄 2개.
- import 묶음: 표준 라이브러리, 서드파티, `contexta` 순. 로컬 묶음 안에서도 별도 import 허용 (`scan.py`의 `access_token as current_access_token`).
- ruff/black/mypy 설정 없음. 포맷터 규칙을 이 캐시에서 만들지 않는다.
- Python `^3.11`. 개발 의존성은 pytest만.

## 무시 파일 (관찰)

`.gitignore`가 새 런타임에서 막는 것: `.env`, `__pycache__/`, `.venv/`, `venv/`, `credentials.json`, `token.json`, `.cache/`, `.pytest_cache/`. `node_modules/`, `.next/`, `api/data/previews/`는 현재 트리에 대응 소스가 없다.
