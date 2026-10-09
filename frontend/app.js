"use strict";

/*
 * Vanilla JS client for the evaluation API. Served from the same origin; no build step.
 *
 * Security: prompts, model outputs and comments are untrusted. Everything returned by the
 * API is rendered through el() / textContent; innerHTML is never used.
 */

// ---------------------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);

/** Create an element. Known DOM properties are set directly, anything else as an attribute.
 *  Children may be nodes or plain values (always inserted as text). */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function setStatus(id, kind, message) {
  const node = $(id);
  node.className = `status ${kind}`;
  node.textContent = message;
}

function clearStatus(id) {
  setStatus(id, "", "");
}

function formatDate(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? String(iso) : date.toLocaleString();
}

function formatNumber(value, digits = 3) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function formatPercent(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
}

function scaleValues(min, max) {
  const values = [];
  for (let score = min; score <= max; score += 1) values.push(score);
  return values;
}

// ---------------------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------------------

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** ["body", "criteria", 0, "name"] -> "criteria[0].name" */
function formatLoc(loc) {
  let path = "";
  for (const part of loc || []) {
    if (part === "body") continue;
    if (typeof part === "number") path += `[${part}]`;
    else path += path ? `.${part}` : part;
  }
  return path;
}

function errorMessage(data, status) {
  const detail = data && data.detail;
  // Business-rule errors: {"detail": {"code", "message", "field"}}
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message) {
    return detail.field ? `${detail.message} (field: ${detail.field})` : detail.message;
  }
  // FastAPI / Pydantic validation errors: {"detail": [{"loc", "msg"}, ...]}
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const where = formatLoc(item.loc);
        const msg = String(item.msg || "Invalid value").replace(/^Value error, /, "");
        return where ? `${where}: ${msg}` : msg;
      })
      .join(" · ");
  }
  if (typeof detail === "string") return detail;
  return `Request failed (HTTP ${status}).`;
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Could not reach the API. Is the server running?", 0);
  }

  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null; // e.g. a plain-text 500 response; never shown raw
    }
  }
  if (!response.ok) throw new ApiError(errorMessage(data, response.status), response.status);
  return data;
}

/** Disable a button while an async action runs, preventing double submissions. */
async function withBusy(button, busyLabel, action) {
  if (button.disabled) return;
  const label = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = busyLabel;
  try {
    await action();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = label;
  }
}

/** Run an action for a form/button and report any ApiError in the given status area. */
async function run(button, busyLabel, statusId, action) {
  await withBusy(button, busyLabel, async () => {
    try {
      await action();
    } catch (error) {
      if (!(error instanceof ApiError)) console.error(error);
      setStatus(statusId, "error", error instanceof ApiError ? error.message : "Unexpected error.");
    }
  });
}

// ---------------------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------------------

const state = {
  rubrics: [],
  submissions: [],
  viewedRubricId: null,
  selectedSubmissionId: null,
};

const rubricById = (id) => state.rubrics.find((rubric) => rubric.id === Number(id));

// ---------------------------------------------------------------------------------------
// 1. Rubrics: create form
// ---------------------------------------------------------------------------------------

const MAX_SCALE_POINTS = 11;
let criterionCounter = 0;

function currentScale() {
  const min = Number($("scale-min").value);
  const max = Number($("scale-max").value);
  if (!Number.isInteger(min) || !Number.isInteger(max) || min >= max) return null;
  if (max - min + 1 > MAX_SCALE_POINTS) return null;
  return { min, max };
}

function addCriterion(initial = {}) {
  criterionCounter += 1;
  const uid = `crit-${criterionCounter}`;
  const card = el(
    "fieldset",
    { class: "criterion-card" },
    el("legend", { text: "Criterion" }),
    el(
      "div",
      { class: "criterion-top" },
      el(
        "div",
        { class: "field" },
        el("label", { htmlFor: `${uid}-name`, text: "Name" }),
        el("input", { id: `${uid}-name`, class: "crit-name", required: true, maxLength: 200, value: initial.name || "" }),
      ),
      el(
        "div",
        { class: "field" },
        el("label", { htmlFor: `${uid}-weight`, text: "Weight" }),
        el("input", {
          id: `${uid}-weight`,
          class: "crit-weight",
          type: "number",
          min: "0.01",
          step: "any",
          required: true,
          value: String(initial.weight ?? 1),
        }),
      ),
    ),
    el(
      "div",
      { class: "field" },
      el("label", { htmlFor: `${uid}-desc` }, "Description ", el("span", { class: "optional", text: "(optional)" })),
      el("input", { id: `${uid}-desc`, class: "crit-desc", maxLength: 4000, value: initial.description || "" }),
    ),
    el(
      "div",
      { class: "anchor-row anchor-header", "aria-hidden": "true" },
      el("span", { text: "Score" }),
      el("span", { text: "Label" }),
      el("span", { text: "Description (optional)" }),
    ),
    el("div", { class: "anchor-rows" }),
    el(
      "div",
      { class: "actions" },
      el("button", {
        type: "button",
        class: "link-danger",
        text: "Remove criterion",
        onclick: () => {
          if (document.querySelectorAll(".criterion-card").length > 1) card.remove();
          else setStatus("rubric-status", "error", "A rubric needs at least one criterion.");
        },
      }),
    ),
  );
  card.dataset.uid = uid;
  card.dataset.anchors = JSON.stringify(initial.anchors || {});
  $("criteria-list").append(card);
  renderAnchorRows(card);
}

/** Build one anchor row per scale point, keeping anything already typed for that score. */
function renderAnchorRows(card) {
  const container = card.querySelector(".anchor-rows");
  const saved = JSON.parse(card.dataset.anchors || "{}");
  for (const row of container.querySelectorAll(".anchor-row")) {
    saved[row.dataset.score] = {
      label: row.querySelector(".anchor-label").value,
      description: row.querySelector(".anchor-desc").value,
    };
  }
  card.dataset.anchors = JSON.stringify(saved);

  const scale = currentScale();
  if (!scale) {
    container.replaceChildren(
      el("p", {
        class: "hint",
        text: `Enter a valid scale: minimum below maximum, at most ${MAX_SCALE_POINTS} points.`,
      }),
    );
    return;
  }
  const uid = card.dataset.uid;
  container.replaceChildren(
    ...scaleValues(scale.min, scale.max).map((score) => {
      const prior = saved[score] || {};
      return el(
        "div",
        { class: "anchor-row", "data-score": score },
        el("span", { class: "anchor-score", text: String(score) }),
        el("input", {
          id: `${uid}-label-${score}`,
          class: "anchor-label",
          required: true,
          maxLength: 100,
          placeholder: "Label",
          value: prior.label || "",
          "aria-label": `Label for score ${score}`,
        }),
        el("input", {
          class: "anchor-desc",
          maxLength: 4000,
          placeholder: "What this score means",
          value: prior.description || "",
          "aria-label": `Description for score ${score}`,
        }),
      );
    }),
  );
}

function rerenderAllAnchors() {
  document.querySelectorAll(".criterion-card").forEach(renderAnchorRows);
}

function resetRubricForm() {
  $("rubric-form").reset();
  $("criteria-list").replaceChildren();
  addCriterion();
}

const EXAMPLE_LEVELS = ["Very poor", "Weak", "Acceptable", "Strong", "Excellent"];

function fillRubricExample() {
  $("rubric-name").value = "General Response Quality";
  $("rubric-description").value = "Evaluates correctness, relevance and clarity of a model response.";
  $("scale-min").value = "1";
  $("scale-max").value = "5";
  $("criteria-list").replaceChildren();
  const criteria = [
    ["Correctness", "How factually and logically correct is the response?", 2],
    ["Relevance", "Does the response address the prompt directly?", 1],
    ["Clarity", "Is the response clear and well organised?", 1],
  ];
  for (const [name, description, weight] of criteria) {
    const anchors = {};
    EXAMPLE_LEVELS.forEach((label, index) => {
      anchors[index + 1] = { label, description: `${label} ${name.toLowerCase()}.` };
    });
    addCriterion({ name, description, weight, anchors });
  }
  clearStatus("rubric-status");
}

function collectRubricPayload() {
  const scale = currentScale();
  if (!scale) return null;
  const criteria = [...document.querySelectorAll(".criterion-card")].map((card) => ({
    name: card.querySelector(".crit-name").value.trim(),
    description: card.querySelector(".crit-desc").value.trim() || null,
    weight: Number(card.querySelector(".crit-weight").value),
    anchors: [...card.querySelectorAll(".anchor-rows .anchor-row")].map((row) => ({
      score: Number(row.dataset.score),
      label: row.querySelector(".anchor-label").value.trim(),
      description: row.querySelector(".anchor-desc").value.trim() || null,
    })),
  }));
  return {
    name: $("rubric-name").value.trim(),
    description: $("rubric-description").value.trim() || null,
    scale_min: scale.min,
    scale_max: scale.max,
    criteria,
  };
}

async function onRubricSubmit(event) {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector("[type=submit]");
  await run(button, "Creating…", "rubric-status", async () => {
    const payload = collectRubricPayload();
    if (!payload) {
      setStatus("rubric-status", "error", `Invalid scale: minimum must be below maximum, with at most ${MAX_SCALE_POINTS} points.`);
      return;
    }
    setStatus("rubric-status", "info", "Creating rubric…");
    const rubric = await api("/rubrics", { method: "POST", body: payload });
    resetRubricForm();
    setStatus("rubric-status", "success", `Rubric created successfully — ID ${rubric.id}`);
    await loadRubrics();
    showRubricDetail(rubric.id);
  });
}

// ---------------------------------------------------------------------------------------
// 1. Rubrics: list and detail
// ---------------------------------------------------------------------------------------

async function loadRubrics() {
  try {
    const page = await api("/rubrics?limit=100");
    state.rubrics = page.items;
    clearStatus("rubric-list-status");
    if (page.total > page.items.length) {
      setStatus("rubric-list-status", "info", `Showing the first ${page.items.length} of ${page.total} rubrics.`);
    }
  } catch (error) {
    setStatus("rubric-list-status", "error", error.message);
  }
  renderRubricRows();
  populateRubricSelects();
}

function renderRubricRows() {
  const rows = state.rubrics.map((rubric) =>
    el(
      "tr",
      { class: rubric.id === state.viewedRubricId ? "selected" : "" },
      el("td", { text: String(rubric.id) }),
      el("td", { text: rubric.name }),
      el("td", { text: `${rubric.scale_min}–${rubric.scale_max}` }),
      el("td", { class: "num", text: String(rubric.criteria.length) }),
      el(
        "td",
        {},
        el("button", {
          type: "button",
          class: "secondary small",
          text: "View",
          "aria-pressed": String(rubric.id === state.viewedRubricId),
          "aria-controls": "rubric-detail",
          "aria-label": `View rubric ${rubric.id}: ${rubric.name}`,
          onclick: () => showRubricDetail(rubric.id),
        }),
      ),
    ),
  );
  $("rubric-rows").replaceChildren(
    ...(rows.length ? rows : [el("tr", {}, el("td", { colSpan: 5, class: "empty", text: "No rubrics yet." }))]),
  );
}

function showRubricDetail(id) {
  const rubric = rubricById(id);
  if (!rubric) return;
  state.viewedRubricId = rubric.id;
  renderRubricRows();
  // Wrapping in el("div") flattens the nested arrays and drops null children.
  const detail = $("rubric-detail");
  const content = el(
    "div",
    {},
    el("h4", { text: `Rubric #${rubric.id}: ${rubric.name}` }),
    el("p", { class: "meta", text: `Scale ${rubric.scale_min}–${rubric.scale_max} · created ${formatDate(rubric.created_at)}` }),
    rubric.description ? el("p", { text: rubric.description }) : null,
    ...rubric.criteria.flatMap((criterion) => [
      el("h4", {}, criterion.name, el("span", { class: "tag", text: `weight ${criterion.weight}` })),
      criterion.description ? el("p", { class: "meta", text: criterion.description }) : null,
      el(
        "dl",
        { class: "anchors" },
        ...criterion.anchors.map((anchor) => [
          el("dt", { text: String(anchor.score) }),
          el("dd", {}, el("strong", { text: anchor.label }), anchor.description ? ` — ${anchor.description}` : ""),
        ]),
      ),
    ]),
  );
  detail.replaceChildren(...content.childNodes);
  detail.hidden = false;
}

function populateRubricSelects() {
  const scoreSelect = $("score-rubric");
  const resultsSelect = $("results-rubric");
  const previousScore = scoreSelect.value;
  const previousResults = resultsSelect.value;
  const options = () => state.rubrics.map((r) => el("option", { value: String(r.id), text: `#${r.id} ${r.name} (${r.scale_min}–${r.scale_max})` }));

  scoreSelect.replaceChildren(el("option", { value: "", text: "Choose a rubric…" }), ...options());
  resultsSelect.replaceChildren(el("option", { value: "", text: "All rubrics" }), ...options());
  if (rubricById(previousScore)) scoreSelect.value = previousScore;
  if (rubricById(previousResults)) resultsSelect.value = previousResults;
}

// ---------------------------------------------------------------------------------------
// 2. Submissions
// ---------------------------------------------------------------------------------------

function fillSubmissionExample() {
  $("sub-prompt").value = "Explain why idempotency matters in payment APIs.";
  $("sub-output").value =
    "Idempotency ensures that retrying the same payment request (for example after a network timeout) " +
    "does not charge the customer twice. Clients send an idempotency key; the server stores the first " +
    "result for that key and returns it for any repeated request.";
  $("sub-model").value = "example-model";
  $("sub-version").value = "v1";
  $("sub-reference").value = "A strong answer discusses duplicate requests, retries and idempotency keys.";
  $("sub-metadata").value = '{"temperature": 0.2, "provider": "example"}';
  $("sub-metadata").setCustomValidity("");
  clearStatus("submission-status");
}

/** Parse the optional metadata textarea; flags the field invalid if it is not a JSON object. */
function parseMetadata() {
  const field = $("sub-metadata");
  const text = field.value.trim();
  field.setCustomValidity("");
  if (!text) return { ok: true, value: null };
  try {
    const value = JSON.parse(text);
    if (value && typeof value === "object" && !Array.isArray(value)) return { ok: true, value };
  } catch {
    // fall through
  }
  field.setCustomValidity('Model metadata must be a JSON object, e.g. {"temperature": 0.2}.');
  field.reportValidity();
  return { ok: false };
}

async function onSubmissionSubmit(event) {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector("[type=submit]");
  const metadata = parseMetadata();
  if (!metadata.ok) {
    setStatus("submission-status", "error", "Model metadata must be a valid JSON object.");
    return;
  }
  await run(button, "Submitting…", "submission-status", async () => {
    setStatus("submission-status", "info", "Creating submission…");
    const submission = await api("/submissions", {
      method: "POST",
      body: {
        prompt: $("sub-prompt").value,
        output: $("sub-output").value,
        model_name: $("sub-model").value.trim(),
        model_version: $("sub-version").value.trim() || null,
        reference_answer: $("sub-reference").value.trim() || null,
        model_metadata: metadata.value,
      },
    });
    event.target.reset();
    setStatus("submission-status", "success", `Submission created successfully — ID ${submission.id}`);
    await loadSubmissions();
    await selectSubmission(submission.id);
  });
}

async function loadSubmissions() {
  try {
    const page = await api("/submissions?limit=50");
    state.submissions = page.items;
    clearStatus("submission-list-status");
    if (page.total > page.items.length) {
      setStatus("submission-list-status", "info", `Showing the ${page.items.length} most recent of ${page.total} submissions.`);
    }
  } catch (error) {
    setStatus("submission-list-status", "error", error.message);
  }
  renderSubmissionRows();
}

function renderSubmissionRows() {
  const rows = state.submissions.map((submission) => {
    const selected = submission.id === state.selectedSubmissionId;
    return el(
      "tr",
      { class: selected ? "selected" : "" },
      el("td", { text: String(submission.id) }),
      el("td", { text: submission.model_version ? `${submission.model_name} (${submission.model_version})` : submission.model_name }),
      el("td", { text: submission.prompt_preview }),
      el("td", { class: "num", text: String(submission.evaluation_count) }),
      el("td", { text: formatDate(submission.created_at) }),
      el(
        "td",
        {},
        el("button", {
          type: "button",
          class: "secondary small",
          text: selected ? "Selected" : "Select",
          "aria-pressed": String(selected),
          "aria-label": `Select submission ${submission.id} for scoring`,
          onclick: () => selectSubmission(submission.id),
        }),
      ),
    );
  });
  $("submission-rows").replaceChildren(
    ...(rows.length ? rows : [el("tr", {}, el("td", { colSpan: 6, class: "empty", text: "No submissions yet." }))]),
  );
}

function textBlock(label, text) {
  return [el("h4", { text: label }), el("div", { class: "text-block", text })];
}

async function selectSubmission(id) {
  state.selectedSubmissionId = id;
  renderSubmissionRows();
  $("agreement-output").replaceChildren();
  $("scores-output").replaceChildren();
  clearStatus("results-status");
  clearStatus("score-status");

  const panel = $("selected-submission");
  try {
    const submission = await api(`/submissions/${id}`);
    panel.replaceChildren(
      el("h3", { text: `Submission #${submission.id}` }),
      el("p", {
        class: "meta",
        text: [
          `Model: ${submission.model_name}`,
          submission.model_version ? `version ${submission.model_version}` : null,
          `created ${formatDate(submission.created_at)}`,
        ]
          .filter(Boolean)
          .join(" · "),
      }),
      ...textBlock("Prompt", submission.prompt),
      ...textBlock("Model output", submission.output),
      ...(submission.reference_answer ? textBlock("Reference answer", submission.reference_answer) : []),
      ...(submission.model_metadata ? textBlock("Model metadata", JSON.stringify(submission.model_metadata, null, 2)) : []),
    );
  } catch (error) {
    panel.replaceChildren(el("p", { class: "status error", text: error.message }));
  }
  panel.hidden = false;
  $("no-submission").hidden = true;
  $("score-form").hidden = false;
  $("no-results").hidden = true;
  $("results-panel").hidden = false;
}

// ---------------------------------------------------------------------------------------
// 3. Scoring
// ---------------------------------------------------------------------------------------

function scoreOptions(rubric, anchors) {
  return [
    el("option", { value: "", text: "Choose…" }),
    ...scaleValues(rubric.scale_min, rubric.scale_max).map((score) => {
      const anchor = anchors && anchors.find((a) => a.score === score);
      return el("option", { value: String(score), text: anchor ? `${score} — ${anchor.label}` : String(score) });
    }),
  ];
}

function renderScoreFields() {
  const rubric = rubricById($("score-rubric").value);
  const fieldset = $("criterion-scores");
  const legend = el("legend", { text: "Criterion scores" });
  if (!rubric) {
    fieldset.replaceChildren(legend, el("p", { class: "hint", text: "Choose a rubric to see its criteria." }));
    $("overall-score").replaceChildren(el("option", { value: "", text: "Choose a rubric first" }));
    return;
  }

  const rows = rubric.criteria.map((criterion) => {
    const selectId = `score-${criterion.id}`;
    const anchorText = el("p", { class: "anchor-text", id: `${selectId}-anchor`, "aria-live": "polite" });
    const select = el("select", {
      id: selectId,
      class: "criterion-score",
      required: true,
      "data-criterion-id": criterion.id,
      "aria-describedby": `${selectId}-anchor`,
      onchange: () => {
        const anchor = criterion.anchors.find((a) => a.score === Number(select.value));
        anchorText.textContent = anchor ? anchor.description || anchor.label : "";
      },
    });
    select.append(...scoreOptions(rubric, criterion.anchors));
    return el(
      "div",
      { class: "score-row" },
      el(
        "div",
        {},
        el("label", { htmlFor: selectId }, criterion.name, el("span", { class: "tag", text: `weight ${criterion.weight}` })),
        criterion.description ? el("p", { class: "anchor-text", text: criterion.description }) : null,
      ),
      el("div", {}, select, anchorText),
      el("input", {
        class: "criterion-comment",
        maxLength: 4000,
        placeholder: "Comment (optional)",
        "aria-label": `Comment for ${criterion.name} (optional)`,
      }),
    );
  });
  fieldset.replaceChildren(legend, ...rows);
  $("overall-score").replaceChildren(...scoreOptions(rubric, null));
}

/** "rater-001" -> "rater-002"; leaves IDs without a trailing number unchanged. */
function nextRaterId(id) {
  const match = /^(.*?)(\d+)$/.exec(id);
  if (!match) return id;
  const next = String(Number(match[2]) + 1).padStart(match[2].length, "0");
  return `${match[1]}${next}`;
}

const EVALUATOR_NAMES = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

async function onScoreSubmit(event) {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector("[type=submit]");
  const rubric = rubricById($("score-rubric").value);
  const submissionId = state.selectedSubmissionId;
  if (!rubric || !submissionId) return;

  await run(button, "Submitting…", "score-status", async () => {
    setStatus("score-status", "info", "Submitting evaluation…");
    const criterionScores = [...document.querySelectorAll("#criterion-scores .score-row")].map((row) => ({
      criterion_id: Number(row.querySelector(".criterion-score").dataset.criterionId),
      score: Number(row.querySelector(".criterion-score").value),
      comment: row.querySelector(".criterion-comment").value.trim() || null,
    }));
    const raterId = $("rater-id").value.trim();
    const evaluation = await api(`/submissions/${submissionId}/scores`, {
      method: "POST",
      body: {
        rubric_id: rubric.id,
        rater: { external_id: raterId, name: $("rater-name").value.trim() },
        criterion_scores: criterionScores,
        overall_score: Number($("overall-score").value),
        comments: $("overall-comments").value.trim() || null,
      },
    });

    setStatus(
      "score-status",
      "success",
      `Evaluation submitted successfully — ${evaluation.rater.name} (${evaluation.rater.external_id}), overall ${evaluation.overall_score}. Ready for the next rater.`,
    );
    // Prepare the form for the next rater on the same rubric.
    renderScoreFields();
    $("overall-comments").value = "";
    $("rater-id").value = nextRaterId(raterId);
    const number = Number((/(\d+)$/.exec($("rater-id").value) || [])[1]);
    if (/^Evaluator /.test($("rater-name").value) && EVALUATOR_NAMES[number - 1]) {
      $("rater-name").value = `Evaluator ${EVALUATOR_NAMES[number - 1]}`;
    }

    $("results-rubric").value = String(rubric.id);
    await Promise.all([loadSubmissions(), loadScores()]);
  });
}

// ---------------------------------------------------------------------------------------
// 4. Scores and agreement
// ---------------------------------------------------------------------------------------

function resultsQuery() {
  const rubricId = $("results-rubric").value;
  return rubricId ? `?rubric_id=${encodeURIComponent(rubricId)}` : "";
}

async function loadScores() {
  const evaluations = await api(`/submissions/${state.selectedSubmissionId}/scores${resultsQuery()}`);
  renderEvaluations(evaluations);
}

function stat(label, value, tag) {
  return el("div", {}, el("dt", {}, label, tag ? el("span", { class: "tag", text: tag }) : null), el("dd", { text: value }));
}

function renderEvaluations(evaluations) {
  const output = $("scores-output");
  if (!evaluations.length) {
    output.replaceChildren(el("h3", { text: "Evaluations" }), el("p", { class: "hint", text: "No evaluations yet for this selection." }));
    return;
  }
  output.replaceChildren(
    el("h3", { text: `Evaluations (${evaluations.length})` }),
    ...evaluations.map((evaluation) =>
      el(
        "article",
        { class: "eval-card" },
        el("h4", { text: `${evaluation.rater.name} (${evaluation.rater.external_id})` }),
        el("p", { class: "meta", text: `Rubric #${evaluation.rubric.id} ${evaluation.rubric.name} · ${formatDate(evaluation.created_at)}` }),
        el(
          "div",
          { class: "table-wrap" },
          el(
            "table",
            { class: "data-table" },
            el(
              "thead",
              {},
              el(
                "tr",
                {},
                el("th", { scope: "col", text: "Criterion" }),
                el("th", { scope: "col", class: "num", text: "Weight" }),
                el("th", { scope: "col", class: "num", text: "Score" }),
                el("th", { scope: "col", text: "Comment" }),
              ),
            ),
            el(
              "tbody",
              {},
              ...evaluation.criterion_scores.map((cs) =>
                el(
                  "tr",
                  {},
                  el("td", { text: cs.criterion_name }),
                  el("td", { class: "num", text: String(cs.weight) }),
                  el("td", { class: "num", text: String(cs.score) }),
                  el("td", { text: cs.comment || "—" }),
                ),
              ),
            ),
          ),
        ),
        el(
          "dl",
          { class: "stats" },
          stat("Overall score", String(evaluation.overall_score), "rater"),
          stat("Mean criterion score", formatNumber(evaluation.derived.mean_criterion_score, 2), "derived"),
          stat("Weighted mean", formatNumber(evaluation.derived.weighted_mean_criterion_score, 2), "derived"),
        ),
        evaluation.comments ? el("p", {}, el("strong", { text: "Comments: " }), evaluation.comments) : null,
      ),
    ),
  );
}

async function loadAgreement() {
  const agreement = await api(`/submissions/${state.selectedSubmissionId}/agreement${resultsQuery()}`);
  renderAgreement(agreement);
}

function kappaCell(pair) {
  if (pair.kappa === null) {
    return el("td", {}, el("strong", { text: "Undefined" }), el("p", { class: "meta", text: pair.kappa_note || "Kappa cannot be computed for this pair." }));
  }
  return el("td", { class: "num", text: formatNumber(pair.kappa) });
}

function renderAgreement(agreement) {
  const rubric = rubricById(agreement.rubric_id);
  const meanKappa =
    agreement.mean_pairwise_kappa === null ? "Undefined (no pair has a defined kappa)" : formatNumber(agreement.mean_pairwise_kappa);

  $("agreement-output").replaceChildren(
    el("h3", { text: `Agreement — rubric #${agreement.rubric_id}${rubric ? ` ${rubric.name}` : ""}` }),
    el(
      "dl",
      { class: "stats" },
      stat("Raters", String(agreement.rater_count)),
      stat("Criteria compared", String(agreement.criterion_count)),
      stat("Mean pairwise Cohen's κ", meanKappa),
      stat("Mean exact agreement", formatPercent(agreement.mean_pairwise_exact_agreement)),
    ),
    el(
      "div",
      { class: "table-wrap" },
      el(
        "table",
        { class: "data-table" },
        el("caption", { class: "visually-hidden", text: "Pairwise agreement" }),
        el(
          "thead",
          {},
          el(
            "tr",
            {},
            el("th", { scope: "col", text: "Rater A" }),
            el("th", { scope: "col", text: "Rater B" }),
            el("th", { scope: "col", text: "Scores A" }),
            el("th", { scope: "col", text: "Scores B" }),
            el("th", { scope: "col", class: "num", text: "Observed (Po)" }),
            el("th", { scope: "col", class: "num", text: "Expected (Pe)" }),
            el("th", { scope: "col", class: "num", text: "Cohen's κ" }),
          ),
        ),
        el(
          "tbody",
          {},
          ...agreement.pairwise.map((pair) =>
            el(
              "tr",
              {},
              el("td", { text: `${pair.rater_a.name} (${pair.rater_a.external_id})` }),
              el("td", { text: `${pair.rater_b.name} (${pair.rater_b.external_id})` }),
              el("td", { text: pair.scores_a.join(", ") }),
              el("td", { text: pair.scores_b.join(", ") }),
              el("td", { class: "num", text: formatPercent(pair.observed_agreement) }),
              el("td", { class: "num", text: formatPercent(pair.expected_agreement) }),
              kappaCell(pair),
            ),
          ),
        ),
      ),
    ),
    el("p", { class: "note", text: agreement.note }),
  );
}

// ---------------------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------------------

async function checkHealth() {
  const badge = $("api-health");
  try {
    const health = await api("/health");
    badge.textContent = health.status === "ok" ? "API online" : "API degraded";
    badge.className = health.status === "ok" ? "health ok" : "health down";
  } catch {
    badge.textContent = "API unavailable";
    badge.className = "health down";
  }
}

function init() {
  addCriterion();
  $("add-criterion").addEventListener("click", () => addCriterion());
  $("rubric-example").addEventListener("click", fillRubricExample);
  $("scale-min").addEventListener("input", rerenderAllAnchors);
  $("scale-max").addEventListener("input", rerenderAllAnchors);
  $("rubric-form").addEventListener("submit", onRubricSubmit);
  $("refresh-rubrics").addEventListener("click", (event) => withBusy(event.currentTarget, "Loading…", loadRubrics));

  $("submission-example").addEventListener("click", fillSubmissionExample);
  $("sub-metadata").addEventListener("input", () => $("sub-metadata").setCustomValidity(""));
  $("submission-form").addEventListener("submit", onSubmissionSubmit);
  $("refresh-submissions").addEventListener("click", (event) => withBusy(event.currentTarget, "Loading…", loadSubmissions));

  $("score-rubric").addEventListener("change", renderScoreFields);
  $("score-form").addEventListener("submit", onScoreSubmit);

  $("load-scores").addEventListener("click", (event) => {
    clearStatus("results-status");
    return run(event.currentTarget, "Loading…", "results-status", loadScores);
  });
  $("load-agreement").addEventListener("click", (event) => {
    clearStatus("results-status");
    $("agreement-output").replaceChildren();
    return run(event.currentTarget, "Calculating…", "results-status", loadAgreement);
  });

  renderScoreFields();
  checkHealth();
  loadRubrics();
  loadSubmissions();
}

document.addEventListener("DOMContentLoaded", init);
