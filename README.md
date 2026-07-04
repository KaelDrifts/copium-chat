# COPIUM 🐸 — crypto twitter chat terminal

Chat assistant con estética de terminal que habla como un degen de crypto twitter. Backend en Flask + Groq (gratis), frontend en HTML/JS vanilla.

> COPIUM no da consejos financieros, no predice precios y no ejecuta trades. Solo vibes.

## 1. Conseguir una API key gratis

1. Entrá a [console.groq.com](https://console.groq.com) y creá una cuenta (gratis, sin tarjeta).
2. Andá a **API Keys** → **Create API Key**.
3. Copiá la key (empieza con `gsk_...`).

## 2. Correr el proyecto

```bash
pip install -r requirements.txt
export GROQ_API_KEY=gsk_tu_key_aca
python app.py
```

Abrí [http://localhost:5001](http://localhost:5001) y listo. gm.

> Nota: se usa el puerto 5001 porque en macOS el 5000 suele estar ocupado por AirPlay Receiver.
