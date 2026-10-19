"""구글 드라이브 폴더 얼굴 검색. 검색 버튼을 누를 때만 인증한다."""

from __future__ import annotations

import logging

import streamlit as st
from google.auth.exceptions import RefreshError

from contexta.auth import (
    CredentialsMissingError,
    build_drive_service,
    ensure_credentials_file,
    load_credentials,
    refresh_access_token,
)
from contexta.face import ImageDecodeError, NoFaceError, extract_reference
from contexta.scan import ScanResult, scan_folder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="드라이브 얼굴 검색", layout="wide")


def _search(image_bytes: bytes, folder_id_value: str) -> ScanResult:
    ensure_credentials_file()
    reference = extract_reference(image_bytes)
    service, credentials = _drive_client()
    progress = st.progress(0.0, text="0/0")

    def on_progress(done: int, total: int) -> None:
        ratio = 0.0 if total == 0 else min(done / total, 1.0)
        progress.progress(ratio, text=f"{done:,}/{total:,}")

    return scan_folder(service, credentials, folder_id_value, reference, on_progress)


def _drive_client():
    credentials = st.session_state.get("drive_credentials")
    service = st.session_state.get("drive_service")
    if credentials is not None and service is not None and credentials.valid:
        return service, credentials
    if (
        credentials is not None
        and service is not None
        and credentials.expired
        and credentials.refresh_token
    ):
        try:
            refresh_access_token(credentials)
        except RefreshError:
            logger.info("저장된 로그인이 취소되어 다시 인증합니다.")
        else:
            return service, credentials
    credentials = load_credentials()
    service = build_drive_service(credentials)
    st.session_state.drive_credentials = credentials
    st.session_state.drive_service = service
    return service, credentials


def _render_result(result: ScanResult) -> None:
    if result.used_largest_of_many:
        st.warning("여러 얼굴이 있어 가장 큰 얼굴을 사용했습니다.")
    st.write(
        f"매칭 {result.matched_count:,}건 · "
        f"불일치 {result.mismatched_count:,}건 · "
        f"얼굴 미검출 {result.undetected_count:,}건 · "
        f"스킵 {result.skipped_count:,}건 · "
        f"오류 {result.error_count:,}건"
    )
    if result.total_count == 0:
        st.info("폴더에서 이미지 파일을 찾지 못했습니다.")
        return
    if not result.matches:
        st.info("매칭된 사진이 없습니다.")
        return
    columns = st.columns(4)
    for index, match in enumerate(result.matches):
        with columns[index % 4]:
            st.image(match.content, caption=match.filename, width="stretch")


st.title("구글 드라이브 얼굴 검색")
st.caption("내 드라이브 폴더의 직계 사진을 썸네일로 비교합니다. 하위 폴더와 원본 파일은 보지 않습니다.")

uploaded = st.file_uploader("기준 사진", type=["jpg", "jpeg", "png", "webp"])
folder_id = st.text_input("폴더 ID", value="1XyO51JvWUcYfT7FerDT4cAc-MOarN4XI", placeholder="드라이브 폴더 ID", key="folder_id_photo_share")

if st.button("검색 시작", type="primary"):
    if uploaded is None:
        st.error("기준 사진을 업로드해 주세요.")
    elif not folder_id.strip():
        st.error("폴더 ID를 입력해 주세요.")
    else:
        try:
            result = _search(uploaded.getvalue(), folder_id.strip())
        except CredentialsMissingError as error:
            st.error(str(error))
        except NoFaceError as error:
            st.error(str(error))
        except ImageDecodeError:
            st.error("기준 사진을 열 수 없습니다. jpeg, png, webp로 다시 업로드해 주세요.")
        except Exception as error:
            logger.exception("검색에 실패했습니다.")
            st.error(f"검색에 실패했습니다: {error}")
        else:
            _render_result(result)
