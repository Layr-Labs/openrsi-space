"use strict";

const byId = id => document.getElementById(id);
const state = { objects: [], tiers: [], matrix: null, selected: null, request: 0, detailRequest: 0 };
const number = value => value == null ? "—" : new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 }).format(value);
const dollars = value => value == null ? "Unknown" : "$" + number(value);
const element = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
async function api(path) {
  const response = await fetch(path);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed.");
  return result;
}
function options(select, entries, selected) {
  select.replaceChildren(...entries.map(([value, label]) => {
    const option = element("option", label);
    option.value = value;
    option.selected = value === selected;
    return option;
  }));
}
function showError(error) {
  byId("error").textContent = error.message;
  byId("error").hidden = false;
}
async function load(reset = false) {
  const requestId = ++state.request;
  const budget = byId("budget").value === "best" ? "best" : Number(byId("budget").value);
  if (!state.tiers.includes(budget)) {
    showError(new Error("Select $20, $200 or Best achieved."));
    return;
  }
  byId("error").hidden = true;
  const [identity, version] = byId("problem").value.split("/");
  const params = new URLSearchParams({ problem: identity, version, budget });
  if (!reset && byId("model").value) params.set("model", byId("model").value);
  if (!reset && byId("conditions").value) params.set("conditions", byId("conditions").value);
  try {
    const matrix = await api("/api/matrix?" + params);
    if (requestId !== state.request) return;
    state.matrix = matrix;
    options(byId("model"), matrix.models.map(m => [m, m]), matrix.model);
    options(byId("conditions"), matrix.condition_options.map(c => [c.id, c.label + " · " + c.id.slice(0, 8)]), matrix.conditions);
    byId("model").disabled = matrix.models.length < 2;
    byId("conditions").disabled = matrix.condition_options.length < 2;
    render();
  } catch (error) { if (requestId === state.request) showError(error); }
}
function render() {
  const matrix = state.matrix;
  const doc = matrix.problem.document;
  byId("problem-title").textContent = doc.title;
  byId("description").textContent = doc.description || "";
  byId("direction").textContent = `${doc.metric.name} · ${doc.metric.direction === "minimize" ? "lower is better" : "higher is better"}`;
  byId("data-label").textContent = doc.demo ? "Synthetic demo data" : "Contributor-reported";
  byId("ranking-note").textContent = `${matrix.ranking} Costs include known ancestors. Pareto highlights use the best observed score and its actual credits.`;
  byId("no-runs").hidden = matrix.entries.length > 0;
  byId("table-container").hidden = matrix.entries.length === 0;
  if (!matrix.entries.some(e => e.id + "/" + e.version === state.selected)) {
    state.selected = matrix.entries[0] ? matrix.entries[0].id + "/" + matrix.entries[0].version : null;
  }
  const body = byId("ranking");
  body.replaceChildren();
  for (const entry of matrix.entries) {
    const row = element("tr");
    row.classList.toggle("selected", state.selected === entry.id + "/" + entry.version);
    const title = element("td");
    const button = element("button", entry.title, "harness-button");
    button.type = "button";
    button.setAttribute("aria-pressed", String(row.classList.contains("selected")));
    button.addEventListener("click", () => { state.selected = entry.id + "/" + entry.version; render(); });
    title.append(button, element("span", entry.version.slice(0, 12), "secondary"));
    row.append(title);
    const score = element("td", entry.score == null ? "No eligible observation" : number(entry.score));
    if (entry.range && entry.range[0] !== entry.range[1]) {
      score.append(element("span", `Range ${number(entry.range[0])}–${number(entry.range[1])}`, "secondary"));
    }
    row.append(score, element("td", dollars(entry.cost)),
               element("td", `${entry.sample_count} eligible / ${entry.attempt_count} recorded`),
               element("td", entry.frontier ? "Pareto frontier" : entry.score == null ? "Unknown" : "Dominated here"));
    body.append(row);
  }
  renderDetail();
}
async function renderDetail() {
  const requestId = ++state.detailRequest;
  const entry = state.matrix.entries.find(e => e.id + "/" + e.version === state.selected);
  byId("detail").hidden = !entry;
  if (!entry) return;
  byId("harness-title").textContent = entry.title;
  byId("harness-version").textContent = "Version " + entry.version.slice(0, 12);
  byId("fetch-command").textContent =
    `uv run catalyst fetch harness ${entry.id} ${entry.version} --output harnesses/${entry.id} --server ${location.origin}`;
  drawChart(entry);
  const runs = byId("runs");
  runs.replaceChildren();
  for (const run of entry.runs) {
    const details = element("details");
    const summary = element("summary");
    const doc = run.document;
    summary.textContent = `${run.id} · ${doc.evidence === "demo" ? "Synthetic demo" : "Reported"} · ${doc.status} · ${dollars(doc.total_cost)}`;
    const facts = element("div", null, "run-facts");
    facts.append(element("span", `Model: ${doc.model}`),
                 element("span", `Selected comparison: ${run.within_budget ? number(run.within_budget.score) : "No comparable observation"}`),
                 element("span", `Input provenance: ${doc.input_provenance || "Contributor supplied"}`));
    if (doc.dungeness_commit) facts.append(element("span", `Dungeness: ${doc.dungeness_commit.slice(0, 12)}`));
    if (!doc.cost_known) facts.append(element("span", "Ancestor cost unknown; excluded from budget ranking."));
    const link = element("a", "Download published run evidence");
    link.href = `/api/bundles/run/${run.id}/${run.version}`;
    details.append(summary, facts, link);
    if (run.report_count) {
      details.append(element("p", `${run.report_count} reported concern(s). No automatic overfitting conclusion.`, "note"));
    }
    details.addEventListener("toggle", async () => {
      if (!details.open || details.dataset.loaded) return;
      details.dataset.loaded = "true";
      try {
        const full = await api(`/api/objects/run/${run.id}/${run.version}`);
        for (const report of full.reports || []) {
          details.append(element("p", report.body, "report"));
          if (report.supporting_run) details.append(element("p", `Supporting run: ${report.supporting_run}`, "note"));
        }
        details.append(element("pre", JSON.stringify(full.document, null, 2)));
      } catch (error) { details.dataset.loaded = ""; details.append(element("p", error.message, "error")); }
    });
    runs.append(details);
  }
  try {
    const full = await api(`/api/objects/harness/${entry.id}/${entry.version}`);
    if (requestId !== state.detailRequest) return;
    byId("harness-description").textContent = full.document.description || "";
    byId("harness-scope").textContent = "Intended scope: " + (full.document.scope || "Not declared");
    byId("method").textContent = full.instructions || "No instructions included in this snapshot.";
    byId("knowledge-files").replaceChildren(...Object.keys(full.files || {}).filter(p => p.startsWith("knowledge/")).map(
      path => element("li", path)));
  } catch (error) { if (requestId === state.detailRequest) showError(error); }
}
function drawChart(entry) {
  const host = byId("chart");
  const width = Math.max(280, host.clientWidth);
  const height = 280, margin = { left: 66, right: 22, top: 22, bottom: 46 };
  const points = entry.runs.flatMap(r => r.document.cost_known === false ? [] : r.document.observations);
  host.replaceChildren();
  byId("legend").replaceChildren();
  if (!points.length) { host.append(element("p", "No observations with comparable cost.", "note")); return; }
  const budget = state.matrix.budget;
  const xmax = Math.max(budget, ...points.map(p => p.cost), .01);
  let ymin = Math.min(...points.map(p => p.score)), ymax = Math.max(...points.map(p => p.score));
  const pad = (ymax - ymin || Math.abs(ymax) || 1) * .08;
  ymin -= pad; ymax += pad;
  const x = cost => margin.left + cost / xmax * (width - margin.left - margin.right);
  const y = score => height - margin.bottom - (score - ymin) / (ymax - ymin) * (height - margin.top - margin.bottom);
  const ns = "http://www.w3.org/2000/svg";
  function svgNode(tag, attributes, text) {
    const node = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attributes || {})) node.setAttribute(key, value);
    if (text != null) node.textContent = text;
    return node;
  }
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}` });
  svg.append(svgNode("title", {}, `${entry.title}: individual observed score-cost trajectories`));
  svg.append(svgNode("rect", { x: margin.left, y: margin.top, width: width-margin.left-margin.right, height: height-margin.top-margin.bottom, class: "chart-frame" }));
  const ticks = width < 480 ? 3 : 5;
  for (let i=0; i<ticks; i++) {
    const cost = xmax*i/(ticks-1), score = ymin+(ymax-ymin)*i/(ticks-1);
    svg.append(svgNode("text", { x: x(cost), y: height-margin.bottom+20, "text-anchor": "middle", class: "chart-text" }, number(cost)));
    svg.append(svgNode("line", { x1: margin.left, x2: width-margin.right, y1: y(score), y2: y(score), class: "chart-grid" }));
    svg.append(svgNode("text", { x: margin.left-9, y: y(score)+4, "text-anchor": "end", class: "chart-text" }, number(score)));
  }
  svg.append(svgNode("text", { x: (margin.left+width-margin.right)/2, y: height-5, "text-anchor": "middle", class: "chart-text" }, "Model credits · reference USD"));
  if (budget != null) {
    svg.append(svgNode("line", { x1:x(budget), x2:x(budget), y1:margin.top, y2:height-margin.bottom, class:"chart-budget" }));
    svg.append(svgNode("text", { x: x(budget)-4, y: margin.top-7, "text-anchor": budget === 0 ? "start" : "end", class:"chart-text" }, `Budget ${dollars(budget)}`));
  }
  entry.runs.forEach((run, index) => {
    if (run.document.cost_known === false) return;
    const observations = [...run.document.observations].sort((a,b) => a.cost-b.cost);
    const opacity = Math.max(.35, 1-index*.16);
    let best = null, path = "";
    for (const point of observations) {
      best = best == null ? point.score : state.matrix.problem.document.metric.direction === "minimize" ? Math.min(best,point.score) : Math.max(best,point.score);
      path += path ? ` H${x(point.cost)} V${y(best)}` : `M${x(point.cost)},${y(best)}`;
      const dot = svgNode("circle", { cx:x(point.cost), cy:y(point.score), r:3, opacity, class:"point" });
      dot.append(svgNode("title", {}, `${run.id}: ${number(point.score)} at ${dollars(point.cost)} (${point.kind})`));
      svg.append(dot);
    }
    svg.append(svgNode("path", { d:path, opacity, class:"curve" }));
    const label = element("span", run.id);
    label.style.opacity = opacity;
    byId("legend").append(label);
  });
  host.append(svg);
}
async function start() {
  try {
    const result = await api("/api/catalog?kind=problem");
    state.objects = result.objects;
    state.tiers = result.budget_tiers;
    options(byId("budget"), state.tiers.map(t => [String(t), t === "best" ? "Best achieved" : dollars(t)]),
            String(state.tiers[0]));
    byId("empty").hidden = result.objects.length > 0;
    byId("content").hidden = result.objects.length === 0;
    if (!result.objects.length) return;
    options(byId("problem"), result.objects.map(p => [p.id+"/"+p.version, `${p.document.title} · ${p.version.slice(0,8)}`]));
    await load(true);
  } catch (error) { showError(error); }
}
byId("filters").addEventListener("submit", event => { event.preventDefault(); load(); });
byId("problem").addEventListener("change", () => load(true));
byId("model").addEventListener("change", () => { byId("conditions").value = ""; load(); });
byId("conditions").addEventListener("change", () => load());
byId("budget").addEventListener("change", () => load());
new ResizeObserver(() => {
  if (!state.matrix) return;
  const entry = state.matrix.entries.find(e => e.id+"/"+e.version === state.selected);
  if (entry) drawChart(entry);
}).observe(byId("chart"));
start();
