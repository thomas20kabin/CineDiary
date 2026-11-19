
import os
from datetime import date
from functools import wraps

import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)


# PostgreSQL connection
def get_db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "cinediary_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row
    )


# Protect private pages
def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access your movie diary.")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


# Public homepage movies
movies = [
    {"title": "Interstellar", "genre": "Sci-Fi", "rating": "★★★★★"},
    {"title": "Vikram", "genre": "Action", "rating": "★★★★☆"},
    {"title": "96", "genre": "Romance", "rating": "★★★★★"},
]


@app.route("/")
def home():
    # Public page: login is not required
    return render_template("home.html", movies=movies)


# Registration
@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("diary"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not 3 <= len(username) <= 50:
            flash("Username must contain 3 to 50 characters.")
            return render_template("register.html")

        if len(email) > 150 or not email:
            flash("Please enter a valid email address.")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return render_template("register.html")

        with get_db_connection() as conn:
            existing_user = conn.execute(
                """
                SELECT id
                FROM users
                WHERE username = %s OR email = %s
                """,
                (username, email)
            ).fetchone()

            if existing_user:
                flash("Username or email is already registered.")
                return render_template("register.html")

            password_hash = generate_password_hash(password)

            conn.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (username, email, password_hash)
            )

        flash("Account created successfully! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


# Login with username or email
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("diary"))

    if request.method == "POST":
        username_or_email = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db_connection() as conn:
            user = conn.execute(
                """
                SELECT id, username, email, password_hash
                FROM users
                WHERE username = %s OR email = %s
                """,
                (username_or_email, username_or_email.lower())
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            flash("Welcome to CineDiary!")
            return redirect(url_for("diary"))

        flash("Incorrect username/email or password.")

    return render_template("login.html")


# Logout
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have logged out successfully.")
    return redirect(url_for("home"))


# Personal movie diary
@app.route("/diary", methods=["GET", "POST"])
@login_required
def diary():
    user_id = session["user_id"]

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        watched_date = request.form.get("watched_date", "")
        rating = request.form.get("rating", "")
        review = request.form.get("review", "").strip()

        if not title or len(title) > 100:
            flash("Movie title is required and must be under 100 characters.")
            return redirect(url_for("diary"))

        if rating not in {"1", "2", "3", "4", "5"}:
            flash("Please choose a rating from 1 to 5.")
            return redirect(url_for("diary"))

        try:
            valid_date = date.fromisoformat(watched_date)
        except ValueError:
            flash("Please enter a valid watched date.")
            return redirect(url_for("diary"))

        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO diary_entries
                    (user_id, title, watched_date, rating, review)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, title, valid_date, int(rating), review)
            )

        flash("Movie added to your diary!")
        return redirect(url_for("diary"))

    with get_db_connection() as conn:
        entries = conn.execute(
            """
            SELECT id, title, watched_date, rating, review
            FROM diary_entries
            WHERE user_id = %s
            ORDER BY watched_date DESC, id DESC
            """,
            (user_id,)
        ).fetchall()

    return render_template("diary.html", entries=entries)


# Edit only the logged-in user's movie
@app.route("/edit/<int:entry_id>", methods=["GET", "POST"])
@login_required
def edit_movie(entry_id):
    user_id = session["user_id"]

    with get_db_connection() as conn:
        entry = conn.execute(
            """
            SELECT id, title, watched_date, rating, review
            FROM diary_entries
            WHERE id = %s AND user_id = %s
            """,
            (entry_id, user_id)
        ).fetchone()

    if entry is None:
        return "Movie entry not found", 404

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        watched_date = request.form.get("watched_date", "")
        rating = request.form.get("rating", "")
        review = request.form.get("review", "").strip()

        if not title or len(title) > 100:
            flash("Movie title is required and must be under 100 characters.")
            return redirect(url_for("edit_movie", entry_id=entry_id))

        if rating not in {"1", "2", "3", "4", "5"}:
            flash("Please choose a rating from 1 to 5.")
            return redirect(url_for("edit_movie", entry_id=entry_id))

        try:
            valid_date = date.fromisoformat(watched_date)
        except ValueError:
            flash("Please enter a valid watched date.")
            return redirect(url_for("edit_movie", entry_id=entry_id))

        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE diary_entries
                SET title = %s, watched_date = %s,
                    rating = %s, review = %s
                WHERE id = %s AND user_id = %s
                """,
                (title, valid_date, int(rating), review, entry_id, user_id)
            )

        flash("Movie updated successfully!")
        return redirect(url_for("diary"))

    return render_template("edit_movie.html", entry=entry)


# Delete only the logged-in user's movie
@app.route("/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_movie(entry_id):
    with get_db_connection() as conn:
        conn.execute(
            """
            DELETE FROM diary_entries
            WHERE id = %s AND user_id = %s
            """,
            (entry_id, session["user_id"])
        )

    flash("Movie deleted if it belonged to your diary.")
    return redirect(url_for("diary"))


# Public About page
@app.route("/about")
def about():
    return """
    <h1>About CineDiary</h1>
    <p>Your personal space for movie memories and reviews.</p>
    <a href="/">Back to Home</a>
    """


if __name__ == "__main__":
    app.run(debug=True, port=5001)
