from flask import jsonify, request, session

from caption_ai import is_supported_image_file
from db import get_db_connection
from message_tone import suggest_message_tones
from services import (
    build_message_threads,
    build_notifications,
    can_message_user,
    create_notification,
    get_conversation_messages,
    get_feed_page,
    get_post,
    get_unread_message_count,
    get_unread_notification_count,
    get_user_profile,
    mark_notifications_read,
    search_profiles,
)
from text_utils import clean_multi_line_text, clean_single_line_text
from upload_utils import store_uploaded_file
from routes.utils import login_required_json


def register_api_routes(app):
    @app.route("/api/profile", methods=["GET", "POST"])
    def api_profile():
        username, error = login_required_json()
        if error:
            return error

        if request.method == "GET":
            return jsonify(get_user_profile(username))

        payload = request.get_json(silent=True) or {}
        allowed_fields = {
            "avatar_url",
            "pet_name",
            "pet_species",
            "pet_age",
            "activity_level",
            "status_message",
            "bio",
            "pet_likes",
            "pet_dislikes",
            "favorite_place",
            "personality",
        }

        updates = []
        values = []
        for field in allowed_fields:
            if field not in payload:
                continue
            value = payload[field]
            if field in {
                "pet_name",
                "pet_species",
                "activity_level",
                "pet_likes",
                "pet_dislikes",
                "favorite_place",
                "personality",
            }:
                value = clean_single_line_text(value, 120)
            elif field == "status_message":
                value = clean_single_line_text(value, 80)
            elif field == "bio":
                value = clean_multi_line_text(value, 280)
            elif field == "avatar_url":
                value = clean_single_line_text(value, 300)
            elif field == "pet_age":
                try:
                    value = max(0, int(value))
                except (TypeError, ValueError):
                    value = 0
            updates.append(f"{field} = ?")
            values.append(value)

        if "pet_name" in payload and not clean_single_line_text(payload["pet_name"], 50):
            return jsonify({"error": "프로필 이름은 비워둘 수 없어요."}), 400

        if not updates:
            return jsonify({"error": "변경할 프로필 정보가 없습니다."}), 400

        with get_db_connection() as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE username = ?",
                (*values, username),
            )
            conn.commit()

        return jsonify({"success": True, "profile": get_user_profile(username)})

    @app.route("/api/profile/avatar", methods=["POST"])
    def api_profile_avatar():
        _username, error = login_required_json()
        if error:
            return error

        file = request.files.get("avatar")
        if not file or not file.filename:
            return jsonify({"error": "프로필 사진을 선택해 주세요."}), 400

        filepath, avatar_url = store_uploaded_file(file, "avatar")

        if not is_supported_image_file(filepath):
            try:
                filepath.unlink(missing_ok=True)
            except OSError:
                pass
            return jsonify({"error": "이미지 파일만 프로필 사진으로 사용할 수 있어요."}), 400

        return jsonify({"success": True, "avatar_url": avatar_url})

    @app.route("/api/profile-search")
    def api_profile_search():
        username, error = login_required_json()
        if error:
            return error

        query = clean_single_line_text(request.args.get("q", ""), 80)
        persona = clean_single_line_text(request.args.get("persona", ""), 80)
        sort = clean_single_line_text(request.args.get("sort", "match"), 20)
        return jsonify({"profiles": search_profiles(username, query=query, persona=persona, sort=sort)})

    @app.route("/api/notifications", methods=["GET", "POST"])
    def api_notifications():
        username, error = login_required_json()
        if error:
            return error

        if request.method == "POST":
            mark_notifications_read(username)

        since_id = request.args.get("since_id", type=int)
        notifications = build_notifications(username, since_id=since_id)
        latest_id = max((item["id"] for item in notifications), default=since_id or 0)
        return jsonify(
            {
                "notifications": notifications,
                "unread_count": get_unread_notification_count(username),
                "message_unread_count": get_unread_message_count(username),
                "latest_id": latest_id,
            }
        )

    @app.route("/api/feed")
    def api_feed():
        username = session.get("username")

        before_created_at = clean_single_line_text(request.args.get("before_created_at", ""), 40)
        before_id = request.args.get("before_id", type=int)
        limit = request.args.get("limit", default=20, type=int)
        return jsonify(
            get_feed_page(
                username,
                limit=limit,
                before_created_at=before_created_at or None,
                before_id=before_id,
            )
        )

    @app.route("/api/posts/<int:post_id>")
    def api_post_detail(post_id):
        username = session.get("username")

        post = get_post(post_id, viewer_username=username)
        if not post:
            return jsonify({"error": "게시물을 찾을 수 없어요."}), 404
        return jsonify({"post": post})

    @app.route("/api/messages")
    def api_messages():
        username, error = login_required_json()
        if error:
            return error

        mark_read = request.args.get("mark_read") == "1"
        partner_username = clean_single_line_text(request.args.get("partner", ""), 80)
        threads = build_message_threads(
            get_user_profile(username),
            mark_read=mark_read,
            partner_to_mark=partner_username or None,
        )
        return jsonify({"threads": threads, "unread_count": get_unread_message_count(username)})

    @app.route("/api/messages/tone-preview", methods=["POST"])
    def api_message_tone_preview():
        username, error = login_required_json()
        if error:
            return error

        payload = request.get_json(silent=True) or {}
        target_username = clean_single_line_text(payload.get("partner", ""), 80)
        body = clean_single_line_text(payload.get("body", ""), 120)
        if not body:
            return jsonify({"suggestions": []})

        with get_db_connection() as conn:
            if target_username and not can_message_user(conn, username, target_username):
                return jsonify({"error": "팔로우한 친구에게만 메시지를 보낼 수 있습니다."}), 403

        return jsonify({"suggestions": suggest_message_tones(get_user_profile(username), body)})

    @app.route("/api/messages/<target_username>", methods=["GET", "POST"])
    def api_send_message(target_username):
        username, error = login_required_json()
        if error:
            return error

        target_username = clean_single_line_text(target_username, 80)
        if request.method == "GET":
            messages = get_conversation_messages(
                username,
                target_username,
                limit=request.args.get("limit", default=20, type=int),
                mark_read=request.args.get("mark_read") == "1",
            )
            if messages is None:
                return jsonify({"error": "이 친구와 대화할 수 없습니다."}), 403
            return jsonify(
                {
                    "messages": messages,
                    "unread_count": get_unread_message_count(username),
                }
            )

        payload = request.get_json(silent=True) or {}
        body = clean_multi_line_text(payload.get("body", ""), 500)
        if not body:
            return jsonify({"error": "메시지 내용을 입력해 주세요."}), 400

        profile = get_user_profile(username)
        with get_db_connection() as conn:
            if not can_message_user(conn, username, target_username):
                return jsonify({"error": "팔로우한 친구에게만 메시지를 보낼 수 있습니다."}), 403

            cursor = conn.execute(
                """
                INSERT INTO messages (sender_username, receiver_username, body)
                VALUES (?, ?, ?)
                """,
                (username, target_username, body),
            )
            create_notification(
                conn,
                target_username,
                username,
                "message",
                f"{profile['pet_name']}의 새 메시지",
                body,
                "/",
            )
            conn.commit()

            row = conn.execute(
                """
                SELECT id, sender_username, receiver_username, body, created_at
                FROM messages
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()

        return jsonify(
            {
                "success": True,
                "message": {
                    "id": row["id"],
                    "sender": row["sender_username"],
                    "receiver": row["receiver_username"],
                    "body": row["body"],
                    "created_at": row["created_at"],
                    "is_me": True,
                },
            }
        )
