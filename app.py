import ast
import operator
import os
import re
import secrets
import time

import base58
import requests
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

MODEL = "llama-3.3-70b-versatile"

# Free public RPCs, tried in order (rate limits are aggressive; env var wins if set)
SOLANA_RPC_URLS = [
    url
    for url in [
        os.environ.get("SOLANA_RPC_URL"),
        "https://api.mainnet-beta.solana.com",
        "https://solana-rpc.publicnode.com",
    ]
    if url
]
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
PUMPFUN_COIN_URL = "https://frontend-api-v3.pump.fun/coins/{}"
PUMPFUN_LIVE_URL = "https://frontend-api-v3.pump.fun/coins/currently-live?offset=0&limit=20&includeNsfw=false"
RUGCHECK_REPORT_URL = "https://api.rugcheck.xyz/v1/tokens/{}/report"

HTTP_TIMEOUT = 10
# Browser-like UA: several of the free endpoints throttle or 403 unknown user agents
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# pump.fun bonding curves start with ~793.1M tokens (6 decimals) in real reserves
PUMPFUN_INITIAL_REAL_TOKEN_RESERVES = 793_100_000_000_000

CA_CANDIDATE_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

SYSTEM_PROMPT = """You are HOOPIUM, a Solana token risk scanner with a crypto-twitter (CT) personality.

You receive a PRE-COMPUTED risk analysis of a token (hard data, red flags, a risk score and
comparable tokens). Your only job is to write it up as a readable terminal-style report.

Format the report with these sections, in this order, using plain text headers like "== HARD DATA ==":
1. HARD DATA — price, liquidity, 24h volume, market cap, pair age, authorities, top-10 holder %, bonding curve / migration status.
2. RED FLAGS — every flag found, one per line, worst first. If none, say so.
3. COMPARABLES — how similar-named tokens are doing, and what that suggests.
4. META FIT — from the list of currently live/trending pump.fun tokens, describe in 1-2 lines
   what the current market meta is (which themes/narratives are running right now), then judge
   whether this token's lore/narrative fits that meta or not, and what that means for it.
5. YOUR RULES — ONLY if the analysis includes "USER'S OWN BUY RULES": restate each rule with
   its PASS/FAIL/UNKNOWN result and the already-computed WOULD BUY / WOULD NOT BUY verdict.
   Never change that verdict. Skip this section entirely if no user rules are present.
6. GUT TAKE — one short paragraph: would you personally ape in or not, and why. Factor in the
   meta fit. ALWAYS end this section stating clearly that this is an automated opinion based
   on heuristics, NOT financial advice.
7. HOOPIUM SCORE — the very LAST section. First line exactly in this format:
   "<score>/100 — RISK: <LOW|MEDIUM|HIGH>", then one line of justification.

Strict rules (never break them):
- ONLY use the data given to you. NEVER invent numbers, holders, flags or comparables.
- NEVER talk about data sources, APIs, or where a number came from. If a value is missing,
  just call it unavailable and move on.
- Light CT slang is fine (ser, ape, rug, dyor) but stay factual and readable.
- No price predictions, no promises of profit. The gut take is an opinion on risk, not a signal.
- Reply in English unless the analysis is clearly in another language.
"""


def get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    from groq import Groq

    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# CA detection
# ---------------------------------------------------------------------------


def extract_solana_ca(message):
    """Return the first valid Solana address (32-byte base58) found in the message."""
    for candidate in CA_CANDIDATE_RE.findall(message):
        try:
            if len(base58.b58decode(candidate)) == 32:
                return candidate
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Data sources (all free). Each returns (data_dict_or_None, error_string_or_None)
# ---------------------------------------------------------------------------


def _get_json(url, **kwargs):
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, **kwargs)
    if resp.status_code == 429:
        raise RuntimeError("rate limited (429)")
    resp.raise_for_status()
    return resp.json()


def fetch_dexscreener(ca):
    try:
        payload = _get_json(DEXSCREENER_TOKEN_URL.format(ca))
        pairs = [
            p
            for p in (payload.get("pairs") or [])
            if p.get("chainId") == "solana" and (p.get("baseToken") or {}).get("address") == ca
        ]
        if not pairs:
            return None, "DexScreener: no trading pairs found for this token"
        # Prefer pairs quoted in majors (exotic quotes often report broken USD prices),
        # then use the deepest pair as the reference market
        majors = {"SOL", "WSOL", "USDC", "USDT"}
        major_pairs = [
            p for p in pairs if ((p.get("quoteToken") or {}).get("symbol") or "").upper() in majors
        ]
        ranked = major_pairs or pairs
        best = max(ranked, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        # Liquidity and volume are spread across pools; sum them so big tokens aren't under-counted
        total_liq = sum(_to_float((p.get("liquidity") or {}).get("usd")) or 0 for p in ranked)
        total_vol = sum(_to_float((p.get("volume") or {}).get("h24")) or 0 for p in ranked)
        created_at = best.get("pairCreatedAt")
        age_days = round((time.time() - created_at / 1000) / 86400, 1) if created_at else None
        base = best.get("baseToken") or {}
        return {
            "name": base.get("name"),
            "symbol": base.get("symbol"),
            "price_usd": _to_float(best.get("priceUsd")),
            "liquidity_usd": round(total_liq, 2),
            "volume_24h_usd": round(total_vol, 2),
            "market_cap_usd": _to_float(best.get("marketCap") or best.get("fdv")),
            "price_change_24h_pct": _to_float((best.get("priceChange") or {}).get("h24")),
            "pair_age_days": age_days,
            "dex": best.get("dexId"),
        }, None
    except Exception as e:
        return None, f"DexScreener: {e}"


def _rpc_call(method, params):
    last_error = None
    for url in SOLANA_RPC_URLS:
        try:
            resp = requests.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                headers=HTTP_HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            if resp.status_code == 429:
                raise RuntimeError("rate limited (429)")
            resp.raise_for_status()
            payload = resp.json()
            if "error" in payload:
                raise RuntimeError(payload["error"].get("message", "RPC error"))
            return payload["result"]
        except Exception as e:
            last_error = e
    raise RuntimeError(f"all RPC endpoints failed, last error: {last_error}")


def fetch_onchain(ca):
    try:
        account = _rpc_call("getAccountInfo", [ca, {"encoding": "jsonParsed"}])
        value = (account or {}).get("value")
        if not value:
            return None, "Solana RPC: account not found (is this really a token mint?)"
        data = value.get("data")
        parsed = (data.get("parsed") or {}) if isinstance(data, dict) else {}
        if not isinstance(parsed, dict) or parsed.get("type") != "mint":
            return None, "Solana RPC: address is not an SPL token mint"
        info = parsed.get("info") or {}

        result = {
            "mint_authority": info.get("mintAuthority"),  # None => renounced
            "freeze_authority": info.get("freezeAuthority"),  # None => renounced
            "top10_holders_pct": None,
        }

        supply = _rpc_call("getTokenSupply", [ca])
        supply_ui = _to_float((supply.get("value") or {}).get("uiAmount"))
        largest = _rpc_call("getTokenLargestAccounts", [ca])
        accounts = (largest or {}).get("value") or []
        if supply_ui and accounts:
            top10 = sum(_to_float(a.get("uiAmount")) or 0 for a in accounts[:10])
            result["top10_holders_pct"] = round(top10 / supply_ui * 100, 1)
        return result, None
    except Exception as e:
        return None, f"Solana RPC: {e}"


def fetch_pumpfun(ca):
    try:
        coin = _get_json(PUMPFUN_COIN_URL.format(ca))
        if not isinstance(coin, dict) or not coin.get("mint"):
            return None, None  # not a pump.fun token: not an error, just no data
        migrated = bool(coin.get("complete"))
        real_reserves = coin.get("real_token_reserves")
        # The v3 API returns synthetic records for arbitrary mints; only trust it when
        # there's an actual bonding curve state (migrated, or real reserves on the curve)
        if not migrated and not real_reserves:
            return None, None
        progress_pct = None
        if not migrated and isinstance(real_reserves, (int, float)):
            progress_pct = round(
                max(0.0, min(100.0, (1 - real_reserves / PUMPFUN_INITIAL_REAL_TOKEN_RESERVES) * 100)), 1
            )
        return {
            "is_pumpfun": True,
            "migrated_to_raydium": migrated,
            "bonding_curve_pct": progress_pct,
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
            "description": (coin.get("description") or "").strip()[:300] or None,
        }, None
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None, None  # not a pump.fun token
        return None, f"pump.fun: {e}"
    except Exception as e:
        return None, f"pump.fun: {e}"


def fetch_pumpfun_trending():
    """Tokens live/trending on pump.fun right now — a snapshot of the current market meta."""
    try:
        coins = _get_json(PUMPFUN_LIVE_URL)
        if not isinstance(coins, list):
            return [], "pump.fun meta: unexpected response"
        trending = []
        for coin in coins[:20]:
            if not isinstance(coin, dict) or not coin.get("name"):
                continue
            trending.append(
                {
                    "name": coin.get("name"),
                    "symbol": coin.get("symbol"),
                    "description": (coin.get("description") or "").strip()[:100] or None,
                    "usd_market_cap": _to_float(coin.get("usd_market_cap")),
                }
            )
        return trending, None
    except Exception as e:
        return [], f"pump.fun meta: {e}"


def fetch_rugcheck(ca):
    try:
        report = _get_json(RUGCHECK_REPORT_URL.format(ca))
        risks = [
            r.get("name") for r in (report.get("risks") or []) if isinstance(r, dict) and r.get("name")
        ]
        holders = [h for h in (report.get("topHolders") or []) if isinstance(h, dict)]
        top10_pct = (
            round(min(100.0, sum(_to_float(h.get("pct")) or 0 for h in holders[:10])), 1)
            if holders
            else None
        )
        return {
            "score": report.get("score_normalised", report.get("score")),
            "risks": risks[:5],
            "rugged": bool(report.get("rugged")),
            "mint_authority": report.get("mintAuthority"),
            "freeze_authority": report.get("freezeAuthority"),
            "top10_holders_pct": top10_pct,
            "total_holders": report.get("totalHolders"),
        }, None
    except Exception as e:
        return None, f"RugCheck: {e}"


def fetch_similar_tokens(name, symbol, ca):
    query = symbol or name
    if not query:
        return [], None
    try:
        payload = _get_json(DEXSCREENER_SEARCH_URL, params={"q": query})
        similar, seen = [], set()
        for pair in payload.get("pairs") or []:
            base = pair.get("baseToken") or {}
            address = base.get("address")
            if pair.get("chainId") != "solana" or not address or address == ca or address in seen:
                continue
            seen.add(address)
            created_at = pair.get("pairCreatedAt")
            similar.append(
                {
                    "name": base.get("name"),
                    "symbol": base.get("symbol"),
                    "market_cap_usd": _to_float(pair.get("marketCap") or pair.get("fdv")),
                    "liquidity_usd": _to_float((pair.get("liquidity") or {}).get("usd")),
                    "price_change_24h_pct": _to_float((pair.get("priceChange") or {}).get("h24")),
                    "pair_age_days": round((time.time() - created_at / 1000) / 86400, 1)
                    if created_at
                    else None,
                }
            )
            if len(similar) == 5:
                break
        return similar, None
    except Exception as e:
        return [], f"DexScreener search (comparables): {e}"


def _to_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Heuristics: plain if/else, no ML
# ---------------------------------------------------------------------------


def build_risk_report(ca):
    errors = []

    dex, err = fetch_dexscreener(ca)
    if err:
        errors.append(err)
    onchain, err = fetch_onchain(ca)
    if err:
        errors.append(err)
    pump, err = fetch_pumpfun(ca)
    if err:
        errors.append(err)
    rugcheck, err = fetch_rugcheck(ca)
    if err:
        errors.append(err)

    if dex is None and onchain is None and rugcheck is None:
        return None, errors

    # RPC data missing (public endpoints throttle hard)? Backfill from RugCheck's report
    if rugcheck:
        if onchain is None:
            onchain = {
                "mint_authority": rugcheck.get("mint_authority"),
                "freeze_authority": rugcheck.get("freeze_authority"),
                "top10_holders_pct": rugcheck.get("top10_holders_pct"),
                "source": "RugCheck (Solana RPC unavailable)",
            }
        elif onchain.get("top10_holders_pct") is None:
            onchain["top10_holders_pct"] = rugcheck.get("top10_holders_pct")

    similar, err = fetch_similar_tokens(
        (dex or {}).get("name"), (dex or {}).get("symbol"), ca
    )
    if err:
        errors.append(err)

    trending, err = fetch_pumpfun_trending()
    if err:
        errors.append(err)

    narrative = {
        "name": (pump or {}).get("name") or (dex or {}).get("name"),
        "symbol": (pump or {}).get("symbol") or (dex or {}).get("symbol"),
        "description": (pump or {}).get("description"),
    }

    red_flags, warnings = [], []

    if rugcheck and rugcheck.get("rugged"):
        red_flags.append("RugCheck marks this token as ALREADY RUGGED.")

    if onchain:
        if onchain["mint_authority"]:
            red_flags.append("Mint authority is ACTIVE — the dev can print unlimited new tokens.")
        if onchain["freeze_authority"]:
            red_flags.append("Freeze authority is ACTIVE — the dev can freeze holders' tokens (honeypot risk).")
        top10 = onchain.get("top10_holders_pct")
        if top10 is not None:
            if top10 >= 50:
                red_flags.append(
                    f"Top 10 accounts hold {top10}% of supply — extremely concentrated "
                    "(note: this includes liquidity pools/bonding curve accounts)."
                )
            elif top10 >= 30:
                warnings.append(
                    f"Top 10 accounts hold {top10}% of supply — somewhat concentrated "
                    "(includes liquidity pools/bonding curve accounts)."
                )

    if dex:
        liq = dex.get("liquidity_usd")
        mcap = dex.get("market_cap_usd")
        vol = dex.get("volume_24h_usd")
        age = dex.get("pair_age_days")
        if liq is not None and liq < 1_000:
            red_flags.append(f"Near-zero liquidity (${liq:,.0f}) — you may not be able to sell.")
        elif liq is not None and mcap:
            ratio = liq / mcap
            if ratio < 0.02:
                red_flags.append(
                    f"Liquidity is only {ratio * 100:.1f}% of market cap "
                    f"(${liq:,.0f} vs ${mcap:,.0f}) — easy rug / heavy slippage."
                )
            elif ratio < 0.05:
                warnings.append(f"Thin liquidity vs market cap ({ratio * 100:.1f}%).")
        if vol is not None and mcap and mcap > 0:
            if vol / mcap < 0.01 or vol < 100:
                warnings.append(
                    f"24h volume (${vol:,.0f}) is tiny vs market cap — possibly a dead token."
                )
        if age is not None and age < 1:
            warnings.append(f"Pair is only {age} days old — no track record at all.")

    if pump and pump.get("is_pumpfun") and not pump.get("migrated_to_raydium"):
        warnings.append(
            "Still on the pump.fun bonding curve (has not migrated to Raydium)"
            + (
                f" — bonding curve at {pump['bonding_curve_pct']}%."
                if pump.get("bonding_curve_pct") is not None
                else "."
            )
        )

    if onchain is None:
        warnings.append("On-chain data (authorities / holders) unavailable — score is less reliable.")

    report = {
        "ca": ca,
        "market": dex,
        "onchain": onchain,
        "pumpfun": pump,
        "rugcheck": rugcheck,
        "red_flags": red_flags,
        "warnings": warnings,
        "comparables": similar,
        "meta_trending": trending,
        "narrative": narrative,
        "data_source_errors": errors,
    }
    report["hoopium_score"] = compute_hoopium_score(report)
    if report["hoopium_score"] >= 70:
        report["risk_score"] = "LOW"
    elif report["hoopium_score"] >= 40:
        report["risk_score"] = "MEDIUM"
    else:
        report["risk_score"] = "HIGH"
    return report, errors


def compute_hoopium_score(report):
    """0-100 'how safe does this look' score. 100 = cleanest. Plain penalty heuristics."""
    onchain = report["onchain"] or {}
    dex = report["market"] or {}
    rugcheck = report["rugcheck"] or {}
    pump = report["pumpfun"] or {}

    score = 100
    if rugcheck.get("rugged"):
        score -= 60
    if onchain.get("mint_authority"):
        score -= 25
    if onchain.get("freeze_authority"):
        score -= 25

    top10 = onchain.get("top10_holders_pct")
    if top10 is not None:
        if top10 >= 80:
            score -= 30
        elif top10 >= 50:
            score -= 20
        elif top10 >= 30:
            score -= 10

    liq = dex.get("liquidity_usd")
    mcap = dex.get("market_cap_usd")
    vol = dex.get("volume_24h_usd")
    age = dex.get("pair_age_days")
    if liq is not None:
        if liq < 1_000:
            score -= 30
        elif mcap and liq / mcap < 0.02:
            score -= 20
        elif mcap and liq / mcap < 0.05:
            score -= 10
    if vol is not None and mcap and (vol / mcap < 0.01 or vol < 100):
        score -= 10
    if age is not None and age < 1:
        score -= 10
    if pump.get("is_pumpfun") and not pump.get("migrated_to_raydium"):
        score -= 5

    rc_score = rugcheck.get("score")
    if isinstance(rc_score, (int, float)) and rc_score >= 50:
        score -= 10

    if report["onchain"] is None:
        score -= 10  # can't verify authorities/holders: less trust

    # Keep the number consistent with the flags: hard red flags cap the score
    if len(report["red_flags"]) >= 2:
        score = min(score, 35)
    elif len(report["red_flags"]) == 1:
        score = min(score, 65)

    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# User-defined buy rules
# ---------------------------------------------------------------------------

ALLOWED_RULE_OPS = {">=", "<=", ">", "<", "=="}
MAX_RULE_EXPR_LEN = 200


class _MissingMetric(Exception):
    pass


_EXPR_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_EXPR_CMPOPS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def safe_eval_rule(expr, metrics):
    """Evaluate a user-coded rule like 'liquidity_usd / market_cap_usd > 0.05 and total_holders > 300'.

    Whitelisted AST only: numbers, metric names, + - * / %, comparisons, and/or/not, parentheses.
    Raises _MissingMetric when a referenced metric has no data, ValueError for anything not allowed.
    """
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.BoolOp):
            values = [ev(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            raise ValueError("operator not allowed")
        if isinstance(node, ast.BinOp) and type(node.op) in _EXPR_BINOPS:
            return _EXPR_BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            result = True
            for op, comparator in zip(node.ops, node.comparators):
                if type(op) not in _EXPR_CMPOPS:
                    raise ValueError("comparison not allowed")
                right = ev(comparator)
                result = result and _EXPR_CMPOPS[type(op)](left, right)
                left = right
            return result
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in metrics:
                raise ValueError(f"unknown variable '{node.id}'")
            value = metrics[node.id]
            if value is None:
                raise _MissingMetric(node.id)
            return value
        raise ValueError(f"'{type(node).__name__}' not allowed in rules")

    return bool(ev(tree.body))


def collect_metrics(report):
    """Flat metric dict the user can write rules against."""
    dex = report["market"] or {}
    onchain = report["onchain"] or {}
    rugcheck = report["rugcheck"] or {}
    pump = report["pumpfun"] or {}
    liq = dex.get("liquidity_usd")
    mcap = dex.get("market_cap_usd")
    return {
        "hoopium_score": report["hoopium_score"],
        "market_cap_usd": mcap,
        "liquidity_usd": liq,
        "liquidity_to_mcap_pct": round(liq / mcap * 100, 2) if liq is not None and mcap else None,
        "volume_24h_usd": dex.get("volume_24h_usd"),
        "price_usd": dex.get("price_usd"),
        "price_change_24h_pct": dex.get("price_change_24h_pct"),
        "pair_age_days": dex.get("pair_age_days"),
        "top10_holders_pct": onchain.get("top10_holders_pct"),
        "total_holders": rugcheck.get("total_holders") or None,
        "rugcheck_score": rugcheck.get("score"),
        "bonding_curve_pct": pump.get("bonding_curve_pct"),
        "mint_renounced": None if report["onchain"] is None else (0 if onchain.get("mint_authority") else 1),
        "freeze_renounced": None if report["onchain"] is None else (0 if onchain.get("freeze_authority") else 1),
    }


def evaluate_user_rules(report, rules):
    """Check the user's own buy rules against the scanned metrics.

    rules: list of either
      {"metric": <key of collect_metrics>, "op": ">=|<=|>|<|==", "value": number}   (simple)
      {"expr": "liquidity_usd / market_cap_usd > 0.05 and total_holders > 300"}     (coded)
    Returns None when there are no usable rules.
    """
    if not isinstance(rules, list):
        return None
    metrics = collect_metrics(report)
    results = []
    for rule in rules[:20]:
        if not isinstance(rule, dict):
            continue

        expr = str(rule.get("expr") or "").strip()
        if expr:
            label = expr[:MAX_RULE_EXPR_LEN]
            actual = None
            try:
                status = "pass" if safe_eval_rule(label, metrics) else "fail"
            except _MissingMetric:
                status = "unknown"
            except Exception:
                status = "invalid"
            results.append({"label": label, "expr": label, "actual": actual, "status": status})
            continue

        metric = rule.get("metric")
        op = rule.get("op")
        value = _to_float(rule.get("value"))
        if metric not in metrics or op not in ALLOWED_RULE_OPS or value is None:
            continue
        actual = metrics[metric]
        if actual is None:
            status = "unknown"
        else:
            passed = {
                ">=": actual >= value,
                "<=": actual <= value,
                ">": actual > value,
                "<": actual < value,
                "==": actual == value,
            }[op]
            status = "pass" if passed else "fail"
        results.append(
            {
                "label": f"{metric} {op} {_fmt(value)}",
                "metric": metric,
                "op": op,
                "value": value,
                "actual": actual,
                "status": status,
            }
        )
    if not results:
        return None
    n_pass = sum(1 for r in results if r["status"] == "pass")
    all_pass = n_pass == len(results)
    return {
        "verdict": "WOULD BUY" if all_pass else "WOULD NOT BUY",
        "passed": all_pass,
        "n_pass": n_pass,
        "n_rules": len(results),
        "results": results,
    }


def format_rules_for_llm(rules_eval):
    if not rules_eval:
        return ""
    lines = ["", "USER'S OWN BUY RULES (already evaluated, do not re-judge them):"]
    for r in rules_eval["results"]:
        detail = "" if r["actual"] is None else f" (actual {_fmt(r['actual'])})"
        lines.append(f"- {r['label']}: {r['status'].upper()}{detail}")
    lines.append(
        f"VERDICT PER USER RULES: {rules_eval['verdict']} "
        f"({rules_eval['n_pass']}/{rules_eval['n_rules']} rules passed)"
    )
    return "\n".join(lines)


def format_report_for_llm(report):
    lines = [f"TOKEN ANALYSIS RESULT for CA {report['ca']}", ""]

    dex = report["market"]
    lines.append("HARD DATA:")
    if dex:
        lines.append(f"- Name/symbol: {dex.get('name')} ({dex.get('symbol')}) on {dex.get('dex')}")
        lines.append(f"- Price: ${_fmt(dex.get('price_usd'))}")
        lines.append(f"- Liquidity: ${_fmt(dex.get('liquidity_usd'))}")
        lines.append(f"- 24h volume: ${_fmt(dex.get('volume_24h_usd'))}")
        lines.append(f"- Market cap: ${_fmt(dex.get('market_cap_usd'))}")
        lines.append(f"- 24h price change: {_fmt(dex.get('price_change_24h_pct'))}%")
        lines.append(f"- Pair age: {_fmt(dex.get('pair_age_days'))} days")
    else:
        lines.append("- No DexScreener market data available.")

    onchain = report["onchain"]
    if onchain:
        lines.append(
            "- Mint authority: "
            + ("RENOUNCED" if not onchain["mint_authority"] else f"ACTIVE ({onchain['mint_authority']})")
        )
        lines.append(
            "- Freeze authority: "
            + ("RENOUNCED" if not onchain["freeze_authority"] else f"ACTIVE ({onchain['freeze_authority']})")
        )
        lines.append(f"- Top 10 accounts hold: {_fmt(onchain.get('top10_holders_pct'))}% of supply "
                     "(includes liquidity pool / bonding curve accounts)")
    else:
        lines.append("- On-chain authority/holder data unavailable.")

    pump = report["pumpfun"]
    if pump and pump.get("is_pumpfun"):
        if pump.get("migrated_to_raydium"):
            lines.append("- pump.fun token: bonding curve COMPLETE, migrated to Raydium.")
        else:
            lines.append(
                f"- pump.fun token: still on bonding curve ({_fmt(pump.get('bonding_curve_pct'))}% complete)."
            )

    rugcheck = report["rugcheck"]
    if rugcheck:
        lines.append(f"- RugCheck score (cross-reference): {_fmt(rugcheck.get('score'))}")
        if rugcheck.get("total_holders"):
            lines.append(f"- Total holders: {_fmt(rugcheck.get('total_holders'))}")
        if rugcheck.get("risks"):
            lines.append(f"- RugCheck flagged risks: {', '.join(rugcheck['risks'])}")

    lines.append("")
    lines.append("RED FLAGS FOUND:")
    if report["red_flags"]:
        lines.extend(f"- {f}" for f in report["red_flags"])
    else:
        lines.append("- none")
    lines.append("")
    lines.append("WARNINGS:")
    if report["warnings"]:
        lines.extend(f"- {w}" for w in report["warnings"])
    else:
        lines.append("- none")
    lines.append("")
    lines.append("COMPARABLE TOKENS (similar name/symbol on Solana):")
    if report["comparables"]:
        for c in report["comparables"]:
            lines.append(
                f"- {c.get('name')} ({c.get('symbol')}): mcap ${_fmt(c.get('market_cap_usd'))}, "
                f"liquidity ${_fmt(c.get('liquidity_usd'))}, 24h {_fmt(c.get('price_change_24h_pct'))}%, "
                f"age {_fmt(c.get('pair_age_days'))} days"
            )
    else:
        lines.append("- none found")

    narrative = report.get("narrative") or {}
    lines.append("")
    lines.append("TOKEN LORE / NARRATIVE:")
    lines.append(f"- Name/symbol: {narrative.get('name')} ({narrative.get('symbol')})")
    if narrative.get("description"):
        lines.append(f'- Description: "{narrative["description"]}"')
    else:
        lines.append("- No description available; judge the narrative from the name/symbol alone.")

    lines.append("")
    lines.append("CURRENT PUMP.FUN META (tokens live/trending right now):")
    if report.get("meta_trending"):
        for t in report["meta_trending"]:
            desc = f' — "{t["description"]}"' if t.get("description") else ""
            mcap = f" (mcap ${_fmt(t['usd_market_cap'])})" if t.get("usd_market_cap") else ""
            lines.append(f"- {t.get('name')} ({t.get('symbol')}){mcap}{desc}")
    else:
        lines.append("- unavailable right now")

    return "\n".join(lines)


def _fmt(value):
    if value is None:
        return "unknown"
    if isinstance(value, float):
        if value != 0 and abs(value) < 0.01:
            return f"{value:.8f}".rstrip("0")
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


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
        "Sign this message to prove you own this wallet and unlock HOOPIUM.\n\n"
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


def run_scan(message, rules=None):
    """Scan logic shared by /api/chat (web, wallet-gated) and /api/scan (browser extension)."""
    ca = extract_solana_ca(message)
    if not ca:
        return jsonify(
            {
                "reply": "that doesn't look like a Solana contract address, ser. "
                "paste a token CA (base58, 32-44 chars, e.g. from dexscreener or pump.fun) "
                "and I'll scan it for rug vibes."
            }
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

    report, errors = build_risk_report(ca)
    if report is None:
        detail = " / ".join(errors) if errors else "no data returned"
        return jsonify(
            {
                "reply": f"couldn't pull any data for {ca}, ser. either it's not a token mint, "
                f"it has no market yet, or the free APIs are down. details: {detail}"
            }
        )

    rules_eval = evaluate_user_rules(report, rules)
    analysis_text = (
        format_report_for_llm(report)
        + format_rules_for_llm(rules_eval)
        + f"\n\nHOOPIUM SCORE (goes in the final section): {report['hoopium_score']}/100 (100 = cleanest)"
        + f"\nCOMPUTED RISK LEVEL: {report['risk_score']}"
    )

    # Structured fields so the frontends can show the verdicts instantly
    extra = {
        "hoopium_score": report["hoopium_score"],
        "risk_level": report["risk_score"],
        "user_rules": rules_eval,
    }

    try:
        client = get_groq_client()
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": analysis_text},
            ],
            temperature=0.4,
            max_tokens=1024,
        )
        reply = completion.choices[0].message.content
        return jsonify({"reply": reply, **extra})
    except Exception as e:
        # LLM down/rate-limited: still deliver the computed analysis instead of breaking
        return jsonify(
            {
                "reply": "groq is not cooperating right now "
                f"({e}), so here's the raw scan instead:\n\n{analysis_text}",
                **extra,
            }
        )


@app.route("/api/chat", methods=["POST"])
def chat():
    if not get_session_pubkey():
        return (
            jsonify({"error": "Wallet not connected. Connect your Phantom wallet first, ser."}),
            401,
        )

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Send a JSON body with a 'message' field."}), 400

    return run_scan(message, data.get("rules"))


@app.route("/api/scan", methods=["POST", "OPTIONS"])
def scan():
    """Wallet-free endpoint for the browser extension (local use)."""
    if request.method == "OPTIONS":
        return _cors(app.make_response(("", 204)))

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return _cors(jsonify({"error": "Send a JSON body with a 'message' field."})), 400

    response = run_scan(message, data.get("rules"))
    # run_scan may return (response, status) or just a response
    if isinstance(response, tuple):
        return _cors(response[0]), response[1]
    return _cors(response)


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


if __name__ == "__main__":
    # Port 5001 because on macOS port 5000 is taken by AirPlay Receiver
    app.run(debug=True, port=5001)
