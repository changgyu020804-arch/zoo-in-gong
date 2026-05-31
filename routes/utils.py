from flask import jsonify, session


def login_required_json():
    username = session.get("username")
    if username:
        return username, None
    return None, (jsonify({"error": "로그인이 필요합니다."}), 401)
