const state = {
  role: "applicant",
  isAdmin: false,
  forceOffline: false,
  apiKey: sessionStorage.getItem("uniassist_gemini_key") || "",
  policiesCache: {},
  selectedProgram: "MCA",
};

const QUICK_PROMPTS = {
  applicant: [
    { text: "Eligibility criteria for MCA admission?", oos: false },
    { text: "Am I eligible for MCA with 58% in BCA and no Math in Class 12?", oos: false },
    { text: "Hostel fee structure?", oos: false },
    { text: "MCA tuition fee under PGCET quota?", oos: false },
    { text: "Merit scholarship slabs for 86% marks?", oos: false },
    { text: "Documents required for admission verification?", oos: false },
    { text: "Does the university offer scuba diving?", oos: true, adminOnly: true },
  ],
  student: [
    { text: "When is the exam schedule released?", oos: false },
    { text: "Minimum attendance requirement and condonation rules?", oos: false },
    { text: "How to apply for a bonafide certificate on ERP?", oos: false },
    { text: "No-Dues clearance procedure for graduating students?", oos: false },
    { text: "Hostel curfew timings and night out leave pass?", oos: false },
    { text: "Revaluation fee and answer-script photocopy deadline?", oos: false },
    { text: "Can I book a private helicopter tour in Bengaluru?", oos: true, adminOnly: true },
  ],
};

const PROGRAM_EXAMS = {
  MCA: ["PGCET", "KMAT", "DSAT"],
  MBA: ["PGCET", "KMAT", "CAT", "MAT", "XAT", "CMAT", "DSAT"],
  "B.Tech": ["KCET", "COMED-K", "JEE Main", "DSAT"],
  BCA: ["DSAT", "Direct / Merit"],
  "B.Sc.": ["DSAT", "Direct / Merit"],
};

const VIEW_META = {
  helpdesk: {
    title: "Virtual Helpdesk",
    subtitle: "Official answers verified against university admissions, fee, hostel & examination circulars",
  },
  estimator: {
    title: "Eligibility & Fee Estimator",
    subtitle: "Check your program eligibility, quota tuition fee & merit scholarship eligibility",
  },
  corpus: {
    title: "University Policies",
    subtitle: "Browse official admissions, fee, scholarship, hostel and examination circulars",
  },
  tickets: {
    title: "Escalation Tickets",
    subtitle: "Tier-2 counselor support queue for unindexed student inquiries",
  },
  benchmark: {
    title: "Benchmark & Diagnostics",
    subtitle: "Live 60-query retrieval evaluation, 6×6 confusion matrix & TC-01..TC-05 verification",
  },
};

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatInr(amount) {
  return "₹" + Number(amount || 0).toLocaleString("en-IN");
}

function formatAnswerHtml(rawText) {
  const escaped = escapeHtml(rawText || "");
  const lines = escaped.split(/\r?\n/);
  let html = "";
  let inList = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      continue;
    }

    let processed = line
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/_(.+?)_/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(
        /\[Policy Ref:\s*([A-Z0-9-]+)\]/gi,
        (_, pid) =>
          `<button type="button" class="policy-ref-btn" data-policy-id="${pid}">📄 Policy Ref: ${pid}</button>`
      );

    if (/^[-*•]\s+/.test(line)) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      processed = processed.replace(/^[-*•]\s+/, "");
      html += `<li>${processed}</li>`;
    } else {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      html += `<p>${processed}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

/* ---------------- Admin Mode Sync ---------------- */
function applyAdminVisibility() {
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.classList.toggle("hidden", !state.isAdmin);
  });

  const btn = document.getElementById("staffAccessBtn");
  const icon = document.getElementById("staffAccessIcon");
  const text = document.getElementById("staffAccessText");
  if (state.isAdmin) {
    btn.classList.add("unlocked");
    icon.textContent = "🔓";
    text.textContent = "Exit Admin Mode";
    document.getElementById("loadTc05Btn").textContent = "Load TC-05 Demo";
  } else {
    btn.classList.remove("unlocked");
    icon.textContent = "🔒";
    text.textContent = "Staff / Admin Login";
    document.getElementById("loadTc05Btn").textContent = "Sample MCA Check";
    document.getElementById("ingestPanel").classList.add("hidden");
    const activeView = document.querySelector(".view.active")?.id;
    if (activeView === "view-tickets" || activeView === "view-benchmark") {
      switchView("helpdesk");
    }
  }
  renderQuickChips();
}

/* ---------------- Navigation ---------------- */
function switchView(viewName) {
  if ((viewName === "tickets" || viewName === "benchmark") && !state.isAdmin) {
    return;
  }
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((sec) => {
    sec.classList.toggle("active", sec.id === `view-${viewName}`);
  });
  const meta = VIEW_META[viewName] || VIEW_META.helpdesk;
  document.getElementById("pageTitle").textContent = meta.title;
  document.getElementById("pageSubtitle").textContent = meta.subtitle;
  document.getElementById("sidebar").classList.remove("open");

  if (viewName === "corpus") loadPolicies();
  if (viewName === "tickets") loadTickets();
  if (viewName === "estimator") runEstimator();
}

/* ---------------- Role & Failover Controls ---------------- */
function setRole(role) {
  state.role = role;
  document.getElementById("roleApplicantBtn").classList.toggle("active", role === "applicant");
  document.getElementById("roleStudentBtn").classList.toggle("active", role === "student");
  document.getElementById("composerRolePill").textContent =
    role === "applicant" ? "Viewing as: Applicant" : "Viewing as: Student";
  document.getElementById("chipsRoleLabel").textContent =
    role === "applicant" ? "Popular Applicant Questions:" : "Popular Student Questions:";
  renderQuickChips();
}

function renderQuickChips() {
  const container = document.getElementById("quickChipsContainer");
  container.innerHTML = "";
  for (const item of QUICK_PROMPTS[state.role]) {
    if (item.adminOnly && !state.isAdmin) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `quick-chip${item.oos ? " chip-oos" : ""}`;
    btn.textContent = item.text;
    btn.addEventListener("click", () => {
      document.getElementById("chatInput").value = item.text;
      submitChatQuery(item.text);
    });
    container.appendChild(btn);
  }
}

/* ---------------- Health & Telemetry ---------------- */
async function refreshHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    state.isAdmin = Boolean(data.is_admin);
    applyAdminVisibility();
    if (state.isAdmin) {
      document.getElementById("statSections").textContent = data.corpus_sections;
      document.getElementById("statIndexMs").textContent = `${data.indexing_ms} ms`;
      document.getElementById("openTicketBadge").textContent = data.open_tickets;
      updateApiKeyBadge(data.gemini_configured);
    }
  } catch (e) {
    console.error("Health check error:", e);
  }
}

function updateApiKeyBadge(serverConfigured = false) {
  const txt = document.getElementById("apiKeyStatusText");
  if (!txt) return;
  txt.textContent = state.apiKey || serverConfigured ? "Gemini Ready" : "Gemini Key";
}

/* ---------------- Chat Submission & Rendering ---------------- */
async function submitChatQuery(queryText) {
  const query = (queryText || "").trim();
  if (!query) return;

  const messagesEl = document.getElementById("chatMessages");
  const welcome = messagesEl.querySelector(".welcome-banner");
  if (welcome) welcome.remove();

  const userRow = document.createElement("div");
  userRow.className = "msg-row user";
  userRow.innerHTML = `
    <div class="user-bubble">${escapeHtml(query)}</div>
    <div class="user-meta">${state.role === "applicant" ? "Prospective Applicant" : "Enrolled Student"}</div>
  `;
  messagesEl.appendChild(userRow);

  const loadingRow = document.createElement("div");
  loadingRow.className = "msg-row assistant";
  loadingRow.innerHTML = `<div class="assistant-card">Searching official university circulars...</div>`;
  messagesEl.appendChild(loadingRow);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  document.getElementById("chatInput").value = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        role: state.role,
        force_offline: state.isAdmin ? state.forceOffline : false,
        api_key: state.isAdmin ? state.apiKey : "",
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      loadingRow.innerHTML = `<div class="assistant-card oos-card">${escapeHtml(data.error || "Request failed.")}</div>`;
      return;
    }

    // Cache clauses for citation modal
    for (const c of data.top_clauses || []) {
      state.policiesCache[c.policy_id] = c;
    }
    if (data.citation_details) {
      for (const [pid, detail] of Object.entries(data.citation_details)) {
        state.policiesCache[pid] = detail;
      }
    }

    const isOos = Boolean(data.is_out_of_scope);

    // Header badges: clean for students, detailed diagnostics for admin
    let badgesHtml = `<span class="badge badge-intent">${escapeHtml(data.inferred_intent)}</span>`;
    if (state.isAdmin && data.engine_label) {
      const engineBadgeClass = isOos
        ? "badge-oos"
        : data.engine_mode === "gemini_flash_online"
        ? "badge-online"
        : "badge-offline";
      badgesHtml += `
        <span class="badge ${engineBadgeClass}">${escapeHtml(data.engine_label)}</span>
        <span class="badge badge-metric">Retrieval: ${data.retrieval_ms} ms</span>
        <span class="badge badge-metric">Total: ${data.total_ms} ms</span>
        <span class="badge badge-metric">Score: ${data.max_score}</span>
      `;
    } else if (!isOos) {
      badgesHtml += `<span class="badge badge-online">Verified University Circular</span>`;
    }

    const failoverHtml =
      state.isAdmin && data.failover_reason
        ? `<div class="failover-note">⚡ ${escapeHtml(data.failover_reason)}</div>`
        : "";

    const citationsHtml = (data.citations || []).length
      ? `<div class="citations-strip">
          ${data.citations
            .map(
              (c) => `
              <button type="button" class="citation-chip" data-policy-id="${escapeHtml(c.policy_id)}">
                📄 <strong>${escapeHtml(c.policy_id)}</strong> • ${escapeHtml(c.title)}
                ${state.isAdmin && c.similarity_score !== undefined ? `<span class="mono">(${c.similarity_score})</span>` : ""}
              </button>`
            )
            .join("")}
        </div>`
      : "";

    let ticketHtml = "";
    if (data.escalation_ticket) {
      const t = data.escalation_ticket;
      ticketHtml = `
        <div class="ticket-callout">
          <div>
            <strong>#${escapeHtml(t.ticket_id)}</strong> • Routed to <b>${escapeHtml(t.routed_desk)}</b>
            <div style="font-size:0.77rem;color:#64748B;">Status: ${escapeHtml(t.status)}${
        state.isAdmin && t.max_similarity_score !== undefined ? ` • Max Score: ${t.max_similarity_score}` : ""
      }</div>
          </div>
          ${
            state.isAdmin
              ? `<button type="button" class="btn-outline btn-sm goto-tickets-btn">View Escalation Queue →</button>`
              : ""
          }
        </div>`;
    }

    const auditHtml =
      state.isAdmin && (data.top_clauses || []).length
        ? `<details class="audit-details">
            <summary>Retrieval Audit & Top-3 Cosine Scores (τ = ${data.threshold_tau})</summary>
            <div class="audit-list">
              ${data.top_clauses
                .map((c) => {
                  const pct = Math.min(100, Math.round(c.similarity_score * 160));
                  const lowClass = c.similarity_score < data.threshold_tau ? " low" : "";
                  return `
                    <div class="audit-row">
                      <button type="button" class="policy-ref-btn" data-policy-id="${escapeHtml(c.policy_id)}">${escapeHtml(
                    c.policy_id
                  )}</button>
                      <span>${escapeHtml(c.title)}</span>
                      <div class="score-bar-track"><div class="score-bar-fill${lowClass}" style="width:${pct}%"></div></div>
                      <span class="mono">${c.similarity_score.toFixed(4)} (${c.role_boost}×)</span>
                    </div>`;
                })
                .join("")}
            </div>
          </details>`
        : "";

    loadingRow.innerHTML = `
      <div class="assistant-card${isOos ? " oos-card" : ""}">
        <div class="assistant-badges">${badgesHtml}</div>
        ${failoverHtml}
        <div class="answer-body">${formatAnswerHtml(data.answer)}</div>
        ${ticketHtml}
        ${citationsHtml}
        ${auditHtml}
      </div>
    `;

    loadingRow.querySelectorAll("[data-policy-id]").forEach((btn) => {
      btn.addEventListener("click", () => openPolicyModal(btn.dataset.policyId));
    });
    const gotoTickets = loadingRow.querySelector(".goto-tickets-btn");
    if (gotoTickets) {
      gotoTickets.addEventListener("click", () => switchView("tickets"));
    }

    if (state.isAdmin) refreshHealth();
    messagesEl.scrollTop = messagesEl.scrollHeight;
  } catch (err) {
    loadingRow.innerHTML = `<div class="assistant-card oos-card">Network error communicating with UniAssist backend.</div>`;
  }
}

/* ---------------- Policy Evidence Modal ---------------- */
async function openPolicyModal(policyId) {
  let policy = state.policiesCache[policyId];
  if (!policy) {
    await loadPolicies(true);
    policy = state.policiesCache[policyId];
  }
  if (!policy) return;

  document.getElementById("modalPolicyId").textContent = policy.policy_id;
  document.getElementById("modalPolicyTitle").textContent = policy.title;
  document.getElementById("modalPolicyMeta").innerHTML = `
    <span class="badge badge-intent">Dept: ${escapeHtml(policy.department)}</span>
    <span class="badge badge-metric">Audience: ${escapeHtml(policy.target_role)}</span>
    ${
      state.isAdmin && policy.similarity_score !== undefined
        ? `<span class="badge badge-online">Cosine: ${policy.similarity_score} (Boost ${policy.role_boost}×)</span>`
        : ""
    }
  `;
  document.getElementById("modalPolicyBody").textContent = policy.content_text;
  document.getElementById("policyModal").classList.remove("hidden");
}

/* ---------------- Estimator ---------------- */
function updateExamDropdown(program, preferredExam = null) {
  const exams = PROGRAM_EXAMS[program] || ["DSAT"];
  const select = document.getElementById("estExam");
  select.innerHTML = exams.map((e) => `<option value="${e}">${e}</option>`).join("");
  if (preferredExam && exams.includes(preferredExam)) {
    select.value = preferredExam;
  }
}

async function runEstimator() {
  const payload = {
    program: state.selectedProgram,
    percentage: parseFloat(document.getElementById("estPercentage").value || "0"),
    category: document.getElementById("estCategory").value,
    entrance_exam: document.getElementById("estExam").value,
    entrance_rank: document.getElementById("estRank").value || null,
    hostel_plan: document.getElementById("estHostel").value,
    has_math: document.getElementById("estHasMath").checked,
  };

  const res = await fetch("/api/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const d = await res.json();
  const card = document.getElementById("estimatorResultCard");
  if (!res.ok) {
    card.innerHTML = `<div class="empty-state">${escapeHtml(d.error || "Invalid input")}</div>`;
    return;
  }

  let statusClass = "ok";
  let statusIcon = "✅";
  if (!d.eligible) {
    statusClass = "no";
    statusIcon = "⛔";
  } else if (d.eligibility_status.includes("Conditionally")) {
    statusClass = "cond";
    statusIcon = "⚠️";
  }

  card.innerHTML = `
    <div class="est-status-banner ${statusClass}">
      <div>
        <div style="font-size:0.74rem;font-weight:700;text-transform:uppercase;opacity:0.8;">Assessment Result</div>
        <div style="font-size:1.12rem;font-weight:800;">${statusIcon} ${escapeHtml(d.eligibility_status)}</div>
        <div style="font-size:0.8rem;opacity:0.9;">${escapeHtml(d.program_full_name)} • ${escapeHtml(d.quota_label)}</div>
      </div>
      <div style="text-align:right;">
        <div style="font-size:0.74rem;font-weight:700;">Merit Waiver</div>
        <div style="font-size:1.35rem;font-weight:800;" class="mono">${d.scholarship_pct}% OFF</div>
      </div>
    </div>

    <ul class="reason-list">
      ${d.eligibility_reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}
    </ul>

    <table class="fee-table">
      <tbody>
        <tr><td>Gross Annual Tuition Fee (${escapeHtml(d.quota_label)})</td><td>${formatInr(d.gross_tuition_fee)}</td></tr>
        <tr class="discount"><td>${escapeHtml(d.scholarship_label)}</td><td>- ${formatInr(d.scholarship_discount)}</td></tr>
        <tr><td><strong>Net Annual Tuition Fee</strong></td><td><strong>${formatInr(d.net_tuition_fee)}</strong></td></tr>
        <tr><td>Admission Processing & Registration (One-Time)</td><td>${formatInr(d.registration_fee)}</td></tr>
        <tr><td>Annual University Exam & Library Fee</td><td>${formatInr(d.exam_library_fee)}</td></tr>
        <tr><td>Refundable Caution Deposit</td><td>${formatInr(d.caution_deposit)}</td></tr>
        ${
          d.hostel_annual_fee > 0
            ? `<tr><td>Hostel & Mess (${escapeHtml(d.hostel_plan)})</td><td>${formatInr(d.hostel_annual_fee)}</td></tr>
               <tr><td>Hostel Security Deposit (Refundable)</td><td>${formatInr(d.hostel_security_deposit)}</td></tr>`
            : ""
        }
        <tr class="total"><td>Total Year-1 Payable Estimate</td><td>${formatInr(d.total_year1_payable)}</td></tr>
      </tbody>
    </table>

    <p style="font-size:0.78rem;color:#475569;margin-bottom:10px;">ℹ️ ${escapeHtml(d.govt_scholarship_note)}</p>

    <div class="citations-strip">
      ${d.citations
        .map(
          (pid) =>
            `<button type="button" class="policy-ref-btn" data-policy-id="${escapeHtml(pid)}">📄 ${escapeHtml(pid)}</button>`
        )
        .join("")}
    </div>
  `;

  card.querySelectorAll("[data-policy-id]").forEach((btn) => {
    btn.addEventListener("click", () => openPolicyModal(btn.dataset.policyId));
  });
}

/* ---------------- Policies & Admin Ingestion ---------------- */
async function loadPolicies(silentRender = false) {
  const q = encodeURIComponent(document.getElementById("corpusSearchInput").value || "");
  const dept = encodeURIComponent(document.getElementById("corpusDeptFilter").value || "ALL");
  const role = encodeURIComponent(document.getElementById("corpusRoleFilter").value || "all");

  const res = await fetch(`/api/policies?q=${q}&department=${dept}&role=${role}`);
  const data = await res.json();
  for (const p of data.policies || []) {
    state.policiesCache[p.policy_id] = p;
  }
  if (silentRender) return;

  const grid = document.getElementById("corpusGrid");
  if (!data.policies.length) {
    grid.innerHTML = `<div class="empty-state">No matching policy sections found.</div>`;
    return;
  }

  grid.innerHTML = data.policies
    .map(
      (p) => `
      <div class="policy-card" data-policy-id="${escapeHtml(p.policy_id)}">
        <div class="policy-card-top">
          <span class="policy-id-pill">${escapeHtml(p.policy_id)}</span>
          <span class="badge badge-intent">${escapeHtml(p.department)}</span>
        </div>
        <h4>${escapeHtml(p.title)}</h4>
        <div class="policy-snippet">${escapeHtml(p.content_text)}</div>
        <div style="margin-top:auto;display:flex;justify-content:space-between;font-size:0.73rem;color:#64748B;padding-top:6px;">
          <span>Audience: <b>${escapeHtml(p.target_role)}</b></span>
          <span>Click to read full rule →</span>
        </div>
      </div>`
    )
    .join("");

  grid.querySelectorAll(".policy-card").forEach((card) => {
    card.addEventListener("click", () => openPolicyModal(card.dataset.policyId));
  });
}

async function handleIngestSubmit(e) {
  e.preventDefault();
  const feedback = document.getElementById("ingestFeedback");
  feedback.textContent = "Ingesting & vectorizing...";

  const fileInput = document.getElementById("ingestFile");
  let res;
  if (fileInput.files && fileInput.files.length > 0) {
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    fd.append("department", document.getElementById("ingestDept").value);
    fd.append("target_role", document.getElementById("ingestRole").value);
    res = await fetch("/api/policies/ingest", { method: "POST", body: fd });
  } else {
    res = await fetch("/api/policies/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        policy_id: document.getElementById("ingestPolicyId").value,
        department: document.getElementById("ingestDept").value,
        target_role: document.getElementById("ingestRole").value,
        title: document.getElementById("ingestTitle").value,
        raw_text: document.getElementById("ingestRawText").value,
      }),
    });
  }

  const data = await res.json();
  if (!res.ok) {
    feedback.style.color = "#DC2626";
    feedback.textContent = data.error || "Ingestion failed.";
    return;
  }

  feedback.style.color = "#059669";
  feedback.textContent = `Indexed ${data.ingested_count} section(s) (${data.ingested_ids.join(", ")}) in ${data.indexing_ms} ms!`;
  document.getElementById("ingestForm").reset();
  refreshHealth();
  loadPolicies();
}

/* ---------------- Admin Tickets ---------------- */
async function loadTickets() {
  if (!state.isAdmin) return;
  const res = await fetch("/api/tickets");
  if (!res.ok) return;
  const data = await res.json();
  const container = document.getElementById("ticketsContainer");

  if (!data.tickets || !data.tickets.length) {
    container.innerHTML = `<div class="empty-state">No escalation tickets yet. Unindexed student queries below τ = 0.15 appear here automatically.</div>`;
    return;
  }

  container.innerHTML = data.tickets
    .map(
      (t) => `
      <div class="ticket-row">
        <div style="flex:1;min-width:240px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span class="ticket-id">#${escapeHtml(t.ticket_id)}</span>
            <span class="badge badge-intent">${escapeHtml(t.routed_desk)}</span>
            <span class="badge badge-metric">Score: ${t.max_similarity_score}</span>
          </div>
          <div style="font-weight:700;font-size:0.9rem;color:#0F172A;">"${escapeHtml(t.query)}"</div>
          <div style="font-size:0.75rem;color:#64748B;margin-top:3px;">
            Role: ${escapeHtml(t.user_role)} • Created: ${escapeHtml(t.created_at)}
          </div>
        </div>
        <div>
          <select class="ticket-status-select" data-ticket-id="${escapeHtml(t.ticket_id)}" style="padding:7px 10px;border-radius:8px;border:1px solid #CBD5E1;font-weight:600;font-size:0.82rem;">
            <option value="Open" ${t.status === "Open" ? "selected" : ""}>Open</option>
            <option value="In Review" ${t.status === "In Review" ? "selected" : ""}>In Review</option>
            <option value="Resolved" ${t.status === "Resolved" ? "selected" : ""}>Resolved</option>
          </select>
        </div>
      </div>`
    )
    .join("");

  container.querySelectorAll(".ticket-status-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      await fetch(`/api/tickets/${sel.dataset.ticketId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: sel.value }),
      });
      refreshHealth();
    });
  });
}

/* ---------------- Admin Benchmark ---------------- */
async function runLiveBenchmark() {
  if (!state.isAdmin) return;
  const target = document.getElementById("benchmarkResults");
  target.innerHTML = `<div class="card"><div class="empty-state">Running 60-query retrieval benchmark + 10 out-of-scope adversarial queries + TC-01..TC-05...</div></div>`;

  const res = await fetch("/api/benchmark/run", { method: "POST" });
  if (!res.ok) {
    target.innerHTML = `<div class="card"><div class="empty-state">Admin authentication required.</div></div>`;
    return;
  }
  const b = await res.json();

  const cmRows = b.confusion_matrix
    .map(
      (row, rIdx) => `
      <tr>
        <th style="text-align:left;">${escapeHtml(b.departments[rIdx])}</th>
        ${row
          .map(
            (val, cIdx) =>
              `<td class="${rIdx === cIdx ? "cm-diag" : ""}">${val}</td>`
          )
          .join("")}
      </tr>`
    )
    .join("");

  target.innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Rank@1 Accuracy</div>
        <div class="kpi-value">${b.rank1_accuracy_pct}%</div>
        <small style="color:#64748B;">${b.rank1_hits} / ${b.total_benchmark_queries} queries</small>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Macro-F1 Score</div>
        <div class="kpi-value">${b.macro_f1.toFixed(3)}</div>
        <small style="color:#64748B;">6 administrative domains</small>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">OOS Refusal Precision</div>
        <div class="kpi-value">${b.oos_refusal_precision_pct}%</div>
        <small style="color:#64748B;">${b.oos_refused} / ${b.oos_total} blocked (τ=0.15)</small>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Median Local Latency</div>
        <div class="kpi-value">${b.median_local_latency_ms} ms</div>
        <small style="color:#64748B;">CPU-only sub-linear TF-IDF</small>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Index Startup Time</div>
        <div class="kpi-value">${b.indexing_latency_ms} ms</div>
        <small style="color:#64748B;">Atomic section corpus</small>
      </div>
    </div>

    <div class="bench-split">
      <div class="card">
        <h3>6×6 Intent Classification Confusion Matrix</h3>
        <p style="font-size:0.8rem;color:#64748B;">Rows: Actual Policy Category • Columns: Predicted Administrative Intent</p>
        <div style="overflow-x:auto;">
          <table class="cm-table">
            <thead>
              <tr>
                <th>Actual \\ Pred</th>
                ${b.departments.map((d) => `<th>${d.slice(0, 5)}</th>`).join("")}
              </tr>
            </thead>
            <tbody>${cmRows}</tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h3>Per-Department Precision, Recall & F1</h3>
        <table class="tc-table">
          <thead>
            <tr><th>Department</th><th>Precision</th><th>Recall</th><th>F1 Score</th></tr>
          </thead>
          <tbody>
            ${b.per_department
              .map(
                (d) => `
                <tr>
                  <td><strong>${escapeHtml(d.department)}</strong></td>
                  <td class="mono">${d.precision.toFixed(3)}</td>
                  <td class="mono">${d.recall.toFixed(3)}</td>
                  <td class="mono"><strong>${d.f1.toFixed(3)}</strong></td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>Functional Test Cases Verification (TC-01 to TC-05)</h3>
      <table class="tc-table">
        <thead>
          <tr><th>Test ID</th><th>Scenario</th><th>Input Query / Action</th><th>Observed Live Output</th><th>Status</th></tr>
        </thead>
        <tbody>
          ${b.functional_tests
            .map(
              (tc) => `
              <tr>
                <td class="mono"><strong>${escapeHtml(tc.test_id)}</strong></td>
                <td>${escapeHtml(tc.scenario)}</td>
                <td>${escapeHtml(tc.input)}</td>
                <td class="mono" style="font-size:0.78rem;">${escapeHtml(tc.observed)}</td>
                <td><span class="badge ${tc.passed ? "badge-online" : "badge-oos"}">${tc.passed ? "PASS" : "FAIL"}</span></td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

/* ---------------- Bootstrapping ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  // Navigation
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  document.getElementById("mobileMenuBtn").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("open");
  });

  // Role switch
  document.getElementById("roleApplicantBtn").addEventListener("click", () => setRole("applicant"));
  document.getElementById("roleStudentBtn").addEventListener("click", () => setRole("student"));

  // Staff / Admin Portal Auth
  document.getElementById("staffAccessBtn").addEventListener("click", async () => {
    if (state.isAdmin) {
      await fetch("/api/admin/logout", { method: "POST" });
      state.isAdmin = false;
      state.forceOffline = false;
      document.getElementById("offlineToggle").checked = false;
      document.getElementById("offlineStatusLabel").textContent = "Auto (Cloud + Failover)";
      applyAdminVisibility();
    } else {
      document.getElementById("adminLoginError").classList.add("hidden");
      document.getElementById("adminPasscodeInput").value = "";
      document.getElementById("adminLoginModal").classList.remove("hidden");
      document.getElementById("adminPasscodeInput").focus();
    }
  });

  document.getElementById("closeAdminLoginBtn").addEventListener("click", () => {
    document.getElementById("adminLoginModal").classList.add("hidden");
  });
  document.getElementById("cancelAdminLoginBtn").addEventListener("click", () => {
    document.getElementById("adminLoginModal").classList.add("hidden");
  });
  document.getElementById("adminLoginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("adminLoginError");
    errEl.classList.add("hidden");
    const passcode = document.getElementById("adminPasscodeInput").value;
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passcode }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || "Invalid passcode.";
      errEl.classList.remove("hidden");
      return;
    }
    document.getElementById("adminLoginModal").classList.add("hidden");
    await refreshHealth();
  });

  // Offline toggle (Admin only)
  const offlineCb = document.getElementById("offlineToggle");
  offlineCb.addEventListener("change", () => {
    state.forceOffline = offlineCb.checked;
    document.getElementById("offlineStatusLabel").textContent = state.forceOffline
      ? "Offline Kiosk (<10ms)"
      : "Auto (Cloud + Failover)";
  });

  // Chat form
  document.getElementById("chatForm").addEventListener("submit", (e) => {
    e.preventDefault();
    submitChatQuery(document.getElementById("chatInput").value);
  });
  document.getElementById("clearChatBtn").addEventListener("click", () => {
    document.getElementById("chatMessages").innerHTML = `
      <div class="welcome-banner">
        <div class="welcome-badge">Official University Information Desk</div>
        <h2>UniAssist Helpdesk Ready</h2>
        <p>Select a popular question above or type your admissions / student service question below.</p>
      </div>`;
  });

  // Policy Modal
  document.getElementById("closePolicyModalBtn").addEventListener("click", () => {
    document.getElementById("policyModal").classList.add("hidden");
  });
  document.getElementById("policyModal").addEventListener("click", (e) => {
    if (e.target.id === "policyModal") e.target.classList.add("hidden");
  });

  // Gemini API Key Modal (Admin only)
  document.getElementById("openApiModalBtn").addEventListener("click", () => {
    document.getElementById("geminiApiKeyInput").value = state.apiKey;
    document.getElementById("apiModal").classList.remove("hidden");
  });
  document.getElementById("closeApiModalBtn").addEventListener("click", () => {
    document.getElementById("apiModal").classList.add("hidden");
  });
  document.getElementById("saveApiKeyBtn").addEventListener("click", () => {
    state.apiKey = document.getElementById("geminiApiKeyInput").value.trim();
    if (state.apiKey) {
      sessionStorage.setItem("uniassist_gemini_key", state.apiKey);
    } else {
      sessionStorage.removeItem("uniassist_gemini_key");
    }
    updateApiKeyBadge();
    document.getElementById("apiModal").classList.add("hidden");
  });
  document.getElementById("clearApiKeyBtn").addEventListener("click", () => {
    state.apiKey = "";
    sessionStorage.removeItem("uniassist_gemini_key");
    document.getElementById("geminiApiKeyInput").value = "";
    updateApiKeyBadge();
    document.getElementById("apiModal").classList.add("hidden");
  });

  // Estimator
  document.querySelectorAll(".prog-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".prog-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.selectedProgram = pill.dataset.program;
      updateExamDropdown(state.selectedProgram);
      runEstimator();
    });
  });

  const rangeEl = document.getElementById("estPercentageRange");
  const numEl = document.getElementById("estPercentage");
  rangeEl.addEventListener("input", () => {
    numEl.value = rangeEl.value;
    runEstimator();
  });
  numEl.addEventListener("input", () => {
    rangeEl.value = numEl.value;
    runEstimator();
  });

  ["estCategory", "estExam", "estHostel", "estHasMath"].forEach((id) => {
    document.getElementById(id).addEventListener("change", runEstimator);
  });
  document.getElementById("estimatorForm").addEventListener("submit", (e) => {
    e.preventDefault();
    runEstimator();
  });
  document.getElementById("loadTc05Btn").addEventListener("click", () => {
    state.selectedProgram = "MCA";
    document.querySelectorAll(".prog-pill").forEach((p) =>
      p.classList.toggle("active", p.dataset.program === "MCA")
    );
    updateExamDropdown("MCA", "PGCET");
    rangeEl.value = "86";
    numEl.value = "86";
    document.getElementById("estCategory").value = "General";
    document.getElementById("estRank").value = "";
    document.getElementById("estHostel").value = "None";
    document.getElementById("estHasMath").checked = true;
    runEstimator();
  });

  // Policies & Ingest
  document.getElementById("corpusSearchInput").addEventListener("input", () => loadPolicies());
  document.getElementById("corpusDeptFilter").addEventListener("change", () => loadPolicies());
  document.getElementById("corpusRoleFilter").addEventListener("change", () => loadPolicies());
  document.getElementById("toggleIngestDrawerBtn").addEventListener("click", () => {
    document.getElementById("ingestPanel").classList.toggle("hidden");
  });
  document.getElementById("closeIngestBtn").addEventListener("click", () => {
    document.getElementById("ingestPanel").classList.add("hidden");
  });
  document.getElementById("ingestForm").addEventListener("submit", handleIngestSubmit);

  // Tickets & Benchmark
  document.getElementById("refreshTicketsBtn").addEventListener("click", loadTickets);
  document.getElementById("runBenchmarkBtn").addEventListener("click", runLiveBenchmark);

  // Initial load
  setRole("applicant");
  refreshHealth();
  updateExamDropdown("MCA", "PGCET");
  runEstimator();
});
