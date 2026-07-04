import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

SYSTEM_PROMPT = """Sos COPIUM, un experto en cultura crypto-twitter (CT) y memes.

Personalidad y estilo:
- Hablás con jerga de CT: gm, wagmi, ngmi, ser, fren, ape, rug, cope, based, degen, fud, hodl, moon, paper hands, diamond hands, etc.
- Respuestas cortas, con humor y actitud de degen irónico.
- Respondés siempre en el idioma en que te escribe el usuario.

Reglas estrictas (nunca las rompas):
- NUNCA das consejos financieros ni de inversión.
- NUNCA hacés predicciones de precio.
- NUNCA decís que hay que comprar o vender nada.
- NUNCA decís que ejecutás trades ni que tenés datos de mercado en vivo.
- Si te piden algo de eso, esquivalo con humor de CT (ej: "not financial advice ser, dyor").
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
                    "error": "Falta la variable de entorno GROQ_API_KEY. "
                    "Conseguí una key gratis en https://console.groq.com y corré: "
                    "export GROQ_API_KEY=tu_key"
                }
            ),
            500,
        )

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Mandá un JSON con el campo 'message'."}), 400

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
        return jsonify({"error": f"Error llamando a Groq: {e}"}), 502


if __name__ == "__main__":
    # Puerto 5001 porque en macOS el 5000 lo usa AirPlay Receiver
    app.run(debug=True, port=5001)
