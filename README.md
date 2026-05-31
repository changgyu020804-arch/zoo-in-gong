# Zoo-In-Gong

강아지 프로필과 게시물을 중심으로 친구를 찾고, 좋아요/댓글/메시지로 소통하는 Flask 기반 반려견 SNS입니다. 사진 업로드 시 Gemini API를 연결하면 반려견 페르소나를 반영한 AI 캡션도 만들 수 있습니다.

## 주요 기능

- 회원가입, 로그인, 프로필 편집
- 반려견 페르소나 설문과 기본 아바타
- 사진 게시물 업로드, 좋아요, 댓글, 북마크
- 친구 추천, 팔로우, 프로필 검색
- 알림 패널과 1:1 메시지
- Gemini 기반 캡션 미리보기와 댓글 추천

## 로컬 실행

```powershell
python -m pip install -r requirements.txt
python app.py
```

브라우저에서 `http://127.0.0.1:5000`으로 접속합니다.

## 환경 변수

프로젝트 루트에 `.env` 파일을 만들고 필요한 값을 넣습니다.

```env
SECRET_KEY=원하는_비밀키
GOOGLE_API_KEY=발급받은_Gemini_API_키
DATABASE_PATH=database.db
UPLOAD_FOLDER=static/uploads
FLASK_DEBUG=1
```

`GOOGLE_API_KEY`가 없으면 AI 캡션 기능은 대체 문구를 사용하고, 로그인/업로드/좋아요/댓글 같은 기본 기능은 그대로 동작합니다. `.env`는 `.gitignore`에 포함되어 있으므로 GitHub에 올라가지 않습니다.

## 테스트

```powershell
pytest
```

테스트는 임시 SQLite DB와 임시 업로드 폴더를 사용합니다. 실제 개발 DB나 업로드 이미지는 건드리지 않습니다.

## 배포 메모

- `requirements.txt` 기준으로 의존성을 설치합니다.
- `SECRET_KEY`, `GOOGLE_API_KEY`, `PORT`, `FLASK_DEBUG`는 환경 변수로 관리합니다.
- 로컬 DB(`database.db`)와 업로드 파일(`static/uploads`)은 개발 데이터이므로 운영 저장소와 분리하는 것을 권장합니다.
- `Procfile`은 Gunicorn 실행을 기준으로 합니다.
