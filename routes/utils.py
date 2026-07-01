from flask import jsonify, session

from db import get_db_connection


def login_required_json():
    username = session.get("username")
    if username:
        return username, None
    return None, (jsonify({"error": "로그인이 필요합니다."}), 401)


def pet_profile_required_json(username):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT pet_profile_completed FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row and row["pet_profile_completed"]:
        return None
    return (
        jsonify(
            {
                "error": "게시물을 올리기 전에 우리 강아지 프로필을 만들어 주세요.",
                "requires_pet_profile": True,
                "redirect_url": "/pet-onboarding",
            }
        ),
        409,
    )
