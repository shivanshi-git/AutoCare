// ---------- Configuration ----------
const BACKEND_RENDER_URL = window.RENDER_BACKEND_URL || "https://autocare-backend.onrender.com";
const API_BASE = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost")
  ? "http://127.0.0.1:8000"
  : (window.location.origin.includes("onrender.com") && !window.location.origin.includes("-backend") ? BACKEND_RENDER_URL : window.location.origin);
const API_KEY = "admin-secret-key"; // Default API key used in development

let kb = [];

// ---------- Navigation Logic ----------
document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");

    const pageId = "page-" + btn.dataset.page;
    const pageEl = document.getElementById(pageId);
    if (pageEl) {
      pageEl.classList.add("active");
    }

    // Refresh data depending on page target
    if (btn.dataset.page === "documents") {
      loadKb();
    }
    if (btn.dataset.page === "search") {
      renderSearch("");
    }
    if (btn.dataset.page === "dashboard") {
      loadKb(); // To update knowledge base size metric
    }
  });
});

// ---------- Load KB Data from Backend ----------
async function loadKb() {
  try {
    const res = await fetch(`${API_BASE}/api/qa`);
    if (!res.ok) throw new Error("Failed to fetch QA data");
    const data = await res.json();
    kb = data.faqs || [];
    renderKb();
    renderSearch(document.getElementById("searchInput")?.value || "");
  } catch (err) {
    console.error("Error loading FAQs from backend:", err);
    // Render offline message in document manager if fetch fails
    const list = document.getElementById("kbList");
    if (list) {
      list.innerHTML = `<div class="panel" style="color: #c0392b;">Could not connect to backend server. Make sure it is running on ${API_BASE}</div>`;
    }
  }
}

// Helper to generate keywords tags based on question text
function getTagsForQuestion(q) {
  const tags = [];
  const qLower = q.toLowerCase();
  if (qLower.includes("warranty")) tags.push("warranty");
  if (qLower.includes("service") || qLower.includes("maintenance")) tags.push("service");
  if (qLower.includes("book") || qLower.includes("appointment")) tags.push("booking");
  if (qLower.includes("hours") || qLower.includes("timings") || qLower.includes("working")) tags.push("timings");
  if (qLower.includes("roadside") || qLower.includes("assistance") || qLower.includes("breakdown")) tags.push("roadside assistance");
  if (qLower.includes("insurance") || qLower.includes("claim")) tags.push("insurance");
  if (qLower.includes("parts") || qLower.includes("order")) tags.push("spare parts");
  if (qLower.includes("hybrid") || qLower.includes("smart hybrid")) tags.push("hybrid");
  if (qLower.includes("cng")) tags.push("cng");
  if (qLower.includes("nexa") || qLower.includes("arena")) tags.push("showroom");
  if (tags.length === 0) tags.push("general");
  return tags;
}

// ---------- Render Documents KB List ----------
function renderKb() {
  const list = document.getElementById("kbList");
  const sizeStat = document.getElementById("kbSizeStat");

  if (sizeStat) {
    sizeStat.textContent = kb.length;
  }

  if (!list) return;

  if (kb.length === 0) {
    list.innerHTML = '<div class="panel">No entries found in the knowledge base. Add some below!</div>';
    return;
  }

  list.innerHTML = kb.map((item, index) => {
    const tags = getTagsForQuestion(item.question);
    const tagsHtml = tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join(" ");
    return `
      <div class="kb-item">
        <div>
          <div class="q">${escapeHtml(item.question)}</div>
          <div class="a">${escapeHtml(item.answer)}</div>
          ${tagsHtml}
        </div>
        <button class="delete-btn" data-question="${escapeHtml(item.question)}">Delete</button>
      </div>
    `;
  }).join("");

  // Add click handlers for delete buttons
  list.querySelectorAll(".delete-btn").forEach(b => {
    b.addEventListener("click", async () => {
      const q = b.dataset.question;
      if (confirm(`Are you sure you want to delete this FAQ entry?\n\n"${q}"`)) {
        await deleteKbEntry(q);
      }
    });
  });
}

// ---------- Add KB Entry to Backend ----------
document.getElementById("kbAddBtn")?.addEventListener("click", async () => {
  const qInput = document.getElementById("kbQuestion");
  const aInput = document.getElementById("kbAnswer");
  const q = qInput.value.trim();
  const a = aInput.value.trim();

  if (!q || !a) {
    alert("Please fill in both the Question and the Answer fields.");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/qa`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${API_KEY}`
      },
      body: JSON.stringify({ question: q, answer: a })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to add FAQ pair");
    }

    // Clear inputs and reload
    qInput.value = "";
    aInput.value = "";
    await loadKb();
  } catch (err) {
    console.error("Error adding QA entry:", err);
    alert(`Error: ${err.message}`);
  }
});

// ---------- Delete KB Entry from Backend ----------
async function deleteKbEntry(question) {
  try {
    const res = await fetch(`${API_BASE}/api/qa`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${API_KEY}`
      },
      body: JSON.stringify({ question: question })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to delete FAQ pair");
    }

    await loadKb();
  } catch (err) {
    console.error("Error deleting QA entry:", err);
    alert(`Error: ${err.message}`);
  }
}

// ---------- AI Chat Client ----------
const chatWindow = document.getElementById("chatWindow");
const chatInput = document.getElementById("chatInput");

// ---------- Citation Cards for Chat Answers ----------
function renderCitationCards(citations) {
  if (!citations || !citations.length) return "";
  const cards = citations.map((c, i) => {
    const label = escapeHtml(c.name || "Source");
    const kind = c.kind || "Document";
    const page = c.page ? `Page ${c.page}` : "";
    const detail = kind === "Industry Reference"
      ? `Industry reference · ${escapeHtml(c.topic || "General")} ↗`
      : [page, escapeHtml(c.model || ""), escapeHtml(c.team || "")].filter(Boolean).join(" · ");
    return `<div class="citation-card" title="${escapeHtml(c.excerpt || '')}">
      <span class="citation-index">${i + 1}</span>
      <span class="citation-info">
        <span class="citation-name">${label}</span>
        <span class="citation-detail">${detail}</span>
      </span>
    </div>`;
  }).join("");
  return `<div class="citation-list">${cards}</div>`;
}

function addMessage(text, sender, meta, citations) {
  if (!chatWindow) return;

  const msg = document.createElement("div");
  msg.className = "message " + sender;

  const avatarText = sender === 'user' ? 'You' : 'AC';
  const avatarClass = sender === 'user' ? 'user-avatar' : 'bot-avatar';

  msg.innerHTML = `
    <div class="avatar ${avatarClass}">${avatarText}</div>
    <div class="bubble">
      ${escapeHtml(text)}
      ${meta ? `<span class="meta">${escapeHtml(meta)}</span>` : ""}
      ${sender === 'bot' ? renderCitationCards(citations) : ""}
    </div>
  `;
  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function sendMessage(text) {
  const query = text.trim();
  if (!query) return;

  addMessage(query, "user");
  if (chatInput) {
    chatInput.value = "";
  }

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query })
    });

    if (!res.ok) throw new Error("Network response not ok");
    const data = await res.json();

    let metaInfo = "";
    if (data.matched_question) {
      metaInfo = `Matched: "${data.matched_question}" (confidence: ${(data.confidence * 100).toFixed(0)}%)`;
    } else {
      metaInfo = `Confidence: ${(data.confidence * 100).toFixed(0)}%`;
    }

    addMessage(data.answer, "bot", metaInfo, data.citations);
  } catch (err) {
    console.error("API call failed:", err);
    addMessage(`Could not connect to the backend server. Make sure it is running on ${API_BASE}`, "bot");
  }
}

document.getElementById("sendBtn")?.addEventListener("click", () => sendMessage(chatInput.value));
chatInput?.addEventListener("keydown", e => {
  if (e.key === "Enter") sendMessage(chatInput.value);
});

// Bind quick chip buttons
document.querySelectorAll(".chip").forEach(c => {
  c.addEventListener("click", () => sendMessage(c.dataset.q));
});

// ---------- Search Logic (Local Filter) ----------
function renderSearch(query) {
  const results = document.getElementById("searchResults");
  if (!results) return;

  const qn = query.toLowerCase().trim();
  const filtered = qn
    ? kb.filter(i => i.question.toLowerCase().includes(qn) || i.answer.toLowerCase().includes(qn))
    : kb;

  if (filtered.length === 0) {
    results.innerHTML = `<div class="panel">No results found matching "${query}".</div>`;
    return;
  }

  results.innerHTML = filtered.map(item => `
    <div class="kb-item">
      <div>
        <div class="q">${escapeHtml(item.question)}</div>
        <div class="a">${escapeHtml(item.answer)}</div>
      </div>
    </div>
  `).join("");
}

document.getElementById("searchInput")?.addEventListener("input", e => {
  renderSearch(e.target.value);
});

// ---------- Utilities ----------
function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

// ---------- Initial Boot ----------
loadKb();
