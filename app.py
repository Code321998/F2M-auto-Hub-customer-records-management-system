"""F2M Auto-Hub Flask backend.

Serves the existing front-end (index.html, style.css, app.js) exactly as it
looks today and stores all records in a local SQLite database (records.db)
so they are shared by every browser that connects to this server.

Run:  python app.py   then open http://127.0.0.1:5000
"""
import json
import os
import sqlite3

from flask import Flask, abort, jsonify, request, send_from_directory, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# On Render, set DATABASE_PATH to a path on a persistent disk (e.g.
# /data/records.db) to keep records across deploys. Defaults to records.db
# next to this file.
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "records.db"))

# Must match the section keys used by the front-end (app.js "configs").
SECTIONS = ["customers", "vehicles", "appointments", "requests",
            "history", "feedback", "notifications", "visits"]

# Demo credentials shown on the login screen. Replace with hashed
# passwords in a real deployment.
USERS = {"admin": "admin123"}

app = Flask(__name__, static_folder=None)
# Set SECRET_KEY in the Render dashboard for stable sessions across restarts.
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

STATIC_FILES = {"index.html", "style.css", "app.js"}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS records (
                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                   section    TEXT NOT NULL,
                   data       TEXT NOT NULL,
                   created_at TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )


def row_to_record(row):
    record = json.loads(row["data"])
    record["id"] = row["id"]
    return record


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    if filename not in STATIC_FILES:
        abort(404)
    return send_from_directory(BASE_DIR, filename)


@app.route("/healthz")
def health():
    # Health check used by Render (see healthCheckPath in render.yaml).
    return jsonify(ok=True)


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if USERS.get(username) == password:
        session["user"] = username
        return jsonify(ok=True)
    return jsonify(error="Incorrect username or password."), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(ok=True)


@app.route("/api/records", methods=["GET"])
def list_records():
    if not session.get("user"):
        return jsonify(error="Not signed in."), 401
    result = {section: [] for section in SECTIONS}
    with db() as conn:
        rows = conn.execute("SELECT * FROM records ORDER BY id DESC").fetchall()
    for row in rows:
        if row["section"] in result:
            result[row["section"]].append(row_to_record(row))
    return jsonify(result)


@app.route("/api/records/<section>", methods=["POST"])
def create_record(section):
    if not session.get("user"):
        return jsonify(error="Not signed in."), 401
    if section not in SECTIONS:
        abort(404)
    payload = request.get_json(silent=True) or {}
    payload.pop("id", None)
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO records (section, data) VALUES (?, ?)",
            (section, json.dumps(payload)),
        )
        record_id = cursor.lastrowid
    return jsonify({**payload, "id": record_id}), 201


@app.route("/api/records/<section>/<int:record_id>", methods=["DELETE"])
def delete_record(section, record_id):
    if not session.get("user"):
        return jsonify(error="Not signed in."), 401
    with db() as conn:
        conn.execute("DELETE FROM records WHERE id = ? AND section = ?",
                     (record_id, section))
    return jsonify(ok=True)


init_db()

if __name__ == "__main__":
    # Local development entry point. On Render the service is started with
    # gunicorn (see render.yaml), which binds to 0.0.0.0:$PORT automatically.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
