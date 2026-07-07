# COPIUM 🐸 — solana token risk scanner

Terminal-styled scanner: paste a Solana token **contract address (CA)** in the chat and COPIUM
returns an automated risk report. Flask backend + Groq (free) for the write-up, vanilla HTML/JS frontend.

> COPIUM does not give financial advice, does not predict prices and does not execute trades.
> The "gut take" at the end of each report is an automated opinion based on simple heuristics.

## What it checks (all free APIs, no keys needed)

| Source | What it pulls |
|---|---|
| [DexScreener](https://docs.dexscreener.com/) | price, liquidity, 24h volume, market cap, pair age + 3-5 similar-named tokens as comparables |
| Solana public RPC | mint & freeze authority (renounced or not), top-10 holder concentration |
| [pump.fun](https://pump.fun) | bonding curve progress / migrated to Raydium, the token's lore/description, and the currently trending tokens (the "meta") |
| [RugCheck](https://rugcheck.xyz) | independent risk score to cross-reference |

Red flags are computed with plain if/else heuristics (active authorities, concentrated holders,
thin liquidity vs mcap, dead volume) into a **0-100 COPIUM score** (100 = cleanest) with a
LOW / MEDIUM / HIGH risk level, and the pre-computed result is handed to the LLM only to write
it up as a readable report. If Groq is down or rate-limited, the raw scan is returned instead.

The report also includes a **META FIT** section: COPIUM pulls the tokens currently live/trending
on pump.fun, summarizes what the market meta is right now, and judges whether the scanned coin's
lore/narrative fits it.

## Your own buy rules

Both the web terminal ("my buy rules" panel under the chat) and the extension popup ("my rules"
in the titlebar) let you define your own thresholds over any scanned metric — market cap,
liquidity, liquidity/mcap %, volume, pair age, top-10 holder %, total holders, RugCheck score,
bonding curve %, COPIUM score, mint/freeze renounced. Pick a metric, an operator (`>= <= > < ==`)
and a value; add as many rules as you want. They're saved in your browser and checked on every
scan, giving you an instant **WOULD BUY / WOULD NOT BUY** verdict by your own criteria — shown
before the report, next to the COPIUM score. Rules with missing data come back as UNKNOWN and
count as not passing.

You can also **code your own rule** as a free-form Python expression combining any of those metrics:

```
liquidity_usd / market_cap_usd > 0.05 and total_holders > 300
100000 <= market_cap_usd <= 5000000
not (top10_holders_pct > 40) or copium_score >= 80
```

Expressions are written in Python syntax: numbers, `+ - * / %`, comparisons (including chained),
`and / or / not` and parentheses. They're evaluated server-side with a whitelisted AST parser (no `eval`, no
function calls, no attribute access), so a broken or malicious expression just comes back as
INVALID instead of doing anything.

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

## 3. Connect your wallet

The scanner is unlocked by signing in with a Solana wallet ([Phantom](https://phantom.app)):

1. Click **connect wallet** in the nav.
2. Approve the connection and sign the login message in Phantom.

The signature only proves you own the wallet — it never triggers a transaction and costs no gas.
Sessions live in server memory, so restarting the server logs everyone out.

## 4. Scan a token

Paste any Solana token CA (base58, 32-44 chars) in the terminal, e.g. BONK:

```
DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
```

Anything that isn't a valid CA gets a reminder to paste one. External API failures and rate
limits are reported in the chat instead of breaking the request.

The public Solana RPC rate-limits aggressively (the scanner falls back to a second public RPC,
and to RugCheck's data for authorities/holders). If you have your own RPC endpoint, set it with:

```
SOLANA_RPC_URL=https://your-rpc-endpoint
```

## 5. Browser extension (scan without leaving your trading platform)

There's a Chrome extension in `extension/` with a mini terminal popup, so you can copy a CA
on Axiom/Photon/DexScreener/whatever and scan it without switching tabs:

1. Make sure the server is running (`python app.py`).
2. Open `chrome://extensions`, enable **Developer mode** (top right).
3. Click **Load unpacked** and pick the `extension/` folder.
4. Pin COPIUM to the toolbar. Click it, paste a CA, hit **scan**.

Bonus: select a CA on any page → right click → **Scan "…" with COPIUM** and the popup
opens with the report already loading. The extension talks to your local server on
`localhost:5001` (endpoint `/api/scan`, no wallet needed) — nothing leaves your machine
except the calls to the free data APIs.

> Note: port 5001 is used because on macOS port 5000 is usually taken by AirPlay Receiver.
