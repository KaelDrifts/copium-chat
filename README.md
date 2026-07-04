# COPIUM 🐸 — crypto twitter chat terminal

Terminal-styled chat assistant that talks like a crypto twitter degen. Flask + Groq backend (free), vanilla HTML/JS frontend.

> COPIUM does not give financial advice, does not predict prices and does not execute trades. Vibes only.

## 1. Get a free API key

1. Go to [console.groq.com](https://console.groq.com) and create an account (free, no credit card).
2. Go to **API Keys** → **Create API Key**.
3. Copy the key (starts with `gsk_...`).

## 2. Run the project

```bash
pip install -r requirements.txt
python app.py
```

Put your key in a `.env` file in the project root:

```
GROQ_API_KEY=gsk_your_key_here
```

(or `export GROQ_API_KEY=gsk_your_key_here` before running).

Open [http://localhost:5001](http://localhost:5001) and that's it. gm.

> Note: port 5001 is used because on macOS port 5000 is usually taken by AirPlay Receiver.
