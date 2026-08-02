// Turn-based client that talks to the fallback FastAPI /api/chat endpoint.

const API = window.VOICE_SERVER_URL || "http://localhost:7860";
const SESSION_ID = "sess-" + Math.random().toString(36).slice(2, 8);

const el = (id) => document.getElementById(id);
const transcriptEl = el("transcript");
const borrowerSel = el("borrower");
const micBtn = el("mic");
const sendBtn = el("send");
const textInput = el("text-input");
const micLabel = el("mic-label");
const statusDot = el("status-dot");
const statusText = el("status-text");

let sending = false;
let borrowerById = {};
let liveCall = false;
let recognition = null;
let recognitionActive = false;
let suppressRecognitionRestart = false;
let botSpeaking = false;
let voiceQueue = [];
let processingVoiceQueue = false;

const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

function setStatus(state, text) {
  statusDot.className = "dot dot-" + state;
  statusText.textContent = text;
}

// ── Boot ────────────────────────────────────────────────────────────────────
async function boot() {
  setStatus("think", "Waking agent...");
  try {
    await fetch(`${API}/api/wake`);
  } catch (_) {}
  await loadBorrowers();
  await refreshSidebar();
  transcriptEl.innerHTML =
    '<div class="hint">Press <b>Start Call</b> and speak naturally. Your voice is transcribed live and sent turn-by-turn automatically, while the agent replies with speech.</div>';
  micLabel.textContent = "Start Call";
  setStatus("idle", "Ready");
  setInterval(refreshSidebar, 3000);
}

async function loadBorrowers() {
  try {
    const r = await fetch(`${API}/api/borrowers`);
    const { borrowers } = await r.json();
    borrowerById = Object.fromEntries(borrowers.map((b) => [b.loan_id, b]));
    borrowerSel.innerHTML = borrowers
      .map(
        (b) =>
          `<option value="${b.loan_id}">${b.name} · ${b.language} · ₹${b.emi_amount} overdue</option>`
      )
      .join("");
  } catch (_) {
    borrowerById = {
      L001: {
        loan_id: "L001",
        language: "hi-IN",
      },
    };
    borrowerSel.innerHTML = `<option value="L001">Ramesh Kumar · hi-IN</option>`;
  }
}

function addBubble(role, text) {
  const hint = transcriptEl.querySelector(".hint");
  if (hint) hint.remove();
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.innerHTML = escapeHtml(text || "");
  transcriptEl.appendChild(bubble);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function speakWithBrowserTTS(text) {
  const content = (text || "").trim();
  if (!content || !window.speechSynthesis) return Promise.resolve();
  return new Promise((resolve) => {
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(content);
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.onend = () => resolve();
      utterance.onerror = () => resolve();
      window.speechSynthesis.speak(utterance);
    } catch (_) {
      resolve();
    }
  });
}

function selectedBorrowerLanguage() {
  return borrowerById[borrowerSel.value]?.language || "hi-IN";
}

function ensureRecognition() {
  if (recognition) return true;
  if (!SpeechRecognitionCtor) return false;

  recognition = new SpeechRecognitionCtor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = selectedBorrowerLanguage();

  recognition.onresult = (event) => {
    let finalText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        finalText += event.results[i][0].transcript + " ";
      }
    }
    const turn = finalText.trim();
    if (turn) {
      addBubble("user", turn);
      voiceQueue.push(turn);
      processVoiceQueue();
    }
  };

  recognition.onend = () => {
    recognitionActive = false;
    if (liveCall && !suppressRecognitionRestart && !botSpeaking) {
      startRecognition();
    }
    suppressRecognitionRestart = false;
  };

  recognition.onerror = () => {
    if (liveCall) {
      setStatus("live", "Listening...");
    }
  };

  return true;
}

function startRecognition() {
  if (!recognition || recognitionActive) return;
  try {
    recognition.lang = selectedBorrowerLanguage();
    recognition.start();
    recognitionActive = true;
    setStatus("live", "Listening...");
  } catch (_) {}
}

function stopRecognition(permanent = false) {
  if (!recognition || !recognitionActive) return;
  suppressRecognitionRestart = permanent;
  recognition.stop();
  recognitionActive = false;
}

function stopRecognitionForPlayback() {
  if (!recognitionActive) return;
  suppressRecognitionRestart = true;
  recognition.stop();
  recognitionActive = false;
}

async function playAudioBase64(audioBase64, fallbackText) {
  botSpeaking = true;
  stopRecognitionForPlayback();

  const audioData = (audioBase64 || "").trim();
  if (!audioData) {
    await speakWithBrowserTTS(fallbackText);
    botSpeaking = false;
    if (liveCall) startRecognition();
    return;
  }

  let audio = document.getElementById("bot-audio");
  if (!audio) {
    audio = document.createElement("audio");
    audio.id = "bot-audio";
    document.body.appendChild(audio);
  }

  const candidates = ["audio/wav", "audio/mpeg", "audio/ogg"];
  for (const mime of candidates) {
    try {
      audio.src = `data:${mime};base64,${audioData}`;
      await audio.play();
      await new Promise((resolve) => {
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
      });
      botSpeaking = false;
      if (liveCall) startRecognition();
      return;
    } catch (_) {
      // Try next MIME type; Sarvam audio container may vary by model/version.
    }
  }

  await speakWithBrowserTTS(fallbackText);
  botSpeaking = false;
  if (liveCall) startRecognition();
}

async function sendTextTurn(text, fromVoice = false) {
  const cleaned = (text || "").trim();
  if (!cleaned || sending) return;

  sending = true;
  if (!liveCall) micBtn.disabled = true;
  sendBtn.disabled = true;
  setStatus("think", "Agent thinking...");

  if (!fromVoice) {
    addBubble("user", cleaned);
    textInput.value = "";
  }

  try {
    const form = new FormData();
    form.append("session_id", SESSION_ID);
    form.append("loan_id", borrowerSel.value || "L001");
    form.append("text", cleaned);

    const r = await fetch(`${API}/api/chat`, { method: "POST", body: form });
    if (!r.ok) {
      throw new Error(`Request failed with status ${r.status}`);
    }
    const data = await r.json();
    addBubble("bot", data.reply || "No reply received.");
    await playAudioBase64(data.audio_base64 || "", data.reply || "");
    setStatus("idle", "Ready");
  } catch (err) {
    console.error(err);
    addBubble("bot", "Service temporarily unavailable. Please try another turn.");
    setStatus("idle", "Service error");
  } finally {
    sending = false;
    micBtn.disabled = false;
    sendBtn.disabled = false;
    if (liveCall) {
      micLabel.textContent = "End Call";
      if (!recognitionActive && !botSpeaking) startRecognition();
    } else {
      micLabel.textContent = "Start Call";
    }
  }
}

async function processVoiceQueue() {
  if (processingVoiceQueue) return;
  processingVoiceQueue = true;
  try {
    while (voiceQueue.length) {
      const turn = voiceQueue.shift();
      await sendTextTurn(turn, true);
    }
  } finally {
    processingVoiceQueue = false;
    if (liveCall && !recognitionActive && !botSpeaking) {
      startRecognition();
    }
  }
}

function startLiveCall() {
  if (liveCall) return;
  if (!ensureRecognition()) {
    addBubble("bot", "Live voice is not supported in this browser. Use typed Send.");
    setStatus("idle", "Voice unsupported");
    return;
  }
  liveCall = true;
  micBtn.classList.add("recording");
  micLabel.textContent = "End Call";
  addBubble("bot", "Connected. Please speak naturally.");
  startRecognition();
}

function endLiveCall() {
  if (!liveCall) return;
  liveCall = false;
  voiceQueue = [];
  stopRecognition(true);
  micBtn.classList.remove("recording");
  micLabel.textContent = "Start Call";
  setStatus("idle", "Ready");
}

function toggleLiveCall() {
  if (liveCall) {
    endLiveCall();
  } else {
    startLiveCall();
  }
}

async function sendTurn() {
  const text = (textInput.value || "").trim();
  if (!text) {
    textInput.focus();
    return;
  }
  await sendTextTurn(text, false);
}

// ── Sidebar: CRM + metrics ──────────────────────────────────────────────────
async function refreshSidebar() {
  try {
    const [mRes, cRes] = await Promise.all([
      fetch(`${API}/api/metrics`),
      fetch(`${API}/api/crm`),
    ]);
    const m = await mRes.json();
    const { calls } = await cRes.json();

    el("m-calls").textContent = m.calls_handled;
    el("m-ptp").textContent = m.promise_to_pay;
    el("m-esc").textContent = m.escalated;
    el("m-savings").textContent = "₹" + (m.savings || 0).toLocaleString("en-IN");

    const crm = el("crm");
    if (!calls.length) return;
    crm.innerHTML = calls
      .map(
        (c) => `
      <div class="crm-row">
        <div class="top">
          <span class="name">${escapeHtml(c.name)}</span>
          <span class="chip ${c.disposition}">${c.disposition.replace(/_/g, " ")}</span>
        </div>
        <div class="meta">
          ${c.language} · ${c.sentiment}
          ${c.promise_to_pay_date ? "· PTP " + c.promise_to_pay_date : ""}
          ${c.escalate ? "· ⚠ escalated" : ""}
        </div>
      </div>`
      )
      .join("");
  } catch (_) {}
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

micBtn.addEventListener("click", toggleLiveCall);
sendBtn.addEventListener("click", sendTurn);
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendTurn();
});

boot();
