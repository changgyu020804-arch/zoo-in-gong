import sqlite3

from flask import redirect, render_template, request, send_from_directory, session, url_for

from db import get_db_connection
from persona import PERSONA_KEYS, enrich_profile, extract_persona_answers
from services import get_user_profile
from text_utils import clean_multi_line_text, clean_single_line_text


def register_auth_routes(app):
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

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            username = clean_single_line_text(request.form["username"], 50)
            password = clean_single_line_text(request.form["password"], 100)
            pet_name = clean_single_line_text(request.form["pet_name"], 50)
            pet_species = clean_single_line_text(request.form["pet_species"], 50)
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

            if not all([username, password, pet_name, pet_species, personality]):
                return render_template("signup.html", error="필수 정보를 모두 입력해 주세요.")

            temp_profile = enrich_profile(
                {
                    "username": username,
                    "pet_name": pet_name,
                    "pet_species": pet_species,
                    "pet_age": pet_age,
                    "activity_level": activity_level,
                    "pet_likes": pet_likes,
                    "pet_dislikes": pet_dislikes,
                    "avatar_url": "",
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
                            activity_level, pet_likes, pet_dislikes, avatar_url, bio,
                            status_message, favorite_place, personality,
                            owner_persona_note,
                            {", ".join(PERSONA_KEYS)}
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
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
                            "",
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
                return render_template("signup.html", error="이미 사용 중인 아이디예요.")

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
        return redirect(url_for("login"))

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
