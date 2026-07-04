import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

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


@app.route("/api/chat", methods=["POST"])
def chat():
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
