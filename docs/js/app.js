// AutoCare Documentation SPA Application Logic

document.addEventListener('DOMContentLoaded', () => {
  // Hide Loader on load
  setTimeout(() => {
    const loader = document.getElementById('loader');
    if (loader) loader.classList.add('hidden');
  }, 600);

  // Initialize Core Systems
  initTheme();
  initRouter();
  initSearch();
  initAccordions();
  initMockChatbot();
  initMockAdmin();
});

// ==========================================
// 1. THEME SWITCHER SYSTEM
// ==========================================
function initTheme() {
  const themeBtn = document.getElementById('themeBtn');
  if (!themeBtn) return;

  const currentTheme = localStorage.getItem('autocare_docs_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', currentTheme);
  updateThemeIcon(currentTheme);

  themeBtn.addEventListener('click', () => {
    const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('autocare_docs_theme', newTheme);
    updateThemeIcon(newTheme);
  });
}

function updateThemeIcon(theme) {
  const themeBtn = document.getElementById('themeBtn');
  if (!themeBtn) return;
  if (theme === 'light') {
    themeBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
  } else {
    themeBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`;
  }
}

// ==========================================
// 2. SPA ROUTER & SIDEBAR ENGINE
// ==========================================
function initRouter() {
  const sidebarLinks = document.querySelectorAll('.sidebar-link');
  const sections = document.querySelectorAll('.section');

  function navigate(hash) {
    let targetId = hash.replace('#', '') || 'home';
    let targetSection = document.getElementById(targetId);

    if (!targetSection) {
      targetId = 'home';
      targetSection = document.getElementById(targetId);
    }

    // Deactivate all sections & links
    sections.forEach(s => s.classList.remove('active'));
    sidebarLinks.forEach(l => l.classList.remove('active'));

    // Activate target
    targetSection.classList.add('active');
    
    const activeLink = Array.from(sidebarLinks).find(l => l.getAttribute('href') === `#${targetId}`);
    if (activeLink) activeLink.classList.add('active');

    // Scroll to top of main content
    window.scrollTo({ top: 0, behavior: 'instant' });
    
    // Close mobile menu if open
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.remove('mobile-open');

    // Build right side Table of Contents
    buildTOC(targetSection);
  }

  // Bind links
  sidebarLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const hash = link.getAttribute('href');
      window.location.hash = hash;
      navigate(hash);
    });
  });

  // Listen to hash change
  window.addEventListener('hashchange', () => {
    navigate(window.location.hash);
  });

  // Run initial route
  navigate(window.location.hash);
}

// ==========================================
// 3. TABLE OF CONTENTS ENGINE
// ==========================================
function buildTOC(section) {
  const rightNav = document.getElementById('rightNav');
  if (!rightNav) return;

  rightNav.innerHTML = '';
  const headers = section.querySelectorAll('h2');

  if (headers.length === 0) {
    rightNav.innerHTML = `<span style="font-size:12px;color:var(--text-muted)">No subsections</span>`;
    return;
  }

  headers.forEach((header, index) => {
    // Ensure header has an ID for anchoring
    if (!header.id) {
      header.id = `${section.id}-sub-${index}`;
    }

    const a = document.createElement('a');
    a.className = 'right-link';
    a.textContent = header.textContent.replace(/^[^\w]*/, '').trim(); // Remove emojis or icon prefixes
    a.href = `#${header.id}`;
    
    a.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.right-link').forEach(l => l.classList.remove('active'));
      a.classList.add('active');
      
      const el = document.getElementById(header.id);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });

    rightNav.appendChild(a);
  });
}

// ==========================================
// 4. SEARCH ENGINE (FULL-TEXT)
// ==========================================
function initSearch() {
  const searchInput = document.getElementById('searchInput');
  if (!searchInput) return;

  searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    const sections = document.querySelectorAll('.section');
    
    // Clear custom search highlight styling
    document.querySelectorAll('.search-highlight').forEach(el => {
      el.replaceWith(document.createTextNode(el.textContent));
    });

    if (!query) {
      // Revert sidebar links and section visibilities to routing state
      const hash = window.location.hash || '#home';
      document.querySelectorAll('.sidebar-link').forEach(link => {
        link.style.display = '';
      });
      sections.forEach(s => {
        s.classList.toggle('active', `#${s.id}` === hash);
      });
      return;
    }

    // Show matching section segments
    sections.forEach(s => {
      const text = s.textContent.toLowerCase();
      if (text.includes(query)) {
        s.classList.add('active');
        highlightText(s, query);
      } else {
        s.classList.remove('active');
      }
    });

    // Update sidebar feedback based on visibility
    document.querySelectorAll('.sidebar-link').forEach(link => {
      const hash = link.getAttribute('href');
      const section = document.querySelector(hash);
      if (section) {
        link.style.display = section.classList.contains('active') ? '' : 'none';
      }
    });
  });
}

function highlightText(element, query) {
  const walk = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, null, false);
  let node;
  const nodesToReplace = [];

  while (node = walk.nextNode()) {
    const val = node.nodeValue;
    const lowerVal = val.toLowerCase();
    if (lowerVal.includes(query) && node.parentElement.tagName !== 'SCRIPT' && node.parentElement.tagName !== 'STYLE' && !node.parentElement.classList.contains('code-header') && !node.parentElement.closest('pre')) {
      nodesToReplace.push(node);
    }
  }

  nodesToReplace.forEach(textNode => {
    const parent = textNode.parentElement;
    const val = textNode.nodeValue;
    const regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
    const parts = val.split(regex);
    
    const fragment = document.createDocumentFragment();
    parts.forEach(part => {
      if (part.toLowerCase() === query) {
        const span = document.createElement('span');
        span.className = 'search-highlight';
        span.style.background = 'rgba(210, 153, 34, 0.35)';
        span.style.color = 'var(--text)';
        span.style.borderRadius = '2px';
        span.style.padding = '0 2px';
        span.textContent = part;
        fragment.appendChild(span);
      } else {
        fragment.appendChild(document.createTextNode(part));
      }
    });
    parent.replaceChild(fragment, textNode);
  });
}

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ==========================================
// 5. ACCORDION MECHANISM
// ==========================================
function initAccordions() {
  document.addEventListener('click', (e) => {
    const header = e.target.closest('.accordion-header');
    if (!header) return;

    const accordion = header.parentElement;
    accordion.classList.toggle('open');

    const body = accordion.querySelector('.accordion-body');
    if (accordion.classList.contains('open')) {
      body.style.maxHeight = body.scrollHeight + 'px';
      body.style.padding = '16px 20px';
    } else {
      body.style.maxHeight = '0px';
      // CSS handles padding transition smoothly
    }
  });
}

// ==========================================
// 6. COPY TO CLIPBOARD HELPER
// ==========================================
window.copyCode = function(btn) {
  const pre = btn.closest('.code-block').querySelector('pre');
  if (!pre) return;
  const text = pre.textContent;

  navigator.clipboard.writeText(text).then(() => {
    const originalText = btn.textContent;
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = originalText;
      btn.classList.remove('copied');
    }, 2000);
  });
};

// ==========================================
// 7. INTERACTIVE CUSTOMER CHATBOT SIMULATION
// ==========================================
const MOCK_FAQS = [
  {
    question: "What is the warranty period for Model 1?",
    answer: "The standard warranty period for Model 1 is 2 years or 40,000 kilometers (whichever occurs first) from the date of delivery. Extended warranties up to 5 years can be purchased separately.",
    department: "Service & Maintenance",
    score: 0.92,
    doc: "Model1_WiperSpecs.pdf",
    page: 1,
    category: "New Parts Details"
  },
  {
    question: "How do I file a roadside assistance ticket?",
    answer: "To request towing or roadside assistance, dial our 24/7 helpline at 1800-102-1800. Provide your vehicle registration number, active location details, and vehicle symptoms. Assistance will arrive in approximately 35-45 minutes.",
    department: "Roadside Assistance",
    score: 0.88,
    doc: "Roadside_Emergency_Guidelines.pdf",
    page: 3,
    category: "General AutoCare"
  },
  {
    question: "What items are covered under bumper-to-bumper insurance?",
    answer: "Bumper-to-bumper or zero-depreciation insurance covers all rubber, glass, fiber, and metal parts at 100% depreciation relief. Standard exclusions apply to batteries, tyres, gas kits, and normal wear-and-tear components.",
    department: "Insurance & Claims",
    score: 0.94,
    doc: "Insurance_Claims_Standard_v3.pdf",
    page: 2,
    category: "Approval of Part Details"
  },
  {
    question: "Can QA reject a part below structural pass mark?",
    answer: "Yes. Any engineering document upload containing quality scores below 60/100 (based on checklist structure) is automatically blocked. Furthermore, physical spare parts failing dimensional checks are rejected until corrective actions are approved.",
    department: "QA New Model Development",
    score: 0.91,
    doc: "Model1_WiperSpecs.pdf",
    page: 1,
    category: "Design Review of New Parts"
  }
];

function initMockChatbot() {
  const chatInput = document.getElementById('chatInput');
  const chatSend = document.getElementById('chatSend');
  const chatBody = document.getElementById('chatBody');
  const chatChipsContainer = document.getElementById('chatChips');
  const deptSelect = document.getElementById('chatDeptSelect');
  
  if (!chatInput || !chatSend || !chatBody) return;

  let ratingFailureCount = 0;

  // Handle Department Change
  deptSelect.addEventListener('change', () => {
    const dept = deptSelect.value;
    chatBody.innerHTML = '';
    
    // Add Welcome Message
    addBotMessage(`Welcome to AutoCare **${dept}** assistance portal. How can I help you today?`);
    
    // Populate Chips for department
    populateChips(dept);
  });

  // Handle Send Button
  chatSend.addEventListener('click', handleUserSend);
  chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleUserSend();
  });

  // Chip clicking delegation
  chatChipsContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.chat-chip');
    if (!chip) return;
    chatInput.value = chip.textContent;
    handleUserSend();
  });

  function handleUserSend() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Render User Message
    addUserMessage(query);
    chatInput.value = '';

    // Show Typing Indicator
    showTypingIndicator();

    // Simulate Backend Search & Response after 1200ms
    setTimeout(() => {
      hideTypingIndicator();
      processChatQuery(query);
    }, 1200);
  }

  function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'chat-msg user';
    div.textContent = text;
    chatBody.appendChild(div);
    scrollChat();
  }

  function addBotMessage(htmlContent, citation = null) {
    const div = document.createElement('div');
    div.className = 'chat-msg bot';
    
    // Simple markdown to HTML conversion for bold/code
    let formatted = htmlContent
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code class="inline-code">$1</code>');
      
    div.innerHTML = `<div>${formatted}</div>`;

    if (citation) {
      const citeCard = document.createElement('div');
      citeCard.className = 'chat-citations';
      citeCard.innerHTML = `
        <div class="citation-card">
          📖 Citations: <strong>${citation.doc}</strong> (Page ${citation.page}) | Match Score: ${(citation.score * 100).toFixed(0)}%
          <div class="citation-excerpt">
            <strong>Excerpt from ${citation.doc}:</strong><br>
            "${citation.answer.substring(0, 150)}..."
          </div>
        </div>
      `;
      div.appendChild(citeCard);
    }

    // Add feedback ratings buttons
    const feedback = document.createElement('div');
    feedback.className = 'feedback-actions';
    feedback.innerHTML = `
      <span>Was this helpful?</span>
      <button class="feedback-btn like" onclick="rateMessage(this, true)">👍</button>
      <button class="feedback-btn dislike" onclick="rateMessage(this, false)">👎</button>
    `;
    div.appendChild(feedback);

    chatBody.appendChild(div);
    scrollChat();
  }

  function showTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'chat-msg bot typing-container';
    div.id = 'botTyping';
    div.innerHTML = `
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    `;
    chatBody.appendChild(div);
    scrollChat();
  }

  function hideTypingIndicator() {
    const indicator = document.getElementById('botTyping');
    if (indicator) indicator.remove();
  }

  function scrollChat() {
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function populateChips(department) {
    chatChipsContainer.innerHTML = '';
    
    const defaults = {
      "Service & Maintenance": ["Model 1 maintenance schedule", "What is covered in warranty?", "Book a service booking"],
      "Insurance & Claims": ["Bumper to bumper coverage", "How to submit insurance claim?", "Is windscreen glass covered?"],
      "Spare Parts": ["Wiper motor pricing", "Where are spares manufactured?", "Check stock for alloy wheels"],
      "Roadside Assistance": ["Emergency towing phone number", "Breakdown on highway helpline", "Flat tire replacement cost"],
      "QA New Model Development": ["Checklist score required to pass", "DRBFM WIP template", "How QA reviews model approval"]
    };

    const chips = defaults[department] || ["What is warranty?", " roadside towing", "Spares pricing"];
    chips.forEach(text => {
      const chip = document.createElement('div');
      chip.className = 'chat-chip';
      chip.textContent = text;
      chatChipsContainer.appendChild(chip);
    });
  }

  function processChatQuery(query) {
    const qLower = query.toLowerCase();
    
    // Find matching FAQ from our local simulation DB
    let bestMatch = null;
    let maxSim = 0;
    
    MOCK_FAQS.forEach(faq => {
      const qTerms = faq.question.toLowerCase().split(' ');
      let matches = 0;
      qTerms.forEach(term => {
        if (qLower.includes(term)) matches++;
      });
      const similarity = matches / qTerms.length;
      if (similarity > maxSim) {
        maxSim = similarity;
        bestMatch = faq;
      }
    });

    // Semantic threshold simulation (0.45 threshold)
    if (maxSim >= 0.45 && bestMatch) {
      addBotMessage(bestMatch.answer, {
        doc: bestMatch.doc,
        page: bestMatch.page,
        score: bestMatch.score,
        answer: bestMatch.answer
      });
    } else {
      // Unanswered log gap simulation
      addBotMessage("I couldn't find a confident answer in our database. I have recorded your query as a **knowledge gap** for our team to review.");
      logGapInDashboard(query);
    }
  }

  // Triggered when thumbs up/down is clicked
  window.rateMessage = function(btn, isPositive) {
    // Disable sibling button and style active rating
    const parent = btn.parentElement;
    parent.querySelectorAll('.feedback-btn').forEach(b => {
      b.disabled = true;
      b.style.opacity = 0.5;
    });
    btn.classList.add('active');
    btn.style.opacity = 1;

    if (!isPositive) {
      ratingFailureCount++;
      if (ratingFailureCount >= 1) {
        showEscalationModal();
      }
    }
  };

  // Build welcome
  deptSelect.dispatchEvent(new Event('change'));
}

// Show the customer support escalation modal
function showEscalationModal() {
  // Create overlay modal dynamically
  const modal = document.createElement('div');
  modal.id = 'escalationModal';
  modal.style.position = 'fixed';
  modal.style.inset = '0';
  modal.style.background = 'rgba(0, 0, 0, 0.6)';
  modal.style.zIndex = '1000';
  modal.style.display = 'flex';
  modal.style.alignItems = 'center';
  modal.style.justifyContent = 'center';
  modal.style.backdropFilter = 'blur(4px)';

  modal.innerHTML = `
    <div class="login-card" style="width: 380px; background: var(--bg-card); position: relative">
      <h3 style="margin-top: 0">Support Escalation</h3>
      <p style="font-size:12.5px; color:var(--text-secondary); margin-bottom: 16px">You gave a negative rating. Would you like to escalate your query to the QA department?</p>
      
      <div class="form-group">
        <label>Your Name</label>
        <input type="text" id="escName" placeholder="Anil Mehta" value="Anil Mehta">
      </div>
      <div class="form-group">
        <label>Email Address</label>
        <input type="email" id="escEmail" placeholder="anil@gmail.com" value="anil@gmail.com">
      </div>
      <div class="form-group">
        <label>Phone Number</label>
        <input type="text" id="escPhone" placeholder="0999999999" value="9999999999">
      </div>
      <div class="form-group">
        <label>Query Reason</label>
        <input type="text" id="escReason" value="Warranty terms for Wiper blades are unclear in standard documentation.">
      </div>

      <div style="display: flex; gap: 8px; margin-top: 20px">
        <button class="btn-primary" style="background:var(--border); color:var(--text)" onclick="closeEscalationModal()">Cancel</button>
        <button class="btn-primary" onclick="submitEscalationForm()">Submit Escalation</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

window.closeEscalationModal = function() {
  const modal = document.getElementById('escalationModal');
  if (modal) modal.remove();
};

window.submitEscalationForm = function() {
  const name = document.getElementById('escName').value;
  const email = document.getElementById('escEmail').value;
  const phone = document.getElementById('escPhone').value;
  const reason = document.getElementById('escReason').value;

  const ticketId = 'tkt_' + Math.random().toString(36).substr(2, 9);
  
  // Log into mock dashboard data
  const ticket = {
    id: ticketId,
    name: name,
    email: email,
    phone: phone,
    query: reason,
    department: document.getElementById('chatDeptSelect').value,
    timestamp: new Date().toISOString().replace('T', ' ').substring(0,19),
    status: 'New'
  };

  addTicketToDashboard(ticket);
  
  alert(`Escalation ticket submitted successfully!\nTicket ID: ${ticketId}`);
  closeEscalationModal();
};

// ==========================================
// 8. INTERACTIVE ADMIN DASHBOARD & CRUD SIMULATION
// ==========================================
const MOCK_TICKETS = [
  { id: "tkt_1785361425891", name: "Anil Mehta", email: "anil@gmail.com", phone: "9999999999", query: "Periodic maintenance schedule details...", department: "Service & Maintenance", timestamp: "2026-08-04 15:45:00", status: "New" },
  { id: "tkt_8829103829102", name: "Shivam Sharma", email: "shivam@gmail.com", phone: "8888888888", query: "Need wiper blade PDF specification approval.", department: "QA New Model Development", timestamp: "2026-08-03 12:30:00", status: "In Progress" }
];

const MOCK_GAPS = [
  { query: "Why is the zero-dep rate high?", match: "What is zero-dep?", conf: 0.32, timestamp: "2026-08-04 15:30:12" },
  { query: "Wiper motor replacement steps", match: "Model 1 Wiper specifications", conf: 0.28, timestamp: "2026-08-04 14:15:22" }
];

const MOCK_AUDITS = [
  { id: "audit_405f7b517ad", timestamp: "2026-08-04 15:21:00", actor: "QA Administrator", role: "QA Admin", action: "faq.created", target: "faq_182dd3303195", details: "What is the warranty period?" },
  { id: "audit_991ba20f8c3", timestamp: "2026-08-04 12:10:00", actor: "Shivam Sharma", role: "QA", action: "document.approved", target: "doc_67b36f7e812d", details: "Model1_WiperSpecs.pdf approved" }
];

const MOCK_SETTINGS = {
  models: ["Model 1", "Model 2", "Model 3", "Model 4"],
  teams: ["Engineering Team 1", "Engineering Team 2", "Engineering Team 3"],
  categories: ["New Parts Details", "Approval of Part Details", "Design Review of New Parts"]
};

let activeFaqs = [...MOCK_FAQS];
let activeDocs = [
  { id: "doc_67b36f7e812d", name: "Model1_WiperSpecs.pdf", model: "Model 1", team: "Engineering Team 1", category: "New Parts Details", uploaded_at: "2026-08-04 12:00:00", revision: "R1", approval_state: "Approved", score: 80 }
];

function initMockAdmin() {
  // Authentication handler
  const loginForm = document.getElementById('loginForm');
  const loginGate = document.getElementById('loginGate');
  const adminMain = document.getElementById('adminMain');
  
  if (!loginForm || !loginGate || !adminMain) return;

  // Check existing token
  if (sessionStorage.getItem('autocare_portal_token')) {
    loginGate.style.display = 'none';
    adminMain.style.display = 'flex';
    renderDashboard();
  }

  loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;

    if (user === 'qa_admin' && pass === 'QAAdmin123!') {
      sessionStorage.setItem('autocare_portal_token', 'mock_admin_token_jwt_like');
      loginGate.style.display = 'none';
      adminMain.style.display = 'flex';
      renderDashboard();
    } else {
      alert('Invalid username or password. Check credentials in user guide.');
    }
  });

  // Handle Admin Dashboard Tabs routing
  const adminLinks = document.querySelectorAll('.admin-sidebar-link');
  adminLinks.forEach(link => {
    link.addEventListener('click', () => {
      adminLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      const target = link.dataset.tab;
      switchAdminTab(target);
    });
  });
}

function switchAdminTab(tab) {
  const containers = document.querySelectorAll('.admin-tab-container');
  containers.forEach(c => c.style.display = 'none');
  
  const targetContainer = document.getElementById(`admin-tab-${tab}`);
  if (targetContainer) {
    targetContainer.style.display = 'block';
    
    // Tab-specific rendering
    if (tab === 'overview') renderDashboard();
    if (tab === 'faqs') renderFaqManager();
    if (tab === 'docs') renderDocLibrary();
    if (tab === 'tickets') renderTickets();
    if (tab === 'gaps') renderGapLogs();
    if (tab === 'audits') renderAudits();
  }
}

function renderDashboard() {
  // Update Live Counts
  document.getElementById('countFaq').textContent = activeFaqs.length;
  document.getElementById('countDocs').textContent = activeDocs.length;
  document.getElementById('countTickets').textContent = MOCK_TICKETS.filter(t => t.status !== 'Resolved').length;
  document.getElementById('countGaps').textContent = MOCK_GAPS.length;

  // Build Mizen Boushi pipeline progress bars
  const pipeline = document.getElementById('mizenPipeline');
  if (pipeline) {
    pipeline.innerHTML = `
      <div class="mizen-model-row">
        <div class="mizen-model-info">
          <span>Model 1 Wiper/Specs Approval</span>
          <strong>80% Complete</strong>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: 80%"></div></div>
      </div>
      <div class="mizen-model-row">
        <div class="mizen-model-info">
          <span>Model 2 Engine Mount Drawings</span>
          <strong>45% Complete</strong>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: 45%; background: var(--accent-orange)"></div></div>
      </div>
      <div class="mizen-model-row">
        <div class="mizen-model-info">
          <span>Model 3 Body Panels Review</span>
          <strong>15% Complete</strong>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: 15%; background: var(--accent-red)"></div></div>
      </div>
    `;
  }
}

function renderFaqManager() {
  const tbody = document.getElementById('faqTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';
  activeFaqs.forEach((faq, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${faq.question}</strong></td>
      <td>${faq.answer.substring(0, 80)}...</td>
      <td><span class="badge badge-accent">${faq.department}</span></td>
      <td>
        <button class="feedback-btn" style="color:var(--accent-red); border-color:var(--border)" onclick="deleteFaq(${index})">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Set up categories in dropdowns
  const deptSelect = document.getElementById('faqDept');
  if (deptSelect && deptSelect.options.length <= 1) {
    const depts = ["Service & Maintenance", "Insurance & Claims", "Spare Parts", "Roadside Assistance", "QA New Model Development"];
    depts.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d;
      deptSelect.appendChild(opt);
    });
  }
}

window.addNewFaq = function() {
  const q = document.getElementById('faqQuestion').value.trim();
  const a = document.getElementById('faqAnswer').value.trim();
  const dept = document.getElementById('faqDept').value;

  if (!q || !a || !dept) {
    alert("Please fill in all FAQ fields.");
    return;
  }

  const newFaq = {
    question: q,
    answer: a,
    department: dept,
    score: 1.0,
    doc: "manual",
    page: 1,
    category: "General"
  };

  activeFaqs.unshift(newFaq);
  
  // Log audit
  logAudit("faq.created", `FAQ added: "${q}"`);
  
  // Clear forms & render
  document.getElementById('faqQuestion').value = '';
  document.getElementById('faqAnswer').value = '';
  renderFaqManager();
  renderDashboard();
  alert("FAQ added successfully! Embed indices rebuilt.");
};

window.deleteFaq = function(index) {
  if (confirm("Are you sure you want to delete this FAQ?")) {
    const removed = activeFaqs.splice(index, 1)[0];
    logAudit("faq.deleted", `FAQ deleted: "${removed.question}"`);
    renderFaqManager();
    renderDashboard();
  }
};

function renderDocLibrary() {
  const tbody = document.getElementById('docTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';
  activeDocs.forEach((doc, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${doc.name}</strong></td>
      <td>${doc.model}</td>
      <td>${doc.team}</td>
      <td><span class="status-badge"><span class="status-dot"></span> ${doc.approval_state}</span></td>
      <td>${doc.score}/100</td>
      <td>
        <button class="feedback-btn" style="color:var(--accent-red); border-color:var(--border)" onclick="deleteDoc(${index})">Remove</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.deleteDoc = function(index) {
  if (confirm("Are you sure you want to remove this document from index?")) {
    const removed = activeDocs.splice(index, 1)[0];
    logAudit("document.deleted", `Document removed: "${removed.name}"`);
    renderDocLibrary();
    renderDashboard();
  }
};

// Simulate PDF uploading, verifying headers, scoring
window.simulatePdfUpload = function() {
  const fileInput = document.getElementById('docFileInput');
  const model = document.getElementById('docModel').value;
  const team = document.getElementById('docTeam').value;
  const category = document.getElementById('docCategory').value;

  if (!fileInput.files.length) {
    alert("Please select a PDF file first.");
    return;
  }

  const filename = fileInput.files[0].name;
  
  // Structural checklist check mockup
  const checklistBox = document.getElementById('uploadChecklistStatus');
  checklistBox.style.display = 'block';
  
  // Simulate checking 5 pointers (Introduction, Methodology, Results, Conclusion, Safety Warning)
  // Wiper specs might lack Methodology but contain Safety and Intro, scoring 80/100
  let points = 0;
  let items = [
    { label: "Introduction segment found", pass: true },
    { label: "Methodology description found", pass: false },
    { label: "Results section found", pass: true },
    { label: "Conclusion validation found", pass: true },
    { label: "Safety Warning warnings found", pass: true }
  ];

  checklistBox.innerHTML = `<h4>Running Quality Checklist on ${filename}...</h4>`;
  
  items.forEach((item, idx) => {
    setTimeout(() => {
      const p = document.createElement('div');
      p.className = 'checklist-item';
      p.innerHTML = `
        <span class="checklist-icon ${item.pass ? 'pass' : 'fail'}">${item.pass ? '✓' : '✗'}</span>
        <span>${item.label}</span>
      `;
      checklistBox.appendChild(p);
      if (item.pass) points += 20;

      if (idx === items.length - 1) {
        // Render score
        const scoreDiv = document.createElement('div');
        scoreDiv.style.marginTop = '12px';
        scoreDiv.style.fontWeight = '700';
        scoreDiv.innerHTML = `Compliance Score: <span style="color:${points >= 60 ? 'var(--accent-green)' : 'var(--accent-red)'}">${points}/100</span>`;
        checklistBox.appendChild(scoreDiv);

        if (points >= 60) {
          // Add document to list
          const newDoc = {
            id: 'doc_' + Math.random().toString(36).substr(2, 9),
            name: filename,
            model: model || 'Model 1',
            team: team || 'Engineering Team 1',
            category: category || 'New Parts Details',
            uploaded_at: new Date().toISOString().replace('T', ' ').substring(0,19),
            revision: 'R1',
            approval_state: 'Approved',
            score: points
          };
          activeDocs.unshift(newDoc);
          logAudit("document.uploaded", `PDF document parsed: "${filename}"`);
          setTimeout(() => {
            renderDocLibrary();
            renderDashboard();
            alert("Compliance pass! Document ingested and vectors updated.");
            checklistBox.style.display = 'none';
            fileInput.value = '';
          }, 1500);
        } else {
          alert("Compliance fail! PDF score must be 60 or above to ingest.");
        }
      }
    }, (idx + 1) * 300);
  });
};

function renderTickets() {
  const tbody = document.getElementById('ticketTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';
  MOCK_TICKETS.forEach((t, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${t.id}</strong></td>
      <td>${t.name}</td>
      <td><span class="badge">${t.department}</span></td>
      <td>${t.query}</td>
      <td><span class="badge ${t.status === 'Resolved' ? 'badge-green' : 'badge-orange'}">${t.status}</span></td>
      <td>
        <button class="feedback-btn" onclick="toggleTicketStatus(${index})">Resolve</button>
        <button class="feedback-btn" style="color:var(--accent-red); border-color:var(--border)" onclick="deleteTicket(${index})">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.toggleTicketStatus = function(index) {
  const t = MOCK_TICKETS[index];
  t.status = t.status === 'Resolved' ? 'In Progress' : 'Resolved';
  logAudit("ticket.updated", `Ticket ${t.id} set to ${t.status}`);
  renderTickets();
  renderDashboard();
};

window.deleteTicket = function(index) {
  if (confirm("Permanently delete support ticket?")) {
    const removed = MOCK_TICKETS.splice(index, 1)[0];
    logAudit("ticket.deleted", `Ticket deleted: ${removed.id}`);
    renderTickets();
    renderDashboard();
  }
};

function renderGapLogs() {
  const tbody = document.getElementById('gapTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';
  MOCK_GAPS.forEach((gap, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>"${gap.query}"</strong></td>
      <td>"${gap.match}"</td>
      <td><span class="badge badge-red">${gap.conf.toFixed(2)}</span></td>
      <td>
        <button class="feedback-btn" style="border-color:var(--accent); color:var(--accent)" onclick="resolveGap(${index})">Resolve (Add FAQ)</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.resolveGap = function(index) {
  const gap = MOCK_GAPS[index];
  
  // Pre-fill FAQ form and switch tab
  document.getElementById('faqQuestion').value = gap.query;
  document.getElementById('faqAnswer').value = `This answer resolves the gap query: "${gap.query}". Add details here.`;
  
  // Switch to FAQs tab
  const faqLink = Array.from(document.querySelectorAll('.admin-sidebar-link')).find(l => l.dataset.tab === 'faqs');
  if (faqLink) faqLink.click();

  // Remove gap
  MOCK_GAPS.splice(index, 1);
};

function renderAudits() {
  const tbody = document.getElementById('auditTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';
  MOCK_AUDITS.forEach(a => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${a.timestamp}</td>
      <td><strong>${a.actor}</strong> (${a.role})</td>
      <td><span class="badge">${a.action}</span></td>
      <td>${a.details}</td>
    `;
    tbody.appendChild(tr);
  });
}

function logAudit(action, details) {
  MOCK_AUDITS.unshift({
    id: 'audit_' + Math.random().toString(36).substr(2, 9),
    timestamp: new Date().toISOString().replace('T', ' ').substring(0,19),
    actor: 'QA Administrator',
    role: 'QA Admin',
    action: action,
    details: details
  });
}

// Integration interface to connect client UI chatbot to admin dashboard
function logGapInDashboard(query) {
  MOCK_GAPS.push({
    query: query,
    match: "General AutoCare FAQs",
    conf: 0.18,
    timestamp: new Date().toISOString().replace('T', ' ').substring(0,19)
  });
  
  // Re-render dashboard statistics if visible
  if (document.getElementById('admin-tab-overview') && document.getElementById('admin-tab-overview').style.display !== 'none') {
    renderDashboard();
  }
}

function addTicketToDashboard(ticket) {
  MOCK_TICKETS.unshift(ticket);
  logAudit("ticket.created", `Escalation ticket submitted: "${ticket.id}"`);
  
  // Re-render dashboard stats/tickets if visible
  renderDashboard();
  if (document.getElementById('admin-tab-tickets') && document.getElementById('admin-tab-tickets').style.display !== 'none') {
    renderTickets();
  }
}

// Admin logout
window.logoutAdmin = function() {
  sessionStorage.removeItem('autocare_portal_token');
  const loginGate = document.getElementById('loginGate');
  const adminMain = document.getElementById('adminMain');
  if (loginGate && adminMain) {
    loginGate.style.display = 'flex';
    adminMain.style.display = 'none';
  }
};
