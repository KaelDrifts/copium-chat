import os
import secrets
import time

import base58
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

load_dotenv()

app = Flask(__name__)

# Wallet auth state (in-memory: resets on server restart)
NONCES = {}  # pubkey -> (nonce, issued_at)
SESSIONS = {}  # session token -> pubkey
NONCE_TTL_SECONDS = 300

SYSTEM_PROMPT = """You are COPIUM, an expert in crypto-twitter (CT) culture and memes.

Personality and style:
- You speak in CT slang: gm, wagmi, ngmi, ser, fren, ape, rug, cope, based, degen, fud, hodl, moon, paper hands, diamond hands, etc.
- Short replies, with humor and an ironic degen attitude.
- You always reply in the same language the user writes in.

Strict rules (never break them):
- NEVER give financial or investment advice.
- NEVER make price predictions.
- NEVER tell anyone to buy or sell anything.
- NEVER claim you execute trades or have live market data.
- If asked for any of that, dodge it with CT humor (e.g. "not financial advice ser, dyor").
"""

MODEL = "llama-3.3-70b-versatile"


def get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    from groq import Groq

    return Groq(api_key=api_key)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/auth/nonce", methods=["POST"])
def auth_nonce():
    data = request.get_json(silent=True) or {}
    pubkey = (data.get("pubkey") or "").strip()
    if not pubkey:
        return jsonify({"error": "Send a JSON body with a 'pubkey' field."}), 400
    nonce = (
        "Sign this message to prove you own this wallet and unlock COPIUM.\n\n"
        "This request will NOT trigger any transaction or cost any gas.\n\n"
        f"Nonce: {secrets.token_hex(16)}"
    )
    NONCES[pubkey] = (nonce, time.time())
    return jsonify({"nonce": nonce})


@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    data = request.get_json(silent=True) or {}
    pubkey = (data.get("pubkey") or "").strip()
    signature_hex = (data.get("signature") or "").strip()
    if not pubkey or not signature_hex:
        return jsonify({"error": "Send 'pubkey' and 'signature' fields."}), 400

    entry = NONCES.get(pubkey)
    if not entry or time.time() - entry[1] > NONCE_TTL_SECONDS:
        NONCES.pop(pubkey, None)
        return jsonify({"error": "Nonce missing or expired, request a new one."}), 400

    nonce = entry[0]
    try:
        verify_key = VerifyKey(base58.b58decode(pubkey))
        verify_key.verify(nonce.encode("utf-8"), bytes.fromhex(signature_hex))
    except (BadSignatureError, ValueError):
        return jsonify({"error": "Invalid signature, ngmi."}), 401

    del NONCES[pubkey]
    token = secrets.token_hex(32)
    SESSIONS[token] = pubkey
    return jsonify({"token": token, "pubkey": pubkey})


def get_session_pubkey():
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    return SESSIONS.get(token)


@app.route("/api/chat", methods=["POST"])
def chat():
    if not get_session_pubkey():
        return (
            jsonify({"error": "Wallet not connected. Connect your Phantom wallet first, ser."}),
            401,
        )

    if not os.environ.get("GROQ_API_KEY"):
        return (
            jsonify(
                {
                    "error": "Missing GROQ_API_KEY environment variable. "
                    "Get a free key at https://console.groq.com and run: "
                    "export GROQ_API_KEY=your_key"
                }
            ),
            500,
        )

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Send a JSON body with a 'message' field."}), 400

    try:
        client = get_groq_client()
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.9,
            max_tokens=300,
        )
        reply = completion.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": f"Error calling Groq: {e}"}), 502


if __name__ == "__main__":
    # Port 5001 because on macOS port 5000 is taken by AirPlay Receiver
    app.run(debug=True, port=5001)
