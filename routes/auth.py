import sqlite3
import os
import re
import unicodedata
from urllib.parse import urlsplit

from authlib.integrations.flask_client import OAuth
from flask import abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from caption_ai import is_supported_image_file
from db import get_db_connection
from persona import PERSONA_KEYS, enrich_profile, extract_persona_answers
from services import add_match_info, get_user_profile
from text_utils import clean_multi_line_text, clean_single_line_text
from upload_utils import store_uploaded_file


def find_account_context():
    return {
        "mode": "find_username",
        "found_usernames": [],
        "username_message": "",
        "password_message": "",
        "username_error": "",
        "password_error": "",
        "username_fields": {},
        "password_fields": {},
    }


def clean_account_lookup_form(form):
    return {
        "username": clean_single_line_text(form.get("username", ""), 50),
        "pet_name": clean_single_line_text(form.get("pet_name", ""), 50),
        "pet_species": clean_single_line_text(form.get("pet_species", ""), 50),
        "phone_number": clean_single_line_text(form.get("phone_number", ""), 30),
    }


def clean_signup_species(form):
    pet_species = clean_single_line_text(form.get("pet_species", ""), 50)
    if pet_species == "기타":
        return clean_single_line_text(form.get("pet_species_other", ""), 50)
    return pet_species


def username_is_available(username):
    if not username:
        return False
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
    return row is None


def username_exists(username):
    if not username:
        return False
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
    return row is not None


def safe_next_path(value):
    value = str(value or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return ""
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def password_validation_error(password, confirmation):
    if len(password) < 8:
        return "비밀번호는 8자 이상으로 만들어 주세요."
    if not any(character.isdigit() for character in password):
        return "비밀번호에 숫자를 1개 이상 넣어 주세요."
    if password != confirmation:
        return "비밀번호 확인이 일치하지 않아요."
    return ""


def account_lookup_values(fields):
    return (fields["pet_name"], fields["pet_species"], fields["phone_number"])


def normalize_account_text(value):
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def normalize_phone_number(value):
    return re.sub(r"\D", "", str(value or ""))


def account_fields_match(row, fields, include_username=False):
    if include_username and normalize_account_text(row["username"]) != normalize_account_text(fields["username"]):
        return False
    return (
        normalize_account_text(row["pet_name"]) == normalize_account_text(fields["pet_name"])
        and normalize_account_text(row["pet_species"]) == normalize_account_text(fields["pet_species"])
        and normalize_phone_number(row["phone_number"]) == normalize_phone_number(fields["phone_number"])
    )


def find_usernames_by_account_fields(fields):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT username, pet_name, pet_species, phone_number
            FROM users
            ORDER BY username
            """
        ).fetchall()
    return [row["username"] for row in rows if account_fields_match(row, fields)]


def reset_password_for_account(fields, new_password):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, username, pet_name, pet_species, phone_number
            FROM users
            """,
        ).fetchall()
        matches = [row for row in rows if account_fields_match(row, fields, include_username=True)]
        if len(matches) != 1:
            return False
        cursor = conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(new_password), matches[0]["id"]),
        )
        conn.commit()
    return cursor.rowcount > 0


def register_auth_routes(app):
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    kakao_rest_api_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    kakao_client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
    oauth = OAuth(app)
    google = oauth.register(
        name="google",
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    kakao = oauth.register(
        name="kakao",
        client_id=kakao_rest_api_key,
        client_secret=kakao_client_secret,
        authorize_url="https://kauth.kakao.com/oauth/authorize",
        access_token_url="https://kauth.kakao.com/oauth/token",
        api_base_url="https://kapi.kakao.com/",
        client_kwargs={"token_endpoint_auth_method": "client_secret_post"},
    )

    def oauth_redirect_uri(environment_key, endpoint):
        configured_uri = os.environ.get(environment_key, "").strip()
        if configured_uri:
            return configured_uri
        if os.environ.get("RENDER"):
            return url_for(endpoint, _external=True, _scheme="https")
        return url_for(endpoint, _external=True)

    def unique_oauth_username(provider, provider_user_id):
        suffix = re.sub(r"[^a-zA-Z0-9]", "", provider_user_id)[-14:] or "account"
        candidate = f"{provider}_{suffix}"[:50]
        counter = 1
        while username_exists(candidate):
            counter += 1
            candidate = f"{provider}_{suffix}_{counter}"[:50]
        return candidate

    def login_or_create_oauth_user(provider, provider_user_id, email, account_name, account_avatar_url):
        with get_db_connection() as conn:
            oauth_row = conn.execute(
                "SELECT username FROM oauth_accounts WHERE provider = ? AND provider_user_id = ?",
                (provider, provider_user_id),
            ).fetchone()
            if oauth_row:
                username = oauth_row["username"]
                conn.execute(
                    """
                    UPDATE users
                    SET account_email = ?, account_name = ?, account_avatar_url = ?
                    WHERE username = ?
                    """,
                    (email, account_name, account_avatar_url, username),
                )
            else:
                username = unique_oauth_username(provider, provider_user_id)
                conn.execute(
                    """
                    INSERT INTO users (
                        username, password, pet_name, pet_species, pet_age, persona,
                        activity_level, pet_likes, pet_dislikes, account_email,
                        account_name, account_avatar_url, pet_profile_completed
                    )
                    VALUES (?, '', '', '', 0, '', '', '', '', ?, ?, ?, 0)
                    """,
                    (username, email, account_name, account_avatar_url),
                )
                conn.execute(
                    """
                    INSERT INTO oauth_accounts (username, provider, provider_user_id, email)
                    VALUES (?, ?, ?, ?)
                    """,
                    (username, provider, provider_user_id, email),
                )
            conn.commit()
        session["username"] = username
        return username

    def welcome_context(oauth_error=""):
        return {
            "google_login_enabled": bool(google_client_id and google_client_secret),
            "kakao_login_enabled": bool(kakao_rest_api_key and kakao_client_secret),
            "oauth_error": oauth_error,
        }

    @app.route("/welcome")
    def welcome():
        return render_template("welcome.html", **welcome_context())

    @app.route("/auth/google")
    def google_login():
        if not google_client_id or not google_client_secret:
            return render_template(
                "welcome.html",
                **welcome_context("Google 로그인을 사용하려면 서버에 Google OAuth 키를 먼저 연결해야 해요."),
            ), 503
        return google.authorize_redirect(oauth_redirect_uri("GOOGLE_REDIRECT_URI", "google_callback"))

    @app.route("/auth/google/callback")
    def google_callback():
        if not google_client_id or not google_client_secret:
            return redirect(url_for("welcome"))
        try:
            token = google.authorize_access_token()
            userinfo = token.get("userinfo") or google.userinfo().json()
        except Exception:
            app.logger.exception("Google OAuth callback failed")
            return render_template(
                "welcome.html",
                **welcome_context("Google 로그인에 실패했어요. 잠시 후 다시 시도해 주세요."),
            ), 400

        provider_user_id = clean_single_line_text(userinfo.get("sub", ""), 120)
        email = clean_single_line_text(userinfo.get("email", ""), 180)
        account_name = clean_single_line_text(userinfo.get("name", ""), 80)
        account_avatar_url = clean_single_line_text(userinfo.get("picture", ""), 500)
        if not provider_user_id:
            return redirect(url_for("welcome"))

        login_or_create_oauth_user("google", provider_user_id, email, account_name, account_avatar_url)
        return redirect(url_for("index"))

    @app.route("/auth/kakao")
    def kakao_login():
        if not kakao_rest_api_key or not kakao_client_secret:
            return render_template(
                "welcome.html",
                **welcome_context("카카오 로그인을 사용하려면 서버에 카카오 앱 키를 먼저 연결해야 해요."),
            ), 503
        return kakao.authorize_redirect(oauth_redirect_uri("KAKAO_REDIRECT_URI", "kakao_callback"))

    @app.route("/auth/kakao/callback")
    def kakao_callback():
        if not kakao_rest_api_key or not kakao_client_secret:
            return redirect(url_for("welcome"))
        try:
            token = kakao.authorize_access_token()
            response = kakao.get("v2/user/me", token=token)
            response.raise_for_status()
            userinfo = response.json()
        except Exception:
            app.logger.exception("Kakao OAuth callback failed")
            return render_template(
                "welcome.html",
                **welcome_context("카카오 로그인에 실패했어요. 카카오 앱 설정을 확인해 주세요."),
            ), 400

        provider_user_id = clean_single_line_text(str(userinfo.get("id", "")), 120)
        kakao_account = userinfo.get("kakao_account") or {}
        kakao_profile = kakao_account.get("profile") or userinfo.get("properties") or {}
        email = clean_single_line_text(kakao_account.get("email", ""), 180)
        account_name = clean_single_line_text(kakao_profile.get("nickname", ""), 80) or "카카오 사용자"
        account_avatar_url = clean_single_line_text(
            kakao_profile.get("profile_image_url", "") or kakao_profile.get("profile_image", ""),
            500,
        )
        if not provider_user_id:
            return redirect(url_for("welcome"))

        login_or_create_oauth_user("kakao", provider_user_id, email, account_name, account_avatar_url)
        return redirect(url_for("index"))

    @app.route("/match/<inviter_username>")
    def match_invite(inviter_username):
        inviter_username = clean_single_line_text(inviter_username, 50)
        if not username_exists(inviter_username):
            abort(404)

        inviter = get_user_profile(inviter_username)
        viewer_username = session.get("username", "")
        viewer = get_user_profile(viewer_username) if viewer_username else None
        match_result = None
        if viewer and viewer_username != inviter_username:
            match_result = add_match_info(viewer, dict(inviter))

        invite_path = url_for("match_invite", inviter_username=inviter_username)
        return render_template(
            "match_invite.html",
            inviter=inviter,
            viewer=viewer,
            match_result=match_result,
            is_owner=viewer_username == inviter_username,
            invite_url=url_for("match_invite", inviter_username=inviter_username, _external=True),
            login_url=url_for("login", next=invite_path),
            signup_url=url_for("signup", invite=inviter_username),
        )

    @app.route("/api/signup/username-check")
    def api_signup_username_check():
        username = clean_single_line_text(request.args.get("username", ""), 50)
        if not username:
            return jsonify(
                {
                    "available": False,
                    "message": "아이디를 입력해 주세요.",
                }
            )

        available = username_is_available(username)
        return jsonify(
            {
                "available": available,
                "message": "사용할 수 있는 아이디예요." if available else "이미 사용 중인 아이디예요.",
            }
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        next_url = safe_next_path(request.values.get("next", ""))
        if request.method == "POST":
            username = clean_single_line_text(request.form["username"], 50)
            password = clean_single_line_text(request.form["password"], 100)

            with get_db_connection() as conn:
                user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                stored_password = user["password"] if user else ""
                password_matches = False
                if stored_password:
                    if stored_password.startswith(("scrypt:", "pbkdf2:")):
                        password_matches = check_password_hash(stored_password, password)
                    else:
                        password_matches = stored_password == password
                    if password_matches and stored_password == password:
                        conn.execute(
                            "UPDATE users SET password = ? WHERE username = ?",
                            (generate_password_hash(password), username),
                        )
                        conn.commit()

            if user and password_matches:
                session["username"] = user["username"]
                return redirect(next_url or url_for("index"))

            return render_template(
                "login.html",
                error="아이디 또는 비밀번호가 올바르지 않아요.",
                next_url=next_url,
            )

        return render_template("login.html", next_url=next_url)

    @app.route("/find-account", methods=["GET", "POST"])
    def find_account():
        context = find_account_context()
        requested_mode = clean_single_line_text(request.args.get("mode", ""), 40)
        if requested_mode in {"find_username", "reset_password"}:
            context["mode"] = requested_mode

        if request.method == "POST":
            action = clean_single_line_text(request.form.get("action", ""), 40)
            context["mode"] = action or "find_username"

            if action == "find_username":
                fields = clean_account_lookup_form(request.form)
                context["username_fields"] = fields
                if not all(account_lookup_values(fields)):
                    context["username_error"] = "주인공 이름, 종류, 전화번호를 모두 입력해 주세요."
                else:
                    context["found_usernames"] = find_usernames_by_account_fields(fields)
                    if context["found_usernames"]:
                        context["username_message"] = "아래 아이디를 찾았어요."
                    else:
                        context["username_error"] = "일치하는 아이디를 찾지 못했어요."

            elif action == "reset_password":
                fields = clean_account_lookup_form(request.form)
                context["password_fields"] = fields
                new_password = clean_single_line_text(request.form.get("new_password", ""), 100)
                if not all([fields["username"], *account_lookup_values(fields), new_password]):
                    context["password_error"] = "아이디, 주인공 정보, 전화번호, 새 비밀번호를 모두 입력해 주세요."
                elif reset_password_for_account(fields, new_password):
                    context["password_message"] = "비밀번호를 새로 설정했어요. 이제 로그인할 수 있어요."
                else:
                    context["password_error"] = "입력한 정보와 일치하는 계정을 찾지 못했어요."

        return render_template("find_account.html", **context)

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        invite_username = clean_single_line_text(
            request.form.get("invite_username", "") or request.args.get("invite", ""),
            50,
        )
        if invite_username and not username_exists(invite_username):
            invite_username = ""

        if request.method == "POST":
            username = clean_single_line_text(request.form["username"], 50)
            password = clean_single_line_text(request.form["password"], 100)
            password_confirmation = clean_single_line_text(request.form.get("password_confirmation", ""), 100)
            phone_number = clean_single_line_text(request.form.get("phone_number", ""), 30)
            pet_name = clean_single_line_text(request.form["pet_name"], 50)
            pet_species = clean_signup_species(request.form)
            try:
                pet_age = max(0, int((request.form.get("pet_age") or "0").strip() or 0))
            except ValueError:
                pet_age = 0
            personality = clean_single_line_text(request.form.get("personality", ""), 40)
            activity_level = clean_single_line_text(request.form.get("activity_level", "보통"), 20)
            pet_likes = clean_single_line_text(request.form.get("pet_likes", "간식"), 120)
            pet_dislikes = clean_single_line_text(request.form.get("pet_dislikes", "목욕"), 120)
            owner_persona_note = clean_multi_line_text(request.form.get("owner_persona_note", ""), 220)
            persona_answers = extract_persona_answers(request.form)

            if not all([username, password, phone_number, pet_name, pet_species, personality]):
                return render_template(
                    "signup.html",
                    error="필수 정보를 모두 입력해 주세요.",
                    start_section="account",
                    form_data=request.form,
                    invite_username=invite_username,
                )

            password_error = password_validation_error(password, password_confirmation)
            if password_error:
                return render_template(
                    "signup.html",
                    error=password_error,
                    start_section="account",
                    form_data=request.form,
                    invite_username=invite_username,
                )

            if not username_is_available(username):
                return render_template(
                    "signup.html",
                    error="이미 사용 중인 아이디예요.",
                    start_section="account",
                    form_data=request.form,
                    invite_username=invite_username,
                )

            avatar_url = ""
            avatar_path = None
            avatar_file = request.files.get("avatar")
            if avatar_file and avatar_file.filename:
                avatar_path, avatar_url = store_uploaded_file(avatar_file, "signup_avatar")
                if not is_supported_image_file(avatar_path):
                    avatar_path.unlink(missing_ok=True)
                    return render_template(
                        "signup.html",
                        error="프로필 사진은 이미지 파일만 사용할 수 있어요.",
                        start_section="avatar",
                        form_data=request.form,
                        invite_username=invite_username,
                    )

            temp_profile = enrich_profile(
                {
                    "username": username,
                    "pet_name": pet_name,
                    "pet_species": pet_species,
                    "pet_age": pet_age,
                    "activity_level": activity_level,
                    "pet_likes": pet_likes,
                    "pet_dislikes": pet_dislikes,
                    "avatar_url": avatar_url,
                    "bio": f"{pet_name}의 첫 인사예요. 오늘부터 주인공 기록을 시작해요.",
                    "status_message": "새 친구 찾는 중",
                    "favorite_place": "",
                    "personality": personality,
                    "owner_persona_note": owner_persona_note,
                    **persona_answers,
                }
            )

            try:
                with get_db_connection() as conn:
                    conn.execute(
                        f"""
                        INSERT INTO users
                        (
                            username, password, pet_name, pet_species, pet_age, persona,
                            activity_level, pet_likes, pet_dislikes, phone_number, avatar_url, bio,
                            status_message, favorite_place, personality,
                            owner_persona_note,
                            {", ".join(PERSONA_KEYS)}
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            {", ".join(["?"] * len(PERSONA_KEYS))}
                        )
                        """,
                        (
                            username,
                            generate_password_hash(password),
                            pet_name,
                            pet_species,
                            pet_age,
                            temp_profile["persona"],
                            activity_level,
                            pet_likes,
                            pet_dislikes,
                            phone_number,
                            avatar_url,
                            temp_profile["bio"],
                            temp_profile["status_message"],
                            temp_profile["favorite_place"],
                            personality,
                            owner_persona_note,
                            *[persona_answers[key] for key in PERSONA_KEYS],
                        ),
                    )
                    conn.commit()
                session["username"] = username
                if invite_username:
                    return redirect(url_for("match_invite", inviter_username=invite_username))
                return redirect(url_for("signup_complete"))
            except sqlite3.IntegrityError:
                if avatar_path:
                    avatar_path.unlink(missing_ok=True)
                return render_template(
                    "signup.html",
                    error="이미 사용 중인 아이디예요.",
                    start_section="account",
                    form_data=request.form,
                    invite_username=invite_username,
                )

        return render_template("signup.html", invite_username=invite_username)

    @app.route("/pet-onboarding", methods=["GET", "POST"])
    def pet_onboarding():
        username = session.get("username")
        if not username:
            return redirect(url_for("welcome"))

        with get_db_connection() as conn:
            account = conn.execute(
                "SELECT pet_profile_completed FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if not account:
            session.pop("username", None)
            return redirect(url_for("welcome"))
        if account["pet_profile_completed"]:
            return redirect(url_for("index"))

        if request.method == "POST":
            pet_name = clean_single_line_text(request.form.get("pet_name", ""), 50)
            pet_species = clean_signup_species(request.form)
            personality = clean_single_line_text(request.form.get("personality", ""), 40)
            try:
                pet_age = max(0, int((request.form.get("pet_age") or "0").strip() or 0))
            except ValueError:
                pet_age = 0
            activity_level = clean_single_line_text(request.form.get("activity_level", "보통"), 20)
            pet_likes = clean_single_line_text(request.form.get("pet_likes", "간식"), 120)
            pet_dislikes = clean_single_line_text(request.form.get("pet_dislikes", "목욕"), 120)
            owner_persona_note = clean_multi_line_text(request.form.get("owner_persona_note", ""), 220)
            persona_answers = extract_persona_answers(request.form)
            if not all([pet_name, pet_species, personality]):
                return render_template(
                    "signup.html",
                    onboarding_mode=True,
                    error="강아지 이름, 종류, 성격을 모두 입력해 주세요.",
                    form_data=request.form,
                    start_section="pet",
                )

            avatar_url = ""
            avatar_path = None
            avatar_file = request.files.get("avatar")
            if avatar_file and avatar_file.filename:
                avatar_path, avatar_url = store_uploaded_file(avatar_file, "pet_avatar")
                if not is_supported_image_file(avatar_path):
                    avatar_path.unlink(missing_ok=True)
                    return render_template(
                        "signup.html",
                        onboarding_mode=True,
                        error="프로필 사진은 이미지 파일만 사용할 수 있어요.",
                        form_data=request.form,
                        start_section="avatar",
                    )

            temp_profile = enrich_profile(
                {
                    "username": username,
                    "pet_name": pet_name,
                    "pet_species": pet_species,
                    "pet_age": pet_age,
                    "activity_level": activity_level,
                    "pet_likes": pet_likes,
                    "pet_dislikes": pet_dislikes,
                    "avatar_url": avatar_url,
                    "bio": f"{pet_name}의 첫 인사예요. 오늘부터 주인공 기록을 시작해요.",
                    "status_message": "새 친구 찾는 중",
                    "favorite_place": "",
                    "personality": personality,
                    "owner_persona_note": owner_persona_note,
                    **persona_answers,
                }
            )
            with get_db_connection() as conn:
                conn.execute(
                    f"""
                    UPDATE users SET
                        pet_name = ?, pet_species = ?, pet_age = ?, persona = ?,
                        activity_level = ?, pet_likes = ?, pet_dislikes = ?, avatar_url = ?,
                        bio = ?, status_message = ?, personality = ?, owner_persona_note = ?,
                        pet_profile_completed = 1,
                        {", ".join(f"{key} = ?" for key in PERSONA_KEYS)}
                    WHERE username = ?
                    """,
                    (
                        pet_name, pet_species, pet_age, temp_profile["persona"], activity_level,
                        pet_likes, pet_dislikes, avatar_url, temp_profile["bio"],
                        temp_profile["status_message"], personality, owner_persona_note,
                        *[persona_answers[key] for key in PERSONA_KEYS], username,
                    ),
                )
                conn.commit()
            return redirect(url_for("signup_complete"))

        return render_template("signup.html", onboarding_mode=True)

    @app.route("/signup/complete")
    def signup_complete():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))

        return render_template("signup_complete.html", profile=get_user_profile(username))

    @app.route("/logout")
    def logout():
        session.pop("username", None)
        return redirect(url_for("welcome"))

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
