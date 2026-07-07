const API_URL = "http://localhost:5001/api/scan";

const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = role === "user" ? "[anon] " : role === "bot" ? "[COPIUM] " : "[ERROR] ";
  div.appendChild(tag);
  div.appendChild(document.createTextNode(text));
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function scan(message) {
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  sendBtn.disabled = true;
  input.disabled = true;
  addMessage("bot", "scanning... (hitting 4 free APIs, gimme a few seconds ser)");
  const loading = chat.lastChild;

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    loading.remove();
    if (!res.ok || data.error) {
      addMessage("error", data.error || "something broke, ngmi");
    } else {
      addMessage("bot", data.reply);
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

// If the popup was opened from the "Scan with COPIUM" context menu, run that CA right away
(async () => {
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
