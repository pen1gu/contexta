# Contexta

내 구글 드라이브 폴더에서 기준 얼굴과 같은 사람이 나온 사진을 찾는 로컬 Streamlit 데모입니다. 데이터베이스는 없고, 임베딩 캐시는 `.cache/embeddings.json` 하나만 사용합니다.

## 사전 요구

- Python 3.11 이상 (TensorFlow 휠이 있는 3.11 또는 3.12를 권장합니다)
- Poetry

## Google Drive API

1. [Google Cloud 콘솔](https://console.cloud.google.com/)에서 프로젝트를 만듭니다.
2. **API 및 서비스**에서 **Google Drive API**를 사용 설정합니다.
3. OAuth 동의 화면을 구성합니다. 앱이 테스트 모드이면 본인 Google 계정을 테스트 사용자로 추가합니다.
4. **사용자 인증 정보**에서 OAuth 클라이언트 ID를 만들고, 애플리케이션 유형을 **데스크톱 앱**으로 선택합니다.
5. JSON을 내려받아 저장소 루트에 `credentials.json`으로 둡니다.

스코프는 `https://www.googleapis.com/auth/drive.readonly` 입니다. 첫 검색에서 브라우저로 한 번 동의하면 `token.json`이 생기고, 그 토큰이 유효한 동안은 다시 열지 않습니다. `credentials.json`과 `token.json`은 git에 올리지 마세요.

## 실행

저장소 루트에서 실행합니다. 기본 `python`이 3.14라면, 먼저 3.11을 가상환경에 지정하세요.

```bash
poetry env use py -3.11
poetry install
poetry run streamlit run app.py
```

화면에서 기준 사진을 올리고 폴더 ID를 입력한 뒤 **검색 시작**을 누릅니다.

원본은 받지 않고 썸네일로 맞추며, 폴더의 직계 파일만 봅니다.

학습이나 파인튜닝은 하지 않고, 사전학습 가중치만 사용합니다.

InsightFace 가중치는 비상업 연구용입니다.

첫 검색에서 YuNet과 Buffalo_L 가중치를 사용자 홈의 `.deepface/weights`로 받습니다.
