const API_URL = "http://localhost:5001/api/scan";

const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent =
    role === "user" ? "[anon] " :
    role === "error" ? "[ERROR] " :
    role.startsWith("verdict") ? "[RULES] " : "[COPIUM] ";
  div.appendChild(tag);
  div.appendChild(document.createTextNode(text));
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function addRulesVerdict(data) {
  if (data.user_rules) {
    const r = data.user_rules;
    addMessage(
      r.passed ? "verdict-pass" : "verdict-fail",
      `${r.passed ? "✓" : "✗"} ${r.verdict} per your rules (${r.n_pass}/${r.n_rules} passed)`
    );
  }
}

function addScoreMessage(data) {
  if (typeof data.copium_score === "number") {
    addMessage("bot", `COPIUM score: ${data.copium_score}/100 — risk ${(data.risk_level || "?").toLowerCase()}`);
  }
}

async function scan(message) {
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  sendBtn.disabled = true;
  input.disabled = true;
  const loading = addMessage("bot", "scanning... gimme a few seconds ser");

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, rules }),
    });
    const data = await res.json();
    loading.remove();
    if (!res.ok || data.error) {
      addMessage("error", data.error || "something broke, ngmi");
    } else {
      addRulesVerdict(data);
      addMessage("bot", data.reply);
      addScoreMessage(data);
    }
  } catch (err) {
    loading.remove();
    addMessage(
      "error",
      "couldn't reach the COPIUM server on localhost:5001. start it with `python app.py` in the copium-chat folder, ser."
    );
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

sendBtn.addEventListener("click", () => scan(input.value.trim()));
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") scan(input.value.trim());
});

// ---------- user buy rules (saved in the extension) ----------
const rulesToggle = document.getElementById("rules-toggle");
const rulesBody = document.getElementById("rules-body");
const rulesList = document.getElementById("rules-list");
const rulesCount = document.getElementById("rules-count");
const ruleMetric = document.getElementById("rule-metric");
const ruleOp = document.getElementById("rule-op");
const ruleValue = document.getElementById("rule-value");

let rules = [];

function metricLabel(key) {
  const opt = ruleMetric.querySelector(`option[value="${key}"]`);
  return opt ? opt.textContent : key;
}

async function saveRules() {
  try {
    await chrome.storage.local.set({ copiumRules: rules });
  } catch (e) {}
  renderRules();
}

function renderRules() {
  rulesCount.textContent = rules.length ? ` (${rules.length})` : "";
  rulesList.innerHTML = "";
  if (!rules.length) {
    const p = document.createElement("div");
    p.className = "rule-row";
    p.textContent = "no rules yet — add one below, ser";
    rulesList.appendChild(p);
    return;
  }
  rules.forEach((rule, i) => {
    const row = document.createElement("div");
    row.className = "rule-row";
    const del = document.createElement("button");
    del.className = "rule-del";
    del.textContent = "[x]";
    del.title = "delete rule";
    del.addEventListener("click", () => { rules.splice(i, 1); saveRules(); });
    row.appendChild(del);
    const label = rule.expr ? `{ ${rule.expr} }` : `${metricLabel(rule.metric)} ${rule.op} ${rule.value}`;
    row.appendChild(document.createTextNode(label));
    rulesList.appendChild(row);
  });
}

rulesToggle.addEventListener("click", () => {
  rulesBody.hidden = !rulesBody.hidden;
  rulesToggle.textContent = (rulesBody.hidden ? "[+]" : "[-]") + " my rules";
  rulesToggle.appendChild(rulesCount);
  renderRules();
});

document.getElementById("rule-add-btn").addEventListener("click", () => {
  const value = parseFloat(ruleValue.value);
  if (Number.isNaN(value)) { ruleValue.focus(); return; }
  rules.push({ metric: ruleMetric.value, op: ruleOp.value, value });
  ruleValue.value = "";
  saveRules();
});

const ruleExpr = document.getElementById("rule-expr");
document.getElementById("rule-expr-btn").addEventListener("click", () => {
  const expr = ruleExpr.value.trim();
  if (!expr) { ruleExpr.focus(); return; }
  rules.push({ expr });
  ruleExpr.value = "";
  saveRules();
});
ruleExpr.addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("rule-expr-btn").click();
});

// Load saved rules, then handle a pending context-menu scan
(async () => {
  try {
    const { copiumRules } = await chrome.storage.local.get("copiumRules");
    if (Array.isArray(copiumRules)) rules = copiumRules;
  } catch (e) {}
  renderRules();

  try {
    const { pendingScan } = await chrome.storage.session.get("pendingScan");
    if (pendingScan) {
      await chrome.storage.session.remove("pendingScan");
      scan(pendingScan);
      return;
    }
  } catch (e) {
    // storage unavailable (e.g. opened as a plain page): just wait for manual input
  }
  input.focus();
})();
