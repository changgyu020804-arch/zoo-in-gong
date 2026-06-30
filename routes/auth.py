import sqlite3

from flask import jsonify, redirect, render_template, request, send_from_directory, session, url_for

from caption_ai import is_supported_image_file
from db import get_db_connection
from persona import PERSONA_KEYS, enrich_profile, extract_persona_answers
from services import get_user_profile
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


def find_usernames_by_account_fields(fields):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT username
            FROM users
            WHERE pet_name = ? AND pet_species = ? AND phone_number = ?
            ORDER BY username
            """,
            account_lookup_values(fields),
        ).fetchall()
    return [row["username"] for row in rows]


def reset_password_for_account(fields, new_password):
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET password = ?
            WHERE username = ? AND pet_name = ? AND pet_species = ? AND phone_number = ?
            """,
            (
                new_password,
                fields["username"],
                fields["pet_name"],
                fields["pet_species"],
                fields["phone_number"],
            ),
        )
        conn.commit()
    return cursor.rowcount > 0


def register_auth_routes(app):
    @app.route("/welcome")
    def welcome():
        return render_template("welcome.html")

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
        if request.method == "POST":
            username = clean_single_line_text(request.form["username"], 50)
            password = clean_single_line_text(request.form["password"], 100)

            with get_db_connection() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ? AND password = ?",
                    (username, password),
                ).fetchone()

            if user:
                session["username"] = user["username"]
                return redirect(url_for("index"))

            return render_template("login.html", error="아이디 또는 비밀번호가 올바르지 않아요.")

        return render_template("login.html")

    @app.route("/find-account", methods=["GET", "POST"])
    def find_account():
        context = find_account_context()

        if request.method == "POST":
            action = clean_single_line_text(request.form.get("action", ""), 40)
            context["mode"] = action or "find_username"

            if action == "find_username":
                fields = clean_account_lookup_form(request.form)
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
                )

            password_error = password_validation_error(password, password_confirmation)
            if password_error:
                return render_template(
                    "signup.html",
                    error=password_error,
                    start_section="account",
                    form_data=request.form,
                )

            if not username_is_available(username):
                return render_template(
                    "signup.html",
                    error="이미 사용 중인 아이디예요.",
                    start_section="account",
                    form_data=request.form,
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
                            password,
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
                return redirect(url_for("signup_complete"))
            except sqlite3.IntegrityError:
                if avatar_path:
                    avatar_path.unlink(missing_ok=True)
                return render_template(
                    "signup.html",
                    error="이미 사용 중인 아이디예요.",
                    start_section="account",
                    form_data=request.form,
                )

        return render_template("signup.html")

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
