import logging
import os
import sys
import time
from pathlib import Path

from flask import Flask, g, request, session

from config import BASE_DIR, UPLOAD_FOLDER
import db
import upload_utils
from persona import PERSONA_QUESTIONS, enrich_profile, persona_defaults
from runtime_metrics import get_process_memory_mb
from routes.api import register_api_routes
from routes.auth import register_auth_routes
from routes.pages import register_page_routes
from routes.posts import register_post_routes
from routes.social import register_social_routes


TEXT_RESPONSE_MIMETYPES = {
    "application/javascript",
    "application/json",
    "text/css",
    "text/html",
    "text/javascript",
    "text/plain",
}


def should_log_request_memory():
    if os.environ.get("REQUEST_MEMORY_LOG", "0") != "1":
        return False
    return request.endpoint not in {"static", "api_notifications"}


def configure_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    log_path = BASE_DIR / "server.log"
    has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and Path(getattr(handler, "baseFilename", "")).resolve() == log_path.resolve()
        for handler in root_logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    if not has_stream_handler:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)


def build_persona_options():
    options = []
    combinations = [
        ("outdoor", "social", "snack"),
        ("outdoor", "social", "play"),
        ("outdoor", "selective", "snack"),
        ("outdoor", "selective", "play"),
        ("indoor", "social", "snack"),
        ("indoor", "social", "play"),
        ("indoor", "selective", "snack"),
        ("indoor", "selective", "play"),
        ("spotlight", "social", "snack"),
        ("spotlight", "social", "play"),
        ("zen", "social", "snack"),
        ("zen", "social", "play"),
    ]

    for energy, social, focus in combinations:
        answers = persona_defaults()
        answers.update(
            {
                "persona_energy": energy,
                "persona_social": social,
                "persona_focus": focus,
            }
        )
        profile = enrich_profile(
            {
                "username": "sample",
                "pet_name": "샘플",
                "pet_species": "강아지",
                "pet_age": 1,
                "activity_level": "보통",
                "pet_likes": "간식",
                "pet_dislikes": "목욕",
                "avatar_url": "",
                "bio": "",
                "status_message": "",
                "favorite_place": "",
                "personality": "",
                "owner_persona_note": "",
                **answers,
            }
        )
        options.append(profile["persona"])
    return options


def create_app(database_path=None, upload_folder=None, testing=False):
    configure_logging()

    if database_path is not None:
        db.DATABASE_PATH = Path(database_path).resolve()

    active_upload_folder = Path(upload_folder).resolve() if upload_folder is not None else UPLOAD_FOLDER
    upload_utils.UPLOAD_FOLDER = active_upload_folder

    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "zooingong_secret_key_123")
    app.config["UPLOAD_FOLDER"] = str(active_upload_folder)
    app.config["TESTING"] = testing
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
    app.json.ensure_ascii = False

    active_upload_folder.mkdir(parents=True, exist_ok=True)
    db.init_db()

    persona_options = build_persona_options()

    @app.context_processor
    def inject_globals():
        return {
            "persona_questions": PERSONA_QUESTIONS,
            "persona_options": persona_options,
        }

    @app.before_request
    def record_request_start():
        g.request_started_at = time.perf_counter()
        g.request_started_memory_mb = get_process_memory_mb()

    @app.after_request
    def finalize_response(response):
        if response.mimetype in TEXT_RESPONSE_MIMETYPES and "charset=" not in response.content_type.lower():
            response.headers["Content-Type"] = f"{response.mimetype}; charset=utf-8"

        if should_log_request_memory():
            started_at = getattr(g, "request_started_at", None)
            started_memory_mb = getattr(g, "request_started_memory_mb", None)
            current_memory_mb = get_process_memory_mb()
            elapsed_ms = (time.perf_counter() - started_at) * 1000 if started_at else 0
            memory_delta_mb = (
                current_memory_mb - started_memory_mb
                if current_memory_mb is not None and started_memory_mb is not None
                else None
            )
            logging.getLogger("request_memory").info(
                "request method=%s path=%s endpoint=%s status=%s elapsed_ms=%.1f user=%s memory_mb=%s memory_delta_mb=%s",
                request.method,
                request.path,
                request.endpoint or "",
                response.status_code,
                elapsed_ms,
                session.get("username", "-"),
                f"{current_memory_mb:.1f}" if current_memory_mb is not None else "unknown",
                f"{memory_delta_mb:+.1f}" if memory_delta_mb is not None else "unknown",
            )
        return response

    register_auth_routes(app)
    register_page_routes(app)
    register_post_routes(app)
    register_social_routes(app)
    register_api_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
