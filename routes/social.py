from flask import jsonify, request

from db import get_db_connection
from services import create_notification, get_profile_stats, get_user_profile
from text_utils import clean_single_line_text
from routes.utils import login_required_json


def register_social_routes(app):
    @app.route("/follow/<target_username>", methods=["POST", "DELETE"])
    def follow_user(target_username):
        username, error = login_required_json()
        if error:
            return error

        target_username = clean_single_line_text(target_username, 80)
        if target_username == username:
            return jsonify({"error": "내 프로필은 팔로우할 수 없어요."}), 400

        profile = get_user_profile(username)
        with get_db_connection() as conn:
            target = conn.execute("SELECT username FROM users WHERE username = ?", (target_username,)).fetchone()
            if not target:
                return jsonify({"error": "찾을 수 없는 친구예요."}), 404

            if request.method == "POST":
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO follows (follower_username, followed_username)
                    VALUES (?, ?)
                    """,
                    (username, target_username),
                )
                following = True
                if cursor.rowcount:
                    create_notification(
                        conn,
                        target_username,
                        username,
                        "follow",
                        f"{profile['pet_name']}이 팔로우했어요",
                        "새 멍친구가 생겼어요. 친구 목록에서 확인해보세요.",
                        "/friends",
                    )
            else:
                conn.execute(
                    """
                    DELETE FROM follows
                    WHERE follower_username = ? AND followed_username = ?
                    """,
                    (username, target_username),
                )
                following = False
            conn.commit()

        return jsonify(
            {
                "success": True,
                "following": following,
                "friend_count": get_profile_stats(username)["friend_count"],
            }
        )
