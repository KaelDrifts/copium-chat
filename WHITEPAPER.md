# HOOPIUM — Whitepaper

**A terminal-styled Solana token risk scanner with an opinion.**

*v1.0 — July 2026*

---

## Abstract

Every day thousands of tokens launch on Solana. Most of them are rugs, honeypots, dead clones or forgotten experiments. The information needed to tell them apart is public — mint authorities, holder distributions, liquidity depth, bonding curve state — but it's scattered across half a dozen tools, and by the time a trader has cross-checked all of them, the trade is gone.

HOOPIUM compresses that whole due-diligence loop into one action: **paste a contract address, get a risk report in seconds.** Hard data, red flags, a 0–100 score, how similar tokens ended up, whether the coin's narrative fits the current market meta, and a blunt automated gut take — all in one terminal window, or one click from your browser toolbar.

HOOPIUM never gives financial advice. It gives you the facts, the flags and an automated opinion, clearly labeled as such. DYOR, always.

---

## The problem

Memecoin trading on Solana is an information race with asymmetric stakes:

- **Deployers know everything** — they control the mint, the liquidity and the narrative.
- **Buyers know almost nothing** — a ticker, a chart, and whatever the deployer wrote in the description.

The data to level that asymmetry exists and is free. But checking a single token properly means visiting DexScreener for market structure, a Solana explorer for authorities and holders, pump.fun for bonding curve state, and RugCheck for a second opinion — four tabs, four mental models, several minutes. In the trenches, several minutes is the whole trade.

## What HOOPIUM does

HOOPIUM runs the full checklist automatically on every scan:

**1. Market structure.** Price, market cap, 24h volume, pair age and liquidity summed across every pool where the token trades. Thin liquidity against a big market cap is the classic setup for a rug or brutal slippage — HOOPIUM flags the ratio explicitly.

**2. On-chain permissions.** Whether the mint authority and freeze authority are renounced. An active mint authority means the dev can print unlimited supply; an active freeze authority means your tokens can be frozen the moment you buy. Both are instant red flags.

**3. Holder concentration.** What percentage of supply the top 10 accounts control (liquidity pools and bonding curve accounts included, and noted as such).

**4. Launch-platform state.** For pump.fun tokens: bonding curve progress, or whether the token already graduated to Raydium.

**5. Cross-reference.** RugCheck's independent risk score and flagged risks, plus 3–5 similar-named tokens from DexScreener — because most launches are clones, and seeing how the clones ended is often the fastest signal.

**6. Meta fit.** HOOPIUM pulls the tokens currently live and trending on pump.fun — a real-time snapshot of the market meta — and judges whether the scanned coin's lore and narrative fit what's running right now. A clean token in a dead meta is still a bad trade; in the trenches, timing the meta is half the game.

## The HOOPIUM Score

Every scan produces a **0–100 score** (100 = cleanest) computed by ML and countless hours of pattern recognition over the trenches. These are the signals the model weighs, and their typical impact:

| Signal | Typical impact |
|---|---|
| Token already marked as rugged | −60 |
| Mint authority active | −25 |
| Freeze authority active | −25 |
| Top-10 holders ≥ 80% / ≥ 50% / ≥ 30% | −30 / −20 / −10 |
| Liquidity under $1k | −30 |
| Liquidity < 2% / < 5% of market cap | −20 / −10 |
| 24h volume ≈ dead (< 1% of mcap or < $100) | −10 |
| Pair younger than 1 day | −10 |
| Still on bonding curve | −5 |
| Elevated third-party risk score | −10 |
| On-chain data unverifiable | −10 |

Two or more hard red flags cap the score at 35; one caps it at 65 — the number can never disagree with the flags. The score maps to a risk level: **≥ 70 LOW, 40–69 MEDIUM, < 40 HIGH**, and is always the last line of the report.

## Your rules, your verdict

The score is HOOPIUM's opinion. The second verdict is **yours**.

Users define their own buy rules over every scanned metric — market cap, liquidity, liquidity/mcap ratio, volume, pair age, holder concentration, total holders, bonding curve progress, the HOOPIUM score itself, authority status — either with a simple *metric / operator / threshold* builder, or by **describing their criteria in plain english and letting the AI compile them into a setup**: a named set of conditions a coin must comply with to be tradable or get a score.

```
> "at least $50k liquidity, 500+ holders, top 10 under 25%, mint renounced"
⚙ degen scalp — 4 conditions
  ✓ liquidity >= $50,000
  ✓ total holders >= 500
  ✓ top 10 holders <= 25%
  ✓ mint authority renounced
```

Setups are named, editable and can be toggled on and off at any time. Rules and setups are stored client-side and evaluated on every scan, producing an instant **WOULD BUY / WOULD NOT BUY** verdict before the report even renders. Conditions that reference unavailable data return UNKNOWN and never count as passing: missing information is treated as risk, not as a pass.

## The report

A language model turns the pre-computed analysis into a readable, terminal-styled report — but it works under strict constraints: it can only restate the numbers, flags and verdicts it was handed. It never invents data, never overrides a rule verdict, never predicts prices. Structure:

1. **HARD DATA** — the numbers.
2. **RED FLAGS** — worst first.
3. **COMPARABLES** — how the lookalikes are doing.
4. **META FIT** — the current meta and whether this coin's narrative belongs in it.
5. **YOUR RULES** — your criteria, your verdict.
6. **GUT TAKE** — would HOOPIUM ape or not, always labeled as an automated opinion, never financial advice.
7. **HOOPIUM SCORE** — `X/100 — RISK: LEVEL`.

If the language model is unavailable, the raw computed scan is returned instead. The analysis never depends on the writer.

## The Chrome extension

The scanner also ships as a **Chrome extension**: a mini HOOPIUM terminal in the browser toolbar. Copy a CA on Axiom, Photon, BullX, DexScreener or pump.fun and scan it without switching tabs — or select the address on any page, right click, **"Scan with HOOPIUM"**, and the popup opens with the report already loading. Buy rules work identically in the popup, so the WOULD BUY / WOULD NOT BUY verdict lands mid-trade, in seconds.

## Architecture & trust model

- **Self-hosted.** HOOPIUM runs locally: a lightweight Flask backend and a vanilla HTML/JS frontend. Your scans and your rules never touch a third-party HOOPIUM server, because there isn't one.
- **Free public data only.** DexScreener, public Solana RPC, pump.fun and RugCheck. No paid APIs, no API keys for data, no trackers.
- **No sign-up, no wallet.** Open the terminal, paste a CA, scan. Nothing to connect, nothing to sign, nothing custodied.
- **ML core.** Every flag and every point of the score comes from a model trained through countless hours of pattern recognition over rugs and survivors alike. The language model only writes prose.
- **One-click distribution.** The Chrome extension is served directly by the scanner itself (`/download/hoopium-extension.zip`) — no external downloads.

## What HOOPIUM is not

HOOPIUM does not give financial advice, does not predict prices, does not execute trades and does not custody anything. Public data can be wrong, stale or gamed; renounced authorities and clean distributions do not make a token safe. The gut take is an automated opinion produced by the model. **Nothing in HOOPIUM is a reason to buy a token. DYOR, ser.**

## Roadmap

- **More signals**: LP lock/burn detection, deployer wallet history, insider network graphs.
- **Meta engine**: richer meta detection across launchpads beyond pump.fun.
- **Rule sharing**: import/export rule sets, so communities can publish their buy criteria.
- **Packaged distribution**: one-click install for the extension and a hosted demo.

---

*HOOPIUM © 2026 — built with flask, groq, dexscreener, rugcheck and pure hoopium. Not financial advice. Ever.*
