(() => {
  document.body.insertAdjacentHTML("beforeend",`<div class="portal-auth-gate" id="portalAuthGate"><form class="portal-login-card" id="portalLoginForm"><div class="portal-login-mark">M</div><h2>Sign in to AutoCare</h2><p>Your role controls document contribution and review access.</p><label>Username<input id="portalUsername" autocomplete="username" required></label><label>Password<input id="portalPassword" type="password" autocomplete="current-password" required></label><button type="submit">Sign in</button><div class="portal-login-error" id="portalLoginError"></div><p class="portal-role-note">Engineering and QA can submit documents. Production and Parts Quality have read-only access.</p></form></div>`);
  const gate=document.getElementById("portalAuthGate"),form=document.getElementById("portalLoginForm"),error=document.getElementById("portalLoginError");
  const showGate=message=>{document.documentElement.classList.add("portal-auth-pending");gate.classList.add("open");if(message){error.textContent=message;error.style.display="block"}};
  const hideGate=()=>{gate.classList.remove("open");document.documentElement.classList.remove("portal-auth-pending");error.style.display="none"};
  const populatePortalConfig=async()=>{
    const response=await fetch(`${API_BASE}/api/config`,{headers:portalAuthHeaders()});if(!response.ok)return;
    const config=await response.json();
    [["portalDocModel",config.models],["portalDocTeam",config.teams],["portalDocCategory",config.categories]].forEach(([id,values])=>{const select=document.getElementById(id);select.innerHTML=values.map(value=>`<option>${escapeHtml(value)}</option>`).join("")});
    document.getElementById("dataEntryRoleCopy").textContent=portalUser.role==="Engineering"&&config.engineering_upload_requires_qa_approval?"Engineering uploads are submitted to QA for approval before publication.":"Your upload permission allows documents to be added to the QA library.";
  };
  const applyUser=user=>{
    portalUser=user;
    document.querySelectorAll(".role-upload-only").forEach(element=>element.hidden=!user.permissions.includes("upload"));
    const profile=document.querySelector(".user-profile");
    if(profile){
      profile.querySelector(".profile-avatar").textContent=user.department==="Parts Quality"?"PQ":user.department.slice(0,2).toUpperCase();
      profile.querySelector(".profile-name").textContent=user.name;
      profile.querySelector(".profile-role").textContent=`${user.department} · ${user.role}`;
      if(!profile.querySelector(".profile-signout"))profile.insertAdjacentHTML("beforeend",`<button class="profile-signout" type="button" title="Sign out">↪</button>`);
      profile.querySelector(".profile-signout").onclick=()=>{sessionStorage.removeItem("autocare_portal_token");portalToken="";portalUser=null;showGate()};
    }
    const adminLink=document.querySelector('.sidebar-footer a[href="admin.html"]');
    if(adminLink)adminLink.style.display=user.role==="QA Admin"?"flex":"none";
    populatePortalConfig();
  };
  const verify=async()=>{
    if(!portalToken){showGate();return}
    try{
      const response=await fetch(`${API_BASE}/api/auth/me`,{headers:portalAuthHeaders()});
      if(!response.ok)throw new Error();
      const data=await response.json();applyUser(data.user);hideGate();await loadKb();window.renderWorkspace?.();
    }catch{sessionStorage.removeItem("autocare_portal_token");portalToken="";showGate("Your session expired. Please sign in again.")}
  };
  form.addEventListener("submit",async event=>{
    event.preventDefault();error.style.display="none";
    const button=form.querySelector("button");button.disabled=true;button.textContent="Signing in…";
    try{
      const response=await fetch(`${API_BASE}/api/auth/login`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:document.getElementById("portalUsername").value,password:document.getElementById("portalPassword").value})});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"Sign-in failed.");
      portalToken=data.token;sessionStorage.setItem("autocare_portal_token",portalToken);applyUser(data.user);hideGate();form.reset();await loadKb();
    }catch(err){error.textContent=err.message;error.style.display="block"}finally{button.disabled=false;button.textContent="Sign in"}
  });
  const uploadZone=document.getElementById("portalUploadZone");
  let currentUploadDraftId = null;
  const chooseFile=()=>{const input=document.createElement("input");input.type="file";input.accept=".pdf";input.onchange=()=>uploadPortalDocument(input.files[0]);input.click()};

  /* ── Build Confidence Score Card HTML ── */
  function buildScoreCard(data) {
    const score = typeof data.score === 'number' ? data.score : 0;
    const docName = data.document?.name || 'Document';
    const docId = data.document?.id || '';
    const missing = data.missing_pointers || [];
    const found = data.found_pointers || [];
    const isPass = score >= 60;
    // SVG ring calculations
    const radius = 34;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (score / 100) * circumference;
    const ringClass = score >= 60 ? 'score-pass' : (score >= 30 ? 'score-warn' : 'score-fail');
    const statusClass = isPass ? 'pass' : (score >= 30 ? 'warn' : 'fail');
    const statusLabel = isPass ? 'Ready to submit' : 'Needs improvement';
    const statusDesc = isPass
      ? 'This document meets the minimum confidence threshold and can be submitted for QA approval.'
      : `Score is too low to submit for approval (minimum 60/100 required). Please correct and upload again.`;

    let pointersHtml = '';
    if (found.length || missing.length) {
      pointersHtml = `<div class="score-card-pointers">
        <span class="score-card-pointers-title">Checklist pointers</span>
        <ul class="score-card-pointers-list">
          ${found.map(p => `<li class="found"><span class="ptr-icon">✓</span>${escapeHtml(p)}</li>`).join('')}
          ${missing.map(p => `<li class="missing"><span class="ptr-icon">✕</span>${escapeHtml(p)}</li>`).join('')}
        </ul>
      </div>`;
    }

    return `<div class="score-card">
      <div class="score-card-header">
        <div class="score-ring-wrap">
          <svg viewBox="0 0 82 82">
            <circle class="score-ring-bg" cx="41" cy="41" r="${radius}"/>
            <circle class="score-ring-fg ${ringClass}" cx="41" cy="41" r="${radius}"
              stroke-dasharray="${circumference}" stroke-dashoffset="${circumference}"
              data-target-offset="${offset}"/>
          </svg>
          <div class="score-ring-label">
            <span class="score-ring-value" data-target="${score}">0</span>
            <span class="score-ring-unit">/100</span>
          </div>
        </div>
        <div class="score-card-info">
          <span class="score-card-filename" title="${escapeHtml(docName)}">${escapeHtml(docName)}</span>
          <span class="score-card-status ${statusClass}"><span class="score-card-status-dot"></span>${statusLabel}</span>
          <p class="score-card-desc">${statusDesc}</p>
        </div>
      </div>
      ${pointersHtml}
      <div class="score-card-actions">
        <button class="score-btn score-btn-draft" id="scoreCardDraftBtn" data-doc-id="${escapeHtml(docId)}">Save as Draft</button>
        <button class="score-btn score-btn-submit" id="scoreCardSubmitBtn" data-doc-id="${escapeHtml(docId)}" ${isPass ? '' : 'disabled'}>Submit for Approval</button>
        <span class="score-card-toast" id="scoreCardToast"></span>
      </div>
    </div>`;
  }

  /* ── Animate the score ring on render ── */
  function animateScoreCard() {
    const fg = document.querySelector('.score-ring-fg[data-target-offset]');
    const valueEl = document.querySelector('.score-ring-value[data-target]');
    if (!fg || !valueEl) return;
    const targetOffset = parseFloat(fg.dataset.targetOffset);
    const targetVal = parseInt(valueEl.dataset.target, 10);
    // trigger animation after a micro-delay
    requestAnimationFrame(() => {
      fg.style.strokeDashoffset = targetOffset;
      // count-up the number
      let current = 0;
      const step = Math.max(1, Math.ceil(targetVal / 40));
      const interval = setInterval(() => {
        current = Math.min(current + step, targetVal);
        valueEl.textContent = current;
        if (current >= targetVal) clearInterval(interval);
      }, 22);
    });
  }

  /* ── Wire score card action buttons ── */
  function wireScoreCardButtons() {
    const draftBtn = document.getElementById('scoreCardDraftBtn');
    const submitBtn = document.getElementById('scoreCardSubmitBtn');
    const toast = document.getElementById('scoreCardToast');

    draftBtn?.addEventListener('click', () => {
      toast.textContent = '✓ Saved as draft';
      toast.classList.add('visible');
      setTimeout(() => toast.classList.remove('visible'), 3000);
    });

    submitBtn?.addEventListener('click', async () => {
      const docId = submitBtn.dataset.docId;
      if (!docId) return;
      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting…';
      try {
        const res = await fetch(`${API_BASE}/api/documents/${docId}/submit`, {
          method: 'PUT',
          headers: { ...portalAuthHeaders(), 'Content-Type': 'application/json' }
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || 'Submission failed.');
        toast.textContent = `✓ ${result.approval_state || 'Submitted'}`;
        toast.classList.add('visible');
        submitBtn.textContent = result.approval_state || 'Submitted';
        // Update status badge
        const badge = document.querySelector('.score-card-status');
        if (badge) {
          badge.className = 'score-card-status pass';
          badge.innerHTML = '<span class="score-card-status-dot"></span>' + escapeHtml(result.approval_state || 'Submitted');
        }
        currentUploadDraftId = null;
        await loadKb();
      } catch (err) {
        toast.textContent = '✕ ' + err.message;
        toast.style.color = '#ff453a';
        toast.classList.add('visible');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit for Approval';
        setTimeout(() => { toast.classList.remove('visible'); toast.style.color = ''; }, 4000);
      }
    });
  }

  /* ── Upload handler ── */
  const uploadPortalDocument=async file=>{
    const resultEl=document.getElementById("portalUploadResult");
    if(!portalUser?.permissions.includes("upload"))return;
    if(!file||!file.name.toLowerCase().endsWith(".pdf")){resultEl.innerHTML=`<div class="score-card" style="padding:18px 24px"><p style="margin:0;color:#ff453a;font-weight:600;font-size:12px">Please select a PDF file.</p></div>`;return}
    uploadZone.style.pointerEvents="none";uploadZone.innerHTML=`<strong>Reading ${escapeHtml(file.name)}…</strong><span>Classifying and indexing the document.</span>`;
    const body=new FormData();body.append("file",file);body.append("model",document.getElementById("portalDocModel").value);body.append("team",document.getElementById("portalDocTeam").value);body.append("category",document.getElementById("portalDocCategory").value);
    // If we have a current draft, auto-replace it
    const replaceId = currentUploadDraftId || document.getElementById("portalReplaceDoc")?.value;
    if(replaceId) body.append("replace_document_id",replaceId);
    try{
      const response=await fetch(`${API_BASE}/api/documents/upload`,{method:"POST",headers:portalAuthHeaders(),body});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"Upload failed.");
      // Track the draft ID for subsequent re-uploads
      if (data.document?.id) currentUploadDraftId = data.document.id;
      // Render the score card
      resultEl.innerHTML = buildScoreCard(data);
      animateScoreCard();
      wireScoreCardButtons();
      await loadKb();
    }catch(err){resultEl.innerHTML=`<div class="score-card" style="padding:18px 24px"><p style="margin:0;color:#ff453a;font-weight:600;font-size:12px">${escapeHtml(err.message)}</p></div>`}finally{uploadZone.style.pointerEvents="";uploadZone.innerHTML=`<span class="portal-upload-icon" aria-hidden="true">↑</span><strong>Select or drop a PDF</strong><span>Maximum 15 MB · Engineering submissions go to QA approval.</span><span class="portal-upload-action">Choose PDF</span>`}
  };
  uploadZone.addEventListener("click",chooseFile);uploadZone.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();chooseFile()}});
  ["dragenter","dragover","dragleave","drop"].forEach(name=>uploadZone.addEventListener(name,event=>{event.preventDefault();event.stopPropagation()}));
  uploadZone.addEventListener("drop",event=>uploadPortalDocument(event.dataTransfer.files[0]));
  verify();
})();