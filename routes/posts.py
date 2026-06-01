from html import escape
import gc
import logging
import os
from threading import BoundedSemaphore, Thread
import time

from flask import jsonify, request

from caption_ai import (
    generate_caption,
    is_supported_image_file,
    make_fallback_caption,
    sanitize_caption_text,
)
from comment_ai import generate_comment_suggestion
from db import get_db_connection
from runtime_metrics import get_process_memory_mb
from services import build_comment_item, create_notification, get_post, get_user_profile
from text_utils import clean_multi_line_text, clean_single_line_text
from upload_utils import remove_upload_file_if_unused, store_uploaded_file
from routes.utils import login_required_json


logger = logging.getLogger(__name__)
PENDING_CAPTION_TEXT = "AI 캡션을 만들고 있어요..."
PENDING_CAPTION_HTML = escape(PENDING_CAPTION_TEXT)
CAPTION_WORKER_CONCURRENCY = max(1, int(os.environ.get("CAPTION_WORKER_CONCURRENCY", "1")))
_caption_worker_semaphore = BoundedSemaphore(CAPTION_WORKER_CONCURRENCY)


def _timed_call(label, callback, *args, **kwargs):
    started_at = time.perf_counter()
    try:
        return callback(*args, **kwargs)
    finally:
        logger.info("AI timing %s elapsed=%.2fs", label, time.perf_counter() - started_at)


def generate_caption_without_image_judgement(filepath, profile, activity_text):
    started_at = time.perf_counter()
    analysis = {"allow": True, "confidence": "skipped", "scene": "", "reason": "image judgement skipped"}
    caption = _timed_call("caption_generation", generate_caption, filepath, profile, activity_text, analysis)
    if not caption:
        caption = escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")
    logger.info("AI timing caption_total elapsed=%.2fs image_judgement=skipped", time.perf_counter() - started_at)
    return analysis, caption


def get_post_payload(post_id, username):
    return get_post(post_id, viewer_username=username)


def finish_pending_caption(post_id, filepath, profile, activity_text):
    started_at = time.perf_counter()
    started_memory_mb = get_process_memory_mb()
    try:
        with _caption_worker_semaphore:
            analysis, caption = generate_caption_without_image_judgement(filepath, profile, activity_text)
        caption_status = "ready"
        if not caption:
            caption = escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")
            caption_status = "fallback"
    except Exception:
        logger.exception("AI caption background generation failed post_id=%s", post_id)
        caption = escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")
        caption_status = "fallback"

    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE posts
            SET caption = ?, caption_status = ?
            WHERE id = ? AND caption_status = 'pending'
            """,
            (caption, caption_status, post_id),
        )
        conn.commit()

    current_memory_mb = get_process_memory_mb()
    memory_delta_mb = (
        current_memory_mb - started_memory_mb
        if current_memory_mb is not None and started_memory_mb is not None
        else None
    )
    logger.info(
        "caption_worker post_id=%s status=%s elapsed=%.2fs memory_mb=%s memory_delta_mb=%s",
        post_id,
        caption_status,
        time.perf_counter() - started_at,
        f"{current_memory_mb:.1f}" if current_memory_mb is not None else "unknown",
        f"{memory_delta_mb:+.1f}" if memory_delta_mb is not None else "unknown",
    )
    gc.collect()


def start_pending_caption(app, post_id, filepath, profile, activity_text):
    if app.config.get("TESTING"):
        finish_pending_caption(post_id, filepath, profile, activity_text)
        return

    worker = Thread(
        target=finish_pending_caption,
        args=(post_id, filepath, profile, activity_text),
        daemon=True,
    )
    worker.start()


def register_post_routes(app):
    @app.route("/upload", methods=["POST"])
    def upload_file():
        username, error = login_required_json()
        if error:
            return error

        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"error": "업로드할 이미지를 선택해 주세요."}), 400

        activity_text = clean_multi_line_text(request.form.get("activity_text", ""), 320)
        if not activity_text:
            return jsonify({"error": "오늘 무엇을 했는지 활동 내용을 적어주세요."}), 400
        caption_override = clean_multi_line_text(request.form.get("caption_override", ""), 700)

        filepath, image_url = store_uploaded_file(file)

        if not is_supported_image_file(filepath):
            try:
                filepath.unlink(missing_ok=True)
            except OSError:
                pass
            return jsonify({"error": "이미지 파일만 업로드할 수 있어요."}), 400

        profile = get_user_profile(username)
        if caption_override:
            analysis = {"scene": ""}
            caption_text = sanitize_caption_text(caption_override)
            caption = escape(caption_text).replace("\n", "<br>") if caption_text else ""
            caption_status = "ready"
            if not caption:
                caption = escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")
                caption_status = "fallback"
        else:
            caption = PENDING_CAPTION_HTML
            caption_status = "pending"

        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO posts (image_url, caption, caption_status, username, activity_text, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (image_url, caption, caption_status, username, activity_text),
            )
            post_id = cursor.lastrowid
            conn.commit()

        if caption_status == "pending":
            start_pending_caption(app, post_id, filepath, profile, activity_text)

        post = get_post_payload(post_id, username)
        return jsonify(
            {
                "success": True,
                "post": post,
                "caption_pending": bool(post and post.get("caption_pending")),
            }
        )

    @app.route("/api/caption-preview", methods=["POST"])
    def caption_preview():
        username, error = login_required_json()
        if error:
            return error

        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"error": "캡션을 만들 사진을 선택해 주세요."}), 400

        activity_text = clean_multi_line_text(request.form.get("activity_text", ""), 320)
        if not activity_text:
            return jsonify({"error": "오늘 무엇을 했는지 활동 내용을 적어주세요."}), 400

        filepath, _image_url = store_uploaded_file(file, "preview")

        try:
            if not is_supported_image_file(filepath):
                return jsonify({"error": "이미지 파일만 업로드할 수 있어요."}), 400

            profile = get_user_profile(username)
            analysis, caption = generate_caption_without_image_judgement(filepath, profile, activity_text)

            caption_text = sanitize_caption_text(caption.replace("<br>", "\n")) if caption else ""
            if not caption_text:
                caption_text = make_fallback_caption(profile, activity_text)
                caption = escape(caption_text).replace("\n", "<br>")

            return jsonify({"success": True, "caption": caption, "caption_text": caption_text})
        finally:
            try:
                filepath.unlink(missing_ok=True)
            except OSError:
                pass

    @app.route("/like/<int:post_id>", methods=["POST"])
    def like_post(post_id):
        username, error = login_required_json()
        if error:
            return error

        profile = get_user_profile(username)
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT p.id, p.likes, p.username, u.pet_name
                FROM posts p
                LEFT JOIN users u ON u.username = p.username
                WHERE p.id = ?
                """,
                (post_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "게시물을 찾을 수 없어요."}), 404

            existing_like = conn.execute(
                """
                SELECT 1
                FROM post_likes
                WHERE post_id = ? AND username = ?
                """,
                (post_id, username),
            ).fetchone()
            if existing_like:
                conn.execute("DELETE FROM post_likes WHERE post_id = ? AND username = ?", (post_id, username))
                conn.execute("UPDATE posts SET likes = MAX(likes - 1, 0) WHERE id = ?", (post_id,))
                liked = False
            else:
                conn.execute("INSERT INTO post_likes (post_id, username) VALUES (?, ?)", (post_id, username))
                conn.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
                liked = True
                create_notification(
                    conn,
                    row["username"],
                    username,
                    "like",
                    f"{profile['pet_name']}이 좋아요를 눌렀어요",
                    f"{row['pet_name'] or row['username']}의 게시물에 킁킁 반응을 남겼어요.",
                    f"/#post-{post_id}",
                )
            row = conn.execute("SELECT likes FROM posts WHERE id = ?", (post_id,)).fetchone()
            conn.commit()
        return jsonify({"likes": row["likes"] if row else 0, "liked": liked})

    @app.route("/comment/<int:post_id>", methods=["POST"])
    def add_comment(post_id):
        username, error = login_required_json()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        content = clean_single_line_text(data.get("content", ""), 180)
        if not content:
            return jsonify({"error": "댓글 내용을 입력해 주세요."}), 400

        profile = get_user_profile(username)
        safe_comment = f"<b>{escape(profile['pet_name'])}</b> {escape(content)}"

        with get_db_connection() as conn:
            row = conn.execute("SELECT username FROM posts WHERE id = ?", (post_id,)).fetchone()
            if not row:
                return jsonify({"error": "게시물을 찾을 수 없어요."}), 404

            cursor = conn.execute(
                """
                INSERT INTO comments (post_id, content, username, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (post_id, safe_comment, username),
            )
            if row:
                create_notification(
                    conn,
                    row["username"],
                    username,
                    "comment",
                    f"{profile['pet_name']}이 댓글을 남겼어요",
                    content,
                    f"/#post-{post_id}",
                )
            conn.commit()
            comment_row = conn.execute(
                """
                SELECT id, post_id, content, username, created_at
                FROM comments
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()

        return jsonify({"success": True, "comment": build_comment_item(comment_row, username)})

    @app.route("/api/comments/<int:comment_id>", methods=["PATCH"])
    def update_comment(comment_id):
        username, error = login_required_json()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        content = clean_single_line_text(data.get("content", ""), 180)
        if not content:
            return jsonify({"error": "댓글 내용을 입력해 주세요."}), 400

        profile = get_user_profile(username)
        safe_comment = f"<b>{escape(profile['pet_name'])}</b> {escape(content)}"

        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT id, post_id, content, username, created_at
                FROM comments
                WHERE id = ?
                """,
                (comment_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "댓글을 찾을 수 없어요."}), 404
            if row["username"] != username:
                return jsonify({"error": "내 댓글만 수정할 수 있어요."}), 403

            conn.execute("UPDATE comments SET content = ? WHERE id = ?", (safe_comment, comment_id))
            conn.commit()
            updated = conn.execute(
                """
                SELECT id, post_id, content, username, created_at
                FROM comments
                WHERE id = ?
                """,
                (comment_id,),
            ).fetchone()

        return jsonify({"success": True, "comment": build_comment_item(updated, username)})

    @app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
    def delete_comment(comment_id):
        username, error = login_required_json()
        if error:
            return error

        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT id, post_id, username
                FROM comments
                WHERE id = ?
                """,
                (comment_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "댓글을 찾을 수 없어요."}), 404
            if row["username"] != username:
                return jsonify({"error": "내 댓글만 삭제할 수 있어요."}), 403

            conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
            conn.commit()

        return jsonify({"success": True, "post_id": row["post_id"], "comment_id": comment_id})

    @app.route("/api/comment-suggestion/<int:post_id>", methods=["POST"])
    def comment_suggestion(post_id):
        username, error = login_required_json()
        if error:
            return error

        post = get_post(post_id, viewer_username=username)
        if not post:
            return jsonify({"error": "게시물을 찾을 수 없어요."}), 404

        viewer_profile = get_user_profile(username)
        recent_comments = [comment.get("content_text", "") for comment in post.get("comments", [])]
        comment = generate_comment_suggestion(viewer_profile, post, recent_comments)
        comment = clean_single_line_text(comment, 60)
        if not comment:
            return jsonify({"error": "댓글을 만들지 못했어요."}), 500

        return jsonify({"success": True, "comment": comment})

    @app.route("/post/<int:post_id>", methods=["PATCH"])
    def update_post(post_id):
        username, error = login_required_json()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        caption_text = clean_multi_line_text(data.get("caption", ""), 700)
        if not caption_text:
            return jsonify({"error": "수정할 캡션 내용을 입력해 주세요."}), 400

        safe_caption = escape(caption_text).replace("\n", "<br>")
        with get_db_connection() as conn:
            row = conn.execute("SELECT username FROM posts WHERE id = ?", (post_id,)).fetchone()
            if not row:
                return jsonify({"error": "게시물을 찾을 수 없어요."}), 404
            if row["username"] != username:
                return jsonify({"error": "내 게시물만 수정할 수 있어요."}), 403

            conn.execute(
                "UPDATE posts SET caption = ?, caption_status = 'ready' WHERE id = ?",
                (safe_caption, post_id),
            )
            conn.commit()

        return jsonify({"success": True, "caption": safe_caption, "caption_text": caption_text})

    @app.route("/post/<int:post_id>", methods=["DELETE"])
    def delete_post(post_id):
        username, error = login_required_json()
        if error:
            return error

        with get_db_connection() as conn:
            row = conn.execute("SELECT username, image_url FROM posts WHERE id = ?", (post_id,)).fetchone()
            if not row:
                return jsonify({"error": "게시물을 찾을 수 없어요."}), 404
            if row["username"] != username:
                return jsonify({"error": "내 게시물만 삭제할 수 있어요."}), 403

            image_url = row["image_url"]
            conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
            conn.execute("DELETE FROM post_likes WHERE post_id = ?", (post_id,))
            conn.execute("DELETE FROM post_bookmarks WHERE post_id = ?", (post_id,))
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            still_used = conn.execute("SELECT 1 FROM posts WHERE image_url = ? LIMIT 1", (image_url,)).fetchone()
            conn.commit()

        remove_upload_file_if_unused(image_url, bool(still_used))
        return jsonify({"success": True})

    @app.route("/bookmark/<int:post_id>", methods=["POST"])
    def bookmark_post(post_id):
        username, error = login_required_json()
        if error:
            return error

        with get_db_connection() as conn:
            post = conn.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
            if not post:
                return jsonify({"error": "게시물을 찾을 수 없어요."}), 404

            existing = conn.execute(
                """
                SELECT 1
                FROM post_bookmarks
                WHERE post_id = ? AND username = ?
                """,
                (post_id, username),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM post_bookmarks WHERE post_id = ? AND username = ?", (post_id, username))
                bookmarked = False
            else:
                conn.execute("INSERT INTO post_bookmarks (post_id, username) VALUES (?, ?)", (post_id, username))
                bookmarked = True

            row = conn.execute("SELECT COUNT(*) AS count FROM post_bookmarks WHERE username = ?", (username,)).fetchone()
            conn.commit()

        return jsonify({"success": True, "bookmarked": bookmarked, "bookmark_count": row["count"] if row else 0})
