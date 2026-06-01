import logging

from flask import redirect, render_template, session, url_for

from db import get_db_connection
from services import (
    build_daily_awards,
    build_like_ranking,
    build_message_threads,
    build_notifications,
    build_daily_mission,
    build_profile_badges,
    get_bookmarked_posts,
    get_following_profiles,
    get_following_usernames,
    get_friend_suggestions,
    get_posts,
    get_profile_stats,
    get_user_profile,
    serialize_bootstrap,
)
from text_utils import clean_single_line_text


logger = logging.getLogger(__name__)


def attach_profile_summary(profile, stats):
    profile["posts_count"] = stats["posts_count"]
    profile["total_likes"] = stats["total_likes"]
    profile["friend_count"] = stats["friend_count"]
    profile["badges"] = build_profile_badges(profile)
    return profile


def build_profile_ranking_fallback(profile, stats):
    pet_name = profile.get("pet_name") or profile.get("username") or "멍스타"
    return [
        {
            "rank": 1,
            "pet_name": pet_name,
            "username": profile.get("username") or "",
            "avatar_url": profile.get("avatar_url") or "",
            "display_avatar_url": profile.get("display_avatar_url") or "",
            "initial": profile.get("initial") or pet_name[0].upper(),
            "persona": profile.get("persona") or "오늘의 첫 주인공",
            "total_likes": stats.get("total_likes") or 0,
            "post_count": stats.get("posts_count") or 0,
            "latest_post": None,
        }
    ]


def build_page_context(page, username):
    profile = get_user_profile(username)
    stats = get_profile_stats(username)
    attach_profile_summary(profile, stats)
    notifications = build_notifications(username)
    message_threads = build_message_threads(profile)
    bootstrap = serialize_bootstrap(page, profile, notifications, message_threads)
    return profile, stats, notifications, bootstrap


def register_page_routes(app):
    @app.route("/")
    def index():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))

        profile, stats, notifications, bootstrap = build_page_context("home", username)
        posts = get_posts(viewer_username=username)
        daily_awards = build_daily_awards(username)
        like_rankings = build_like_ranking()
        if not like_rankings:
            like_rankings = build_profile_ranking_fallback(profile, stats)

        logger.info(
            "home_context user=%s posts=%s rankings=%s awards=%s notifications=%s",
            username,
            len(posts),
            len(like_rankings),
            len(daily_awards),
            len(notifications),
        )

        return render_template(
            "index.html",
            posts=posts,
            profile=profile,
            stats=stats,
            notifications=notifications,
            daily_awards=daily_awards,
            like_rankings=like_rankings,
            daily_mission=build_daily_mission(profile),
            bootstrap=bootstrap,
        )

    @app.route("/profile")
    def profile():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))
        return render_profile_page(username)

    @app.route("/profile/<target_username>")
    def public_profile(target_username):
        if not session.get("username"):
            return redirect(url_for("login"))
        return render_profile_page(clean_single_line_text(target_username, 80))

    @app.route("/friends")
    def friends():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))

        profile_data, stats, notifications, bootstrap = build_page_context("friends", username)

        return render_template(
            "friends.html",
            profile=profile_data,
            friends=get_following_profiles(username),
            suggestions=get_friend_suggestions(username),
            stats=stats,
            notifications=notifications,
            bootstrap=bootstrap,
        )

    @app.route("/studio")
    def studio():
        username = session.get("username")
        if not username:
            return redirect(url_for("login"))

        profile_data, stats, notifications, bootstrap = build_page_context("studio", username)

        return render_template(
            "studio.html",
            profile=profile_data,
            stats=stats,
            notifications=notifications,
            bootstrap=bootstrap,
        )


def render_profile_page(target_username):
    viewer_username = session.get("username")
    if not viewer_username:
        return redirect(url_for("login"))

    with get_db_connection() as conn:
        target = conn.execute(
            "SELECT username FROM users WHERE username = ?",
            (target_username,),
        ).fetchone()
        if not target:
            return redirect(url_for("index"))
        following_usernames = get_following_usernames(conn, viewer_username)

    profile_data = get_user_profile(target_username)
    viewer_profile = get_user_profile(viewer_username)
    is_owner = target_username == viewer_username
    stats = get_profile_stats(target_username)
    attach_profile_summary(profile_data, stats)
    notifications = build_notifications(viewer_username)
    message_threads = build_message_threads(viewer_profile)
    bootstrap = serialize_bootstrap("profile", viewer_profile, notifications, message_threads)

    return render_template(
        "profile.html",
        user=profile_data,
        viewer=viewer_profile,
        can_edit=is_owner,
        is_following=target_username in following_usernames,
        posts=get_posts(target_username, viewer_username=viewer_username),
        saved_posts=get_bookmarked_posts(viewer_username) if is_owner else [],
        stats=stats,
        notifications=notifications,
        bootstrap=bootstrap,
    )
