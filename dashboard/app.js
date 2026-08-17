const state = {
  submissions: [],
  filter: "all",
  selectedId: null,
  runs: {}, // submission_id -> trace, cached client-side once fetched/run
};

const SPECIALIST_LABELS = {
  coverage_checker: "Coverage Checker",
  consistency_checker: "Consistency Checker",
  pricing_checker: "Pricing / Risk Checker",
};

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function decisionBadge(decision, size) {
  if (!decision) return `<span class="badge badge-decision-pending">Not run</span>`;
  const cls = `badge-decision-${decision}`;
  const tag = size === "large" ? "decision-badge-large" : "badge";
  return `<span class="${tag} ${cls}">${escapeHtml(decision)}</span>`;
}

function severityBadge(sev) {
  return `<span class="badge badge-sev badge-sev-${escapeHtml(sev)}">${escapeHtml(sev)}</span>`;
}

// ---------- Sidebar list ----------

function renderList() {
  const container = document.getElementById("submission-list");
  const filtered = state.submissions.filter((s) => {
    if (state.filter === "all") return true;
    return s.latest_decision === state.filter;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="list-loading">No submissions match this filter yet — run some first.</div>`;
    return;
  }

  container.innerHTML = filtered
    .map((s) => {
      const selected = s.submission_id === state.selectedId ? "is-selected" : "";
      return `
        <button class="submission-row ${selected}" data-id="${escapeHtml(s.submission_id)}">
          <div class="submission-row-top">
            <span class="submission-name">${escapeHtml(s.business_name)}</span>
            <span class="submission-id">${escapeHtml(s.submission_id)}</span>
          </div>
          <div class="submission-type">${escapeHtml(s.business_type)}</div>
          <div class="submission-row-bottom">
            ${decisionBadge(s.latest_decision)}
            <span class="badge badge-outline">known: ${escapeHtml(s.known_label || "—")}</span>
          </div>
        </button>
      `;
    })
    .join("");

  container.querySelectorAll(".submission-row").forEach((el) => {
    el.addEventListener("click", () => selectSubmission(el.dataset.id));
  });
}

// ---------- Trace view ----------

async function selectSubmission(id) {
  state.selectedId = id;
  renderList();
  document.getElementById("empty-state").hidden = true;
  const traceView = document.getElementById("trace-view");
  traceView.hidden = false;
  traceView.innerHTML = `<div class="list-loading">Loading…</div>`;

  const submission = await fetchJSON(`/api/submissions/${encodeURIComponent(id)}`);
  const listEntry = state.submissions.find((s) => s.submission_id === id);
  let trace = null;
  if (listEntry && listEntry.latest_run_id) {
    trace = await fetchJSON(`/api/runs/${encodeURIComponent(listEntry.latest_run_id)}`);
  }
  renderTrace(submission, trace);
}

async function runLive(id) {
  const btn = document.getElementById("run-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Running… (calls Claude 2-3×)";
  }
  try {
    const trace = await fetchJSON(`/api/submissions/${encodeURIComponent(id)}/run`, { method: "POST" });
    const listEntry = state.submissions.find((s) => s.submission_id === id);
    if (listEntry) {
      listEntry.latest_run_id = trace.run_id;
      listEntry.latest_decision = trace.decision.decision;
    }
    const submission = await fetchJSON(`/api/submissions/${encodeURIComponent(id)}`);
    renderTrace(submission, trace);
    renderList();
  } catch (err) {
    const traceView = document.getElementById("trace-view");
    traceView.insertAdjacentHTML(
      "beforeend",
      `<div class="run-error">Run failed: ${escapeHtml(err.message)}. Check that ANTHROPIC_API_KEY is set in your .env file.</div>`
    );
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Run live";
    }
  }
}

function renderTrace(submission, trace) {
  const traceView = document.getElementById("trace-view");
  const decision = trace ? trace.decision : null;

  const header = `
    <div class="trace-header">
      <div class="trace-header-top">
        <div>
          <h2>${escapeHtml(submission.business_name)}</h2>
          <div class="meta-line">
            ${escapeHtml(submission.business_type)}
            <span class="sep">·</span>${escapeHtml(submission.industry_class_code)}
            <span class="sep">·</span>${escapeHtml(submission.location.city)}, ${escapeHtml(submission.location.state)}
            <span class="sep">·</span>$${Number(submission.annual_revenue).toLocaleString()} revenue
            <span class="sep">·</span>${submission.employee_count} employees
          </div>
        </div>
        <button id="run-btn" class="run-button ${trace ? "secondary" : ""}">${trace ? "Run again" : "Run live"}</button>
      </div>
      ${decision ? renderDecisionPanel(decision, submission) : `<div class="eval-note">No run yet for this submission. Click "Run live" to invoke the orchestrator (requires ANTHROPIC_API_KEY).</div>`}
    </div>
  `;

  const body = trace
    ? `
      <div class="trace-body">
        <p class="trace-section-title">Orchestration trace</p>
        ${renderPipeline(trace)}
        ${renderScoring(decision)}
      </div>
    `
    : "";

  traceView.innerHTML = header + body;
  document.getElementById("run-btn").addEventListener("click", () => runLive(submission.submission_id));
}

function renderDecisionPanel(decision, submission) {
  const pct = Math.round(decision.confidence * 100);
  const known = submission.known_label;
  let evalNote = "";
  if (known) {
    const match = known === decision.decision;
    evalNote = `<div class="eval-note">Eval label: <strong>${escapeHtml(known)}</strong> — ${
      match ? `<span class="eval-match">matches orchestrator decision</span>` : `<span class="eval-mismatch">differs from orchestrator decision</span>`
    }</div>`;
  }
  return `
    <div class="decision-panel">
      ${decisionBadge(decision.decision, "large")}
      <div class="rationale">${escapeHtml(decision.rationale)}</div>
      <div class="confidence-meter">
        <div class="value">${pct}%</div>
        <div class="label">Combined confidence</div>
        <div class="confidence-bar"><div class="confidence-bar-fill" style="width:${pct}%"></div></div>
      </div>
    </div>
    ${evalNote}
  `;
}

function renderPipeline(trace) {
  const verdictsBySpecialist = {};
  trace.verdicts.forEach((v) => (verdictsBySpecialist[v.specialist] = v));

  const phases = trace.routing
    .map((step) => {
      const cards = step.specialists_invoked.length
        ? `<div class="specialist-row">${step.specialists_invoked
            .map((name) => renderSpecialistCard(verdictsBySpecialist[name]))
            .join("")}</div>`
        : `<div class="specialist-row"><div class="specialist-card skipped">Pricing check skipped this phase — see reason above.</div></div>`;

      return `
        <div class="phase">
          <div class="phase-dot"></div>
          <div class="phase-label">Phase ${step.phase} — ${step.specialists_invoked.length ? step.specialists_invoked.map((n) => SPECIALIST_LABELS[n] || n).join(" + ") : "skipped"}</div>
          <div class="phase-reason">${escapeHtml(step.reason)}</div>
          ${cards}
        </div>
      `;
    })
    .join("");

  return `<div class="pipeline">${phases}</div>`;
}

function renderSpecialistCard(verdict) {
  if (!verdict) return "";
  const findingsHtml = verdict.findings.length
    ? `<ul class="findings-list">${verdict.findings.map(renderFinding).join("")}</ul>`
    : `<p class="no-findings">No findings — nothing to flag.</p>`;

  const droppedHtml = verdict.dropped_findings && verdict.dropped_findings.length
    ? `<div class="dropped-note">${verdict.dropped_findings.length} finding(s) dropped — the model couldn't cite a field that supported the claim.</div>`
    : "";

  const toolCallsHtml = verdict.tool_calls && verdict.tool_calls.length
    ? `<details class="tool-trace"><summary>${verdict.tool_calls.length} reference lookup(s)</summary>
        ${verdict.tool_calls.map((tc) => `<div class="tool-call">${escapeHtml(tc.tool)}(${escapeHtml(JSON.stringify(tc.input))})\n→ ${escapeHtml(JSON.stringify(tc.result))}</div>`).join("")}
      </details>`
    : "";

  return `
    <div class="specialist-card">
      <div class="specialist-card-header">
        <span class="specialist-name">${escapeHtml(SPECIALIST_LABELS[verdict.specialist] || verdict.specialist)}</span>
        ${severityBadge(verdict.overall_severity)}
      </div>
      <div class="specialist-confidence">confidence ${(verdict.overall_confidence * 100).toFixed(0)}%</div>
      <p class="specialist-summary">${escapeHtml(verdict.summary)}</p>
      ${findingsHtml}
      ${droppedHtml}
      ${toolCallsHtml}
    </div>
  `;
}

function renderFinding(f) {
  return `
    <li class="finding sev-${escapeHtml(f.severity)}">
      <div class="finding-meta">${severityBadge(f.severity)}<span class="specialist-confidence">confidence ${(f.confidence * 100).toFixed(0)}%</span></div>
      <div class="finding-text">${escapeHtml(f.finding)}</div>
      <span class="finding-citation">${escapeHtml(f.citation.field)}: "${escapeHtml(f.citation.excerpt)}"</span>
    </li>
  `;
}

function renderScoring(decision) {
  const sb = decision.score_breakdown;
  const rows = sb.per_specialist
    .map(
      (e) => `
      <tr>
        <td>${escapeHtml(SPECIALIST_LABELS[e.specialist] || e.specialist)}</td>
        <td>${severityBadge(e.worst_severity)}</td>
        <td>${(e.worst_confidence * 100).toFixed(0)}%</td>
        <td>${e.specialist_score.toFixed(2)}</td>
        <td>${e.confidence_weight}×</td>
      </tr>
    `
    )
    .join("");

  return `
    <details class="scoring">
      <summary>How this decision was scored</summary>
      <table class="scoring-table">
        <thead>
          <tr><th>Specialist</th><th>Worst finding</th><th>Confidence</th><th>Score</th><th>Weight in combined confidence</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="scoring-formula">
        Decline threshold: score ≥ ${sb.decline_threshold.toFixed(2)}. Refer threshold: score ≥ ${sb.refer_threshold.toFixed(2)}
        or ${sb.refer_medium_plus_count_trigger}+ independent medium-or-above findings (this run had ${sb.medium_plus_finding_count}).
        Highest specialist score this run: ${sb.max_specialist_score.toFixed(2)}.<br><br>
        Combined confidence formula: ${escapeHtml(sb.combined_confidence_formula)}
      </div>
    </details>
  `;
}

// ---------- Init ----------

async function init() {
  document.querySelectorAll(".filter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".filter-chip").forEach((c) => c.classList.remove("is-active"));
      chip.classList.add("is-active");
      state.filter = chip.dataset.filter;
      renderList();
    });
  });

  state.submissions = await fetchJSON("/api/submissions");
  renderList();
}

init();
