"""Flask web application — production-ready entry point."""
import os
import threading
import asyncio
import json
import subprocess
import sys
import time

from flask import Flask, render_template, request, jsonify, abort
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env for local development (no-op on Render where vars come from dashboard)
load_dotenv()

from chatbot.database import auth_user, init_db
from chatbot.mcp.client_sse import InteractiveBankingAssistant

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ── Optional: launch MCP server as a subprocess ──────────────────────────────
# Set LAUNCH_MCP_SERVER=true when you want a single Render service to run both.
# In the recommended two-service setup, leave this unset (default: false).
_mcp_process = None

def _start_mcp_subprocess():
    global _mcp_process
    print("[INFO] Launching MCP server subprocess...")
    _mcp_process = subprocess.Popen(
        [sys.executable, "-m", "chatbot.mcp.server_sse"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    # Wait up to 15 s for the MCP server to accept connections
    from chatbot.config import MCP_URL
    import urllib.request
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(MCP_URL.replace("/sse", "/"), timeout=2)
            break
        except Exception:
            time.sleep(1)
    print(f"[INFO] MCP subprocess pid={_mcp_process.pid}")


if os.getenv("LAUNCH_MCP_SERVER", "false").lower() == "true":
    _start_mcp_subprocess()

# ── Assistant ────────────────────────────────────────────────────────────────
assistant = InteractiveBankingAssistant()
background_loop = asyncio.new_event_loop()


def _run_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(assistant.initialize_session())
    loop.run_forever()


_bg_thread = threading.Thread(target=_run_background_loop, args=(background_loop,), daemon=True)
_bg_thread.start()

# ── JWT helpers ──────────────────────────────────────────────────────────────
def create_access_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = payload.get("sub")
        if not user:
            abort(401, "Invalid token payload")
        return user
    except jwt.ExpiredSignatureError:
        abort(401, "Token has expired")
    except jwt.InvalidTokenError:
        abort(401, "Invalid token")


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("chat.html")


@app.route("/health", methods=["GET"])
def health():
    """Health-check endpoint used by Render."""
    return jsonify({"status": "ok"}), 200


@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        abort(400, 'Missing "username" or "password"')
    if not auth_user(username, password):
        return jsonify({"status": "fail"}), 401
    token = create_access_token(username)
    return jsonify({"status": "success", "access_token": token, "token_type": "bearer"}), 200


@app.route("/chat", methods=["POST"])
def chat():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"reply": "Please login to continue."}), 401
    token = auth_header.split(" ", 1)[1]
    verify_access_token(token)

    msg = (request.json or {}).get("message", "").strip()
    if not msg:
        return jsonify({"reply": "I didn't receive any text."}), 400

    future = asyncio.run_coroutine_threadsafe(
        assistant.send_message(msg), background_loop
    )
    try:
        result = future.result(timeout=60)
    except Exception as exc:
        return jsonify({"reply": f"Internal error: {exc}"}), 500

    if isinstance(result, str):
        return jsonify({"reply": result})
    if isinstance(result, dict) and "error" in result:
        return jsonify({"reply": result["error"]})
    return jsonify({"reply": json.dumps(result, indent=2)})


# ── Local dev entry point (gunicorn is used on Render) ───────────────────────
if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=False)
