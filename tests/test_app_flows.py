import io
import base64
from types import SimpleNamespace

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    upload_folder = tmp_path / "uploads"
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("UPLOAD_FOLDER", str(upload_folder))

    import app as app_module
    import db
    import routes.posts as post_routes

    flask_app = app_module.create_app(
        database_path=database_path,
        upload_folder=upload_folder,
        testing=True,
    )

    monkeypatch.setattr(post_routes, "is_supported_image_file", lambda _path: True)
    monkeypatch.setattr(post_routes, "generate_caption", lambda *_args, **_kwargs: "테스트 캡션")

    with flask_app.test_client() as test_client:
        test_client.db = db
        yield test_client


def create_user(client, username, pet_name):
    with client.db.get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users
                (username, password, pet_name, pet_species, pet_age, persona, phone_number,
                 activity_level, pet_likes, pet_dislikes, personality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username, "pw", pet_name, "강아지", 3, "산책 리더형", "010-1234-5678", "보통", "간식", "목욕", "활발"),
        )
        conn.commit()


def login_as(client, username):
    with client.session_transaction() as session:
        session["username"] = username


def test_login_required_redirects_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_text_responses_declare_utf8(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["Content-Type"].lower()
    assert client.application.json.ensure_ascii is False


def test_signup_creates_user_and_starts_session(client):
    response = client.post(
        "/signup",
        data={
            "username": "nari",
            "password": "password1",
            "password_confirmation": "password1",
            "phone_number": "010-1234-5678",
            "pet_name": "나리",
            "pet_species": "강아지",
            "pet_age": "2",
            "personality": "명랑",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/signup/complete" in response.headers["Location"]
    with client.db.get_db_connection() as conn:
        user = conn.execute("SELECT username, pet_name, phone_number FROM users WHERE username = ?", ("nari",)).fetchone()
    assert dict(user) == {"username": "nari", "pet_name": "나리", "phone_number": "010-1234-5678"}


def test_signup_accepts_custom_pet_species(client):
    response = client.post(
        "/signup",
        data={
            "username": "custom",
            "password": "password1",
            "password_confirmation": "password1",
            "phone_number": "010-9999-1111",
            "pet_name": "또리",
            "pet_species": "기타",
            "pet_species_other": "웰시코기",
            "pet_age": "4",
            "personality": "명랑",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.db.get_db_connection() as conn:
        user = conn.execute("SELECT pet_species FROM users WHERE username = ?", ("custom",)).fetchone()
    assert user["pet_species"] == "웰시코기"


def test_signup_username_check_reports_availability(client):
    create_user(client, "nari", "나리")

    available = client.get("/api/signup/username-check?username=bori")
    duplicate = client.get("/api/signup/username-check?username=nari")

    assert available.status_code == 200
    assert available.get_json()["available"] is True
    assert duplicate.status_code == 200
    assert duplicate.get_json()["available"] is False


def test_signup_rejects_weak_or_mismatched_password(client):
    base_data = {
        "username": "weak",
        "phone_number": "010-1111-2222",
        "pet_name": "약함",
        "pet_species": "푸들",
        "pet_age": "2",
        "personality": "활발한",
    }

    weak = client.post(
        "/signup",
        data={**base_data, "password": "short1", "password_confirmation": "short1"},
    )
    mismatch = client.post(
        "/signup",
        data={**base_data, "password": "password1", "password_confirmation": "password2"},
    )

    assert "8자 이상" in weak.get_data(as_text=True)
    assert "일치하지 않아요" in mismatch.get_data(as_text=True)
    with client.db.get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("weak",)).fetchone()[0]
    assert count == 0


def test_signup_saves_optional_profile_avatar(client):
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    response = client.post(
        "/signup",
        data={
            "username": "photo",
            "password": "password1",
            "password_confirmation": "password1",
            "phone_number": "010-3333-4444",
            "pet_name": "포토",
            "pet_species": "푸들",
            "pet_age": "2",
            "personality": "활발한",
            "avatar": (io.BytesIO(png_bytes), "avatar.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.db.get_db_connection() as conn:
        user = conn.execute("SELECT avatar_url FROM users WHERE username = ?", ("photo",)).fetchone()
    assert user["avatar_url"].startswith("/uploads/signup_avatar_")


def test_find_account_page_finds_username_and_resets_password(client):
    create_user(client, "nari", "나리")

    response = client.get("/find-account")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "아이디 찾기" in html
    assert "비밀번호 재설정" in html

    response = client.post(
        "/find-account",
        data={
            "action": "find_username",
            "pet_name": "나리",
            "pet_species": "강아지",
            "phone_number": "010-1234-5678",
        },
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "아래 아이디를 찾았어요." in html
    assert "nari" in html

    response = client.post(
        "/find-account",
        data={
            "action": "reset_password",
            "username": "nari",
            "pet_name": "나리",
            "pet_species": "강아지",
            "phone_number": "010-1234-5678",
            "new_password": "newpw",
        },
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "비밀번호를 새로 설정했어요" in html

    login_response = client.post(
        "/login",
        data={"username": "nari", "password": "newpw"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/")


def test_upload_creates_post_with_caption(client):
    create_user(client, "nari", "나리")
    login_as(client, "nari")

    response = client.post(
        "/upload",
        data={
            "activity_text": "공원 산책",
            "file": (io.BytesIO(b"fake image bytes"), "dog.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    with client.db.get_db_connection() as conn:
        post = conn.execute("SELECT username, activity_text, caption FROM posts").fetchone()
    assert post["username"] == "nari"
    assert post["activity_text"] == "공원 산책"
    assert post["caption"] == "테스트 캡션"


def test_upload_adds_optional_growth_record_without_blocking_normal_posts(client):
    create_user(client, "nari", "나리")
    login_as(client, "nari")

    response = client.post(
        "/upload",
        data={
            "activity_text": "처음으로 공원 산책",
            "taken_on": "2026-06-20",
            "weight_kg": "4.7",
            "growth_milestone": "첫 산책",
            "file": (io.BytesIO(b"fake image bytes"), "first-walk.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    post_payload = response.get_json()["post"]
    assert post_payload["taken_on"] == "2026-06-20"
    assert post_payload["weight_kg"] == 4.7
    assert post_payload["growth_milestone"] == "첫 산책"
    assert post_payload["pet_age_at_post"] == 3

    with client.db.get_db_connection() as conn:
        post = conn.execute(
            """
            SELECT taken_on, weight_kg, growth_milestone, pet_age_at_post
            FROM posts
            WHERE username = ?
            """,
            ("nari",),
        ).fetchone()
    assert dict(post) == {
        "taken_on": "2026-06-20",
        "weight_kg": 4.7,
        "growth_milestone": "첫 산책",
        "pet_age_at_post": 3,
    }


def test_growth_album_includes_existing_posts_and_growth_metadata(client):
    create_user(client, "nari", "나리")
    with client.db.get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO posts (
                image_url, caption, username, activity_text, created_at,
                taken_on, weight_kg, growth_milestone, pet_age_at_post
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/static/uploads/first-walk.jpg",
                "첫 산책 성공",
                "nari",
                "처음으로 공원 산책",
                "2026-06-21 01:00:00",
                "2026-06-20",
                4.7,
                "첫 산책",
                3,
            ),
        )
        conn.execute(
            """
            INSERT INTO posts (image_url, caption, username, activity_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "/static/uploads/everyday.jpg",
                "평범한 하루",
                "nari",
                "소파에서 낮잠",
                "2026-05-03 01:00:00",
            ),
        )
        conn.commit()

    login_as(client, "nari")
    response = client.get("/profile/nari/album")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "나리의 성장 앨범" in html
    assert "첫 산책" in html
    assert "4.7kg" in html
    assert "2026년 06월" in html
    assert "2026년 05월" in html
    assert "평범한 하루" in html


def test_mobile_nav_is_consistent_across_main_pages(client):
    create_user(client, "nari", "나리")
    login_as(client, "nari")

    expected_bits = [
        'data-nav-action="home"',
        'data-nav-action="search"',
        'data-nav-action="upload"',
        'fa-wand-magic-sparkles',
        'data-nav-action="messages"',
        'data-nav-action="alerts"',
        'fa-circle-user',
    ]

    for path in ["/", "/profile", "/friends", "/studio", "/profile/nari/album"]:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        start = html.index('<nav class="mobile-nav">')
        end = html.index("</nav>", start)
        nav = html[start:end]

        assert nav.count('class="mobile-nav-button') == 7
        for expected in expected_bits:
            assert expected in nav


def test_like_comment_and_profile_update_flow(client):
    create_user(client, "owner", "오너")
    create_user(client, "friend", "친구")
    with client.db.get_db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO posts (image_url, caption, username, activity_text) VALUES (?, ?, ?, ?)",
            ("/static/uploads/dog.jpg", "안녕", "owner", "산책"),
        )
        post_id = cursor.lastrowid
        conn.commit()

    login_as(client, "friend")
    like_response = client.post(f"/like/{post_id}")
    comment_response = client.post(f"/comment/{post_id}", json={"content": "귀여워요"})
    profile_response = client.post("/api/profile", json={"status_message": "오늘도 산책 완료"})

    assert like_response.status_code == 200
    assert like_response.get_json()["liked"] is True
    assert comment_response.status_code == 200
    assert comment_response.get_json()["comment"]["content_text"] == "귀여워요"
    assert profile_response.status_code == 200
    assert profile_response.get_json()["profile"]["status_message"] == "오늘도 산책 완료"

    login_as(client, "owner")
    notifications = client.get("/api/notifications").get_json()
    assert notifications["unread_count"] == 2


def test_messages_create_unread_thread_and_mark_read(client):
    create_user(client, "nari", "나리")
    create_user(client, "bori", "보리")
    with client.db.get_db_connection() as conn:
        conn.execute(
            "INSERT INTO follows (follower_username, followed_username) VALUES (?, ?)",
            ("nari", "bori"),
        )
        conn.commit()

    login_as(client, "nari")
    send_response = client.post("/api/messages/bori", json={"body": "오늘 산책 갈래?"})
    assert send_response.status_code == 200
    assert send_response.get_json()["message"]["body"] == "오늘 산책 갈래?"

    login_as(client, "bori")
    unread_response = client.get("/api/messages")
    assert unread_response.get_json()["unread_count"] == 1
    thread = unread_response.get_json()["threads"][0]
    assert thread["username"] == "nari"
    assert thread["unread_count"] == 1

    read_response = client.get("/api/messages?mark_read=1&partner=nari")
    assert read_response.get_json()["unread_count"] == 0
    assert read_response.get_json()["threads"][0]["unread_count"] == 0


def test_message_tone_preview_uses_sender_profile(client):
    create_user(client, "nari", "나리")
    create_user(client, "bori", "보리")
    with client.db.get_db_connection() as conn:
        conn.execute(
            "UPDATE users SET personality = ? WHERE username = ?",
            ("먹보", "nari"),
        )
        conn.execute(
            "INSERT INTO follows (follower_username, followed_username) VALUES (?, ?)",
            ("nari", "bori"),
        )
        conn.commit()

    login_as(client, "nari")
    response = client.post(
        "/api/messages/tone-preview",
        json={"partner": "bori", "body": "안녕하세요"},
    )

    assert response.status_code == 200
    suggestions = response.get_json()["suggestions"]
    assert suggestions
    assert any("멍" in item or "개" in item for item in suggestions)


def test_profile_search_includes_match_summary_and_badges(client):
    create_user(client, "nari", "나리")
    create_user(client, "bori", "보리")
    with client.db.get_db_connection() as conn:
        conn.execute(
            "UPDATE users SET activity_level = ?, pet_likes = ? WHERE username = ?",
            ("높음", "산책 공원 간식", "bori"),
        )
        for index in range(3):
            conn.execute(
                """
                INSERT INTO posts (image_url, caption, likes, username, activity_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"/static/uploads/bori-{index}.jpg", "산책 기록", 4, "bori", "공원 산책"),
            )
        conn.commit()

    login_as(client, "nari")
    response = client.get("/api/profile-search?q=보리")

    assert response.status_code == 200
    profiles = response.get_json()["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["username"] == "bori"
    assert profiles[0]["match_summary"]
    assert profiles[0]["badges"]
    assert {badge["label"] for badge in profiles[0]["badges"]} & {"인기스타", "꾸준러", "산책왕"}


def test_ai_tone_suggestions_avoid_repetitive_walk_terms():
    from message_tone import suggest_message_tones

    suggestions = suggest_message_tones(
        {"persona": "산책 리더형 놀이파", "personality": "활발한", "pet_name": "나리"},
        "산책가자",
    )

    assert suggestions
    assert all("순찰" not in item for item in suggestions)
    assert all("리드줄" not in item for item in suggestions)
    assert all("코스" not in item for item in suggestions)


def test_caption_cleanup_limits_repetitive_walk_terms():
    from caption_ai import sanitize_caption_text

    caption = sanitize_caption_text(
        "산책 코스 순찰 완료!\n리드줄 잡고 산책 코스 다시 순찰하자\n#산책 #순찰 #리드줄",
        snack_terms_allowed=False,
    )
    repeated_count = sum(caption.count(term) for term in ("산책", "순찰", "리드줄", "코스"))

    assert repeated_count <= 1
    assert any(term in caption for term in ("바깥 구경", "발바닥 시간", "함께 걷는 길", "우리 길", "새 냄새 확인", "동네 한 바퀴"))


def test_caption_cleanup_finishes_truncated_sentence_and_adds_fallback_tags():
    from caption_ai import sanitize_caption_text

    caption = sanitize_caption_text(
        "이 편안함은 일종의 전략적 휴식인데 집사가 오해하는 눈치네. "
        "내 명예로운 발바닥 피로도를 수치로 환산해서 이번 달 영수증에 청구할 예정이야. "
        "심장 잡고 반성해, 집",
        fallback_hashtags="#표정박물관 #오늘도주인공",
    )

    assert "반성해, 집" not in caption
    assert "반성해." in caption
    assert "#표정박물관" in caption
    assert caption.splitlines()[0].endswith(".")


def test_caption_cleanup_does_not_treat_html_entities_as_hashtags():
    from caption_ai import sanitize_caption_text

    caption = sanitize_caption_text("&#x27;아무것도&#x27;는 #표정이말함")

    assert "#x27" not in caption
    assert "&#x27;" not in caption
    assert "#표정이말함" in caption


def test_ai_text_normalizer_repairs_entity_fragments():
    from text_utils import normalize_ai_text

    text = normalize_ai_text("#x27;아무것도#x27; &amp; & quot;표정&quot;")

    assert "#x27" not in text
    assert "&amp;" not in text
    assert "&quot;" not in text
    assert "'아무것도'" in text
    assert '"표정"' in text


def test_ai_comment_cleanup_repairs_entity_fragments():
    from comment_ai import _clean_ai_comment

    comment = _clean_ai_comment("&#x27;귀여움&#x27;은 #비밀")

    assert "#x27" not in comment
    assert "&#x27;" not in comment
    assert "#비밀" not in comment
    assert "귀여움" in comment


def test_caption_short_result_is_rejected():
    from caption_ai import is_caption_too_short

    assert is_caption_too_short("멍 #오늘도주인공")
    assert not is_caption_too_short("오늘은 꼬리가 먼저 대답한 날이라 집사도 바로 알아챘다개.")


def test_caption_cleanup_softens_report_like_terms():
    from caption_ai import sanitize_caption_text

    caption = sanitize_caption_text(
        "산책을 갔다. 냄새 지도랑 발바닥 컨디션까지 체크했으니, 집사 손은 작은 칭찬 타이밍을 챙기라개.\n"
        "상황 파악 완료, 내 표정 관리팀은 오늘도 열일했다.\n"
        "#냄새지도업데이트 #입맛회의",
    )

    for bad_word in ("냄새 지도", "발바닥 컨디션", "집사 손", "작은 칭찬 타이밍", "상황 파악 완료", "표정 관리팀", "#입맛회의"):
        assert bad_word not in caption
    assert "새 냄새" in caption
    assert "쓰담 타이밍" in caption


def test_fallback_caption_sounds_less_like_report():
    from caption_ai import make_fallback_caption

    caption = make_fallback_caption(
        {"persona": "산책 리더형 간식파", "personality": "똑똑한", "pet_name": "콩이"},
        "산책을 갔다",
    )

    for bad_word in ("냄새 지도", "발바닥 컨디션", "작은 칭찬 타이밍", "상황 파악 완료", "입맛회의"):
        assert bad_word not in caption
    assert "바깥 냄새" in caption


def test_fallback_caption_does_not_force_walk_words_for_non_walk_activity():
    from caption_ai import make_fallback_caption

    caption = make_fallback_caption(
        {"persona": "산책 리더형 간식파", "personality": "장난꾸러기", "pet_name": "콩이"},
        "잠이 너무 온다 형이 군대옷을 입혔다",
    )

    assert "군대옷" in caption
    assert "패션" in caption
    assert "바깥 냄새" not in caption
    assert "발걸음" not in caption


def test_ai_comment_short_result_uses_fallback(monkeypatch):
    import comment_ai

    monkeypatch.setattr(comment_ai, "generate_gemini_content", lambda *_args, **_kwargs: SimpleNamespace(text="멍"))

    comment = comment_ai.generate_comment_suggestion(
        {"persona": "산책 리더형 놀이파", "personality": "활발한", "pet_name": "나리"},
        {"pet_name": "콩이", "caption_text": "오늘도 신난 얼굴", "activity_text": "공놀이"},
    )

    assert comment != "멍"
    assert len("".join(ch for ch in comment if ch.isalnum())) >= 8


def test_message_tone_suggestions_keep_short_results_simple():
    from message_tone import suggest_message_tones

    suggestions = suggest_message_tones(
        {"persona": "산책 리더형 놀이파", "personality": "활발한", "pet_name": "나리"},
        "좋아",
    )

    assert suggestions
    assert all("," not in item for item in suggestions)
    assert all("꼬리로" not in item and "발바닥까지" not in item and "내 마음이" not in item for item in suggestions)
    assert all("멍" in item or "개" in item for item in suggestions)


def test_message_tone_suggestions_remove_added_comma_phrase():
    from message_tone import suggest_message_tones

    suggestions = suggest_message_tones(
        {"persona": "애교 스트라이커형 놀이파", "personality": "애교많은", "pet_name": "나리"},
        "안녕, 꼬리로 바로 접수했개",
    )

    assert suggestions == ["안녕하개", "안녕멍", "반갑개"]


def test_caption_hashtag_hint_mixes_persona_activity_and_general_tags():
    from caption_ai import _caption_hashtag_hint

    tags = _caption_hashtag_hint(
        {"persona": "산책 리더형 놀이파", "pet_name": "나리", "personality": "활발한"},
        "공원에서 공놀이하고 사진 찍었어요",
    ).split()

    assert len(tags) >= 5
    assert all(tag.startswith("#") for tag in tags)
    assert all(" " not in tag for tag in tags)
    assert any(tag in {"#공원모먼트", "#풀냄새좋아", "#바람맛집", "#잔디체크", "#햇살냠냠"} for tag in tags)
    assert any(tag in {"#공놀이대장", "#공따라눈반짝", "#굴러가면출동", "#놀이본능", "#집중력최고"} for tag in tags)


def test_home_renders_daily_mission_card(client):
    create_user(client, "nari", "나리")
    login_as(client, "nari")

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "오늘의 미션" in html
    assert "js-use-daily-mission" in html
    assert "data-mission-prompt" in html
    assert "mission-angle-chip" in html


def test_home_renders_persona_share_card(client):
    create_user(client, "nari", "나리")
    login_as(client, "nari")

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "성격 테스트 결과" in html
    assert "persona-share-section" in html
    assert "js-download-persona-card" in html
    assert "js-copy-persona-share" in html
    assert "{&#39;key&#39;" not in html
    assert "data-traits=\"밖이 좋아요" in html


def test_studio_page_renders_canvas_maker(client):
    create_user(client, "nari", "나리")
    login_as(client, "nari")

    response = client.get("/studio")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "제작소" in html
    assert "studio-canvas" in html
    assert "data-studio-background" not in html
    assert "studio-controls" in html
    assert "data-studio-text" in html
    assert "studio-text-input" in html
    assert "studio-bubble-text-input" in html
    assert "studio-bubble-size-input" in html
    assert "문구 삭제" not in html
    assert "텍스트 위치" not in html
    assert "data-studio-color" in html
    assert "data-studio-sticker" in html
    assert "말풍선 입력" in html
    assert "왕관" in html
    assert "하트" in html
    assert "꽃" in html
    assert "선글라스" in html
    assert "별" in html
    assert "뼈다귀" in html
    assert "스티커 삭제" not in html
    assert "인기 스티커" in html
    assert "PNG 저장" in html


def test_daily_awards_pick_recent_posts(client):
    from services import build_daily_awards

    create_user(client, "nari", "나리")
    create_user(client, "bori", "보리")
    with client.db.get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO posts (image_url, caption, likes, username, activity_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("/static/uploads/pose.jpg", "표정 천재 포즈", 8, "nari", "사진 찍고 눈빛 자랑"),
        )
        conn.execute(
            """
            INSERT INTO posts (image_url, caption, likes, username, activity_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("/static/uploads/play.jpg", "공놀이 MVP", 5, "bori", "공 장난감 놀이를 했어요"),
        )
        conn.commit()

    awards = build_daily_awards("nari")

    assert awards
    assert {award["label"] for award in awards} >= {"표정왕", "놀이 MVP"}
    assert all(award["post"]["id"] for award in awards)


def test_daily_awards_avoid_repeated_source_images(client):
    from services import _daily_award_image_key, build_daily_awards

    create_user(client, "ruby", "루비")
    create_user(client, "nari", "나리")
    with client.db.get_db_connection() as conn:
        repeated_posts = [
            ("20260602010101000001_sleepy.jpg", "잠이 너무 오는 표정", "잠이 너무 오는 표정을 찍어 봤어"),
            ("20260602010202000002_sleepy.jpg", "졸린 표정과 집사 옆", "잠이 너무 오는 표정을 찍어 봤어"),
            ("20260602010303000003_sleepy.jpg", "장난감 옆 졸림", "잠이 너무 오는 표정을 찍어 봤어"),
        ]
        for filename, caption, activity in repeated_posts:
            conn.execute(
                """
                INSERT INTO posts (image_url, caption, likes, username, activity_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"/static/uploads/{filename}", caption, 9, "ruby", activity),
            )
        conn.execute(
            """
            INSERT INTO posts (image_url, caption, likes, username, activity_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("/static/uploads/20260602010404000004_play.jpg", "공놀이 MVP", 6, "nari", "공 장난감 놀이를 했어요"),
        )
        conn.commit()

    awards = build_daily_awards("ruby")
    image_keys = [_daily_award_image_key(award["post"]) for award in awards]

    assert image_keys
    assert len(image_keys) == len(set(image_keys))


def test_daily_awards_fall_back_to_available_unique_posts(client):
    from services import build_daily_awards

    create_user(client, "ruby", "루비")
    with client.db.get_db_connection() as conn:
        for index in range(3):
            conn.execute(
                """
                INSERT INTO posts (image_url, caption, likes, username, activity_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"/static/uploads/20260602020{index}_quiet-{index}.jpg",
                    "편안한 하루",
                    1,
                    "ruby",
                    "조용히 쉬었어요",
                ),
            )
        conn.commit()

    awards = build_daily_awards("ruby")

    assert awards
    assert len({award["post"]["id"] for award in awards}) == len(awards)


def test_home_renders_daily_awards_when_posts_exist(client):
    create_user(client, "nari", "나리")
    with client.db.get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO posts (image_url, caption, likes, username, activity_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("/static/uploads/pose.jpg", "꼬리 신남", 3, "nari", "사진 찍고 꼬리 흔들었어요"),
        )
        conn.commit()
    login_as(client, "nari")

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "오늘의 댕댕 랭킹" in html
    assert "daily-award-card" in html
