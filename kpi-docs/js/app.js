// KPI Documentation System Logic & Telemetry Replicas

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initTabSwitch();
  initReplicaInspector();
  initSearch();
});

// ==========================================
// 1. THEME CONTROLLER
// ==========================================
function initTheme() {
  const themeBtns = document.querySelectorAll('.rep-theme-btn');
  const currentTheme = localStorage.getItem('autocare_docs_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', currentTheme);
  
  themeBtns.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === currentTheme);
    btn.addEventListener('click', () => {
      themeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const theme = btn.dataset.theme;
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('autocare_docs_theme', theme);
    });
  });
}

// ==========================================
// 2. MAIN SWITCHER (REPLICA VIEW vs TOC VIEW)
// ==========================================
function initTabSwitch() {
  const toggleBtns = document.querySelectorAll('.tab-toggle-btn');
  const replicaView = document.getElementById('view-replica');
  const tocView = document.getElementById('view-toc');

  toggleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      toggleBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      const tab = btn.dataset.tab;
      if (tab === 'replica') {
        replicaView.style.display = 'flex';
        tocView.classList.add('hidden');
      } else {
        replicaView.style.display = 'none';
        tocView.classList.remove('hidden');
        renderTOC();
      }
    });
  });
}

// ==========================================
// 3. KPI CATALOG DOCUMENTATION DATA
// ==========================================
const KPI_CATALOG = {
  "qa-queries": {
    title: "QA Queries Today",
    subtitle: "Real-time query volume monitoring metric",
    purpose: "Measures daily operator traffic and system engagement levels on the factory floor.",
    formula: "QA Queries = Total POST requests logged in database_activity.json since 00:00:00 local time.",
    included: "All valid customer and factory operator chat queries routed to the AI matching pipeline.",
    excluded: "API status health checks, administrative search filtering, and failed auth logins.",
    business: "Management uses this metric to calculate operational support agent workload savings. High spikes indicate training gaps or drawing ambiguities on specific car models.",
    sla: "Daily limits scale up to 5,000 queries/day. Alerts route to IT if backend query execution latency exceeds 150ms.",
    questions: [
      { q: "Do short rephrased search queries count towards this tally?", a: "Yes. Every request processed by the vector engine represents a query and is recorded." },
      { q: "Is query volume cached?", a: "No. The dashboard refreshes the count directly from activity database logs every 60 seconds." }
    ]
  },
  "doc-grounded": {
    title: "Document Grounded Rate",
    subtitle: "Retrieval semantic matching telemetry",
    purpose: "Tracks search precision by calculating queries answered from verified quality specifications.",
    formula: "DGR = (Grounded Queries / Total Queries) * 100",
    included: "Chat responses where matched similarity score is ≥ 0.45 threshold against index matrices.",
    excluded: "Queries ending in fallbacks, support ticket escalations, or manual offline routing.",
    business: "Ensures customer responses are derived strictly from approved drawing PDF evidence to guarantee compliance.",
    sla: "Target SLA is ≥ 85% Grounded Rate. Falling below 80% flags QA to review gap query logs.",
    questions: [
      { q: "What happens when grounding falls below target?", a: "It indicates a documentation gap. QA engineers resolve unresolved queries in gap reviews." },
      { q: "Are FAQ matches counted as grounded?", a: "Yes. Verified FAQ responses are categorized as grounded responses." }
    ]
  },
  "open-tickets": {
    title: "Open QA Tickets",
    subtitle: "Active customer and line issue tracker",
    purpose: "Tracks unresolved customer support escalations or factory drawing feedback tickets.",
    formula: "Open Tickets = Count of ticket objects in escalations.json where status != 'Resolved'.",
    included: "New and In-Progress support tickets submitted via chat interface triggers.",
    excluded: "Archived or successfully resolved tickets.",
    business: "Monitors unresolved engineering drawing disputes to enforce corrective action procedures.",
    sla: "All ticket tickets must transition to 'Resolved' status within 48 hours.",
    questions: [
      { q: "Who can resolve or change ticket status?", a: "Only QA Admins possess write credentials to transition status keys." },
      { q: "What triggers automatic escalation logging?", a: "Three consecutive query matches below 0.45 similarity threshold, or negative rating submission." }
    ]
  },
  "approved-docs": {
    title: "Approved Documents Index",
    subtitle: "Index volume and grounding pool depth",
    purpose: "Measures the size of the active document library and vector search coverage.",
    formula: "Approved Docs = Count of records in documents.json where approval_state == 'Approved'.",
    included: "QA-approved PDF specifications and design guidelines injected into active matrices.",
    excluded: "Draft drawing uploads, pending engineering requests, or superseded file revisions.",
    business: "Helps management audit search coverage depth across engineering model parameters.",
    sla: "Requires 100% drawing metadata compliance check scoring before inclusion.",
    questions: [
      { q: "Can a document search bypass QA approval?", a: "No. Only QA Admin approved documents are compiled into query matrix indices." }
    ]
  },
  "mizen-pipeline": {
    title: "Mizenboshi Pipeline Progress",
    subtitle: "Model approval completeness tracking widget",
    purpose: "Tracks QA document validation progress bars across target car models.",
    formula: "Model Progress % = (Approved Model Docs / Total Target Model Docs) * 100",
    included: "Ingested drawings passing the 60/100 structural checklist rules.",
    excluded: "General QA manuals or unassigned department documentation.",
    business: "Acts as a launch readiness tracker. Ensures no new vehicle production line commences without complete documentation coverage.",
    sla: "Must achieve 100% completion status before final model production clearance.",
    questions: [
      { q: "How are total target document limits calculated?", a: "Derived from model configs specified in configurations settings." }
    ]
  },
  "priority-table": {
    title: "Model System Priority Grid",
    subtitle: "Standard checklist priority mapping table",
    purpose: "Detailed overview of validation checkpoints matching priority levels 1-4.",
    formula: "Visual matrix mapping model states to priority badge levels.",
    included: "Model status (QA Review, WIP, Ingest, Planned), min section counts, and priority circles.",
    excluded: "Detailed document content snippets.",
    business: "Allows compliance auditors to isolate checklist deficiencies in specific engineering models.",
    sla: "All Priority 1 checklist parameters must be verified first without deviations.",
    questions: [
      { q: "What do the numbers inside the priority circles represent?", a: "Uncompleted check points. Zero represents complete compliance check verification." }
    ]
  },
  "work-queue": {
    title: "QA Work Queue",
    subtitle: "Urgent approvals and actions registry",
    purpose: "Isolates drawing uploads requiring immediate review and ticket actions exceeding standard SLA limits.",
    formula: "Alert counts based on upload timelines and ticket ages (overdue if unresolved > 48 hours).",
    included: "Drawings awaiting QA verification and tickets older than 48 hours.",
    excluded: "Approved documents or active tickets within standard SLA timelines.",
    business: "Acts as the administrative inbox, preventing approval bottlenecks in quality control workflows.",
    sla: "Awaiting files must be processed (Approve/Reject) within 24 hours.",
    questions: [
      { q: "Can engineers bypass the QA approval queue?", a: "No. If configurations require QA gates, drawings remain drafts until reviewed." }
    ]
  },
  "recently-added": {
    title: "Recently Ingested PDF Archive",
    subtitle: "Approved quality file previews",
    purpose: "Displays the latest drawings added to the system vector indices.",
    formula: "Sorted documents.json filtered by timestamp descending.",
    included: "Latest 4 approved drawing references.",
    excluded: "Draft specs or deleted drawing revisions.",
    business: "Enables operators to verify recent index updates and preview document headers.",
    sla: "Display updates instantly upon document approval."
  },
  "live-switch": {
    title: "Live Data Feed Status",
    subtitle: "Dashboard sync indicator",
    purpose: "Controls websocket simulation and real-time backend indexing status.",
    formula: "Checkbox toggle controlling active data polling triggers.",
    included: "WebSocket connection indicator green dot.",
    excluded: "Historical telemetry reporting configurations.",
    business: "Indicates active sync telemetry. Re-verifies live connectivity on factory screens."
  }
};

// ==========================================
// 4. INTERACTIVE REPLICA INSPECTOR ENGINE
// ==========================================
function initReplicaInspector() {
  const elements = document.querySelectorAll('.annotated-element');
  
  // Set default view on load
  inspectElement('qa-queries');

  elements.forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      
      // Update highlights
      elements.forEach(item => item.classList.remove('selected'));
      el.classList.add('selected');

      const target = el.dataset.target;
      inspectElement(target);
    });
  });
}

function inspectElement(targetKey) {
  const data = KPI_CATALOG[targetKey];
  const body = document.getElementById('inspectorBody');
  
  if (!data || !body) return;

  let questionsHtml = '';
  if (data.questions && data.questions.length > 0) {
    questionsHtml = `
      <div class="insp-qna">
        <h4 style="font-size:12.5px; text-transform:uppercase; color:var(--insp-accent); margin-bottom:12px">Common Presentation Q&A</h4>
        ${data.questions.map(q => `
          <div class="insp-qna-item">
            <div class="insp-q">❓ ${q.q}</div>
            <div class="insp-a">➡️ ${q.a}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  body.innerHTML = `
    <div class="insp-header">
      <div class="insp-title">${data.title}</div>
      <div class="insp-subtitle">${data.subtitle}</div>
    </div>
    <p><strong>Business Purpose:</strong> ${data.purpose}</p>
    <p><strong>Calculation Logic:</strong></p>
    <div class="insp-formula">${data.formula}</div>
    <ul class="insp-list">
      <li><strong>Included Data:</strong> ${data.included}</li>
      <li><strong>Excluded Data:</strong> ${data.excluded}</li>
      <li><strong>SLA & Guardrails:</strong> ${data.sla}</li>
    </ul>
    <p><strong>Management Decision Value:</strong> ${data.business}</p>
    ${questionsHtml}
  `;
}

// ==========================================
// 5. SEARCH IMPLEMENTATION
// ==========================================
function initSearch() {
  const search = document.getElementById('kpiSearchInput');
  if (!search) return;

  search.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    
    // Fallback switch to TOC view to show search results easily
    const tocBtn = Array.from(document.querySelectorAll('.tab-toggle-btn')).find(b => b.dataset.tab === 'toc');
    if (tocBtn && !tocBtn.classList.contains('active') && q.length > 0) {
      tocBtn.click();
    }

    renderTOC(q);
  });
}

// ==========================================
// 6. RENDER TOC (DOCS MODE)
// ==========================================
function renderTOC(query = '') {
  const grid = document.getElementById('tocGrid');
  if (!grid) return;

  grid.innerHTML = '';
  
  let keys = Object.keys(KPI_CATALOG);
  let matched = false;

  keys.forEach(key => {
    const data = KPI_CATALOG[key];
    if (query && !data.title.toLowerCase().includes(query) && !data.purpose.toLowerCase().includes(query)) {
      return;
    }

    matched = true;
    const card = document.createElement('div');
    card.className = 'toc-card';
    card.innerHTML = `
      <h3>${data.title}</h3>
      <p style="margin-bottom: 6px"><strong>Formula:</strong> <code>${data.formula}</code></p>
      <p>${data.purpose}</p>
    `;

    // Click on TOC card switches back to replica and inspects element
    card.addEventListener('click', () => {
      const repBtn = Array.from(document.querySelectorAll('.tab-toggle-btn')).find(b => b.dataset.tab === 'replica');
      if (repBtn) repBtn.click();
      
      const repEl = document.querySelector(`[data-target="${key}"]`);
      if (repEl) {
        repEl.click();
        repEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });

    grid.appendChild(card);
  });

  if (!matched) {
    grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; color:var(--dash-text-muted); padding:32px">No matching documentation elements found.</div>`;
  }
}
