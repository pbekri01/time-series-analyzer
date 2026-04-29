const summaryBtn = document.getElementById("summaryBtn");
const exportBtn = document.getElementById("exportBtn");

const out = document.getElementById("out");
const promptOut = document.getElementById("promptOut");
const err = document.getElementById("err");
const statusEl = document.getElementById("status");
const summaryWrap = document.getElementById("summaryWrap");
const warnWrap = document.getElementById("warnWrap");
const overallWrap = document.getElementById("overallWrap");

const entityChartMeta = document.getElementById("entityChartMeta");
const entityChartLegend = document.getElementById("entityChartLegend");
const entityChartMount = document.getElementById("entityChartMount");

const kpiEntities = document.getElementById("kpiEntities");
const kpiPairs = document.getElementById("kpiPairs");
const kpiWarnings = document.getElementById("kpiWarnings");

const toggleJsonBtn = document.getElementById("toggleJsonBtn");
const jsonCardBody = document.getElementById("jsonCardBody");

const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const chatSendBtn = document.getElementById("chatSendBtn");
const resetChatBtn = document.getElementById("resetChatBtn");
const chatStatus = document.getElementById("chatStatus");
const pdfExportBtn = document.getElementById("pdfExportBtn");

const chartModeSelect = document.getElementById("chartModeSelect");
let currentChartMode = "normalized";

let summaryTable = null;
let activeSummaryEntity = null;
let isJsonCollapsed = true;
let loaderTimeout;
let currentEntityJson = null;

function $(id) {
  return document.getElementById(id);
}

function showCard(id) {
  const el = $(id);
  if (el) el.classList.remove("is-hidden");
}

function hideCard(id) {
  const el = $(id);
  if (el) el.classList.add("is-hidden");
}

function toggleCard(id, shouldShow) {
  const el = $(id);
  if (!el) return;
  el.classList.toggle("is-hidden", !shouldShow);
}

function hideCardsForEmptyState() {
  hideCard("warningsCard");
  hideCard("summaryCard");
  hideCard("overallCard");
  hideCard("entityChartCard");
  hideCard("promptCard");
  hideCard("jsonCard");
  hideCard("mapCard");
}

function hasWarnings(summaryJson) {
  const metaWarn = (summaryJson?.meta || {}).warnings || [];
  const entWarnCount = Object.values(summaryJson?.entities || {}).reduce(
    (acc, e) => acc + (e.warnings || []).length,
    0,
  );
  return metaWarn.length > 0 || entWarnCount > 0;
}

function hasSummaryRows(summaryJson) {
  const entities = summaryJson?.entities || {};
  for (const [, edata] of Object.entries(entities)) {
    const top =
      edata.top_pairs && edata.top_pairs.length > 0 ? edata.top_pairs[0] : null;

    if (
      top &&
      top.best_overlap_n != null &&
      edata.n_points != null &&
      edata.n_points >= 3
    ) {
      return true;
    }
  }
  return false;
}

function hasOverallRows(summaryJson) {
  const pairs = (summaryJson?.overall || {}).pairwise || {};
  return Object.keys(pairs).length > 0;
}

function hasPrompt(json) {
  return (
    typeof json?.llm_prompt === "string" && json.llm_prompt.trim().length > 0
  );
}
function getChartModeLabel(mode, chartData) {
  if (mode === "raw") return "raw";
  if (mode === "trend") return "trend";
  if (mode === "residual") return "residual";
  if (mode === "differenced") return "differenced";
  return chartData.normalization || "normalized";
}
function hasEntityChart(json) {
  const entities = json?.entities || {};
  const entityName = Object.keys(entities)[0];
  if (!entityName) return false;

  const ent = entities[entityName] || {};
  const chartData = ent.chart_data;
  if (!chartData || !chartData.series) return false;

  const seriesKey = getSeriesKeyForMode(currentChartMode);

  const seriesEntries = Object.entries(chartData.series || {});
  return seriesEntries.some(
    ([, s]) =>
      Array.isArray(s[seriesKey]) &&
      s[seriesKey].some((v) => typeof v === "number" && Number.isFinite(v)),
  );
}
function getSeriesKeyForMode(mode) {
  if (mode === "raw") return "raw_values";
  if (mode === "trend") return "trend_values";
  if (mode === "residual") return "residual_values";
  if (mode === "differenced") return "differenced_values";
  return "normalized_values";
}
function hasJsonContent(value) {
  if (value == null) return false;
  if (typeof value === "string")
    return value.trim().length > 0 && value.trim() !== "{}";
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function hasMapContent() {
  const mapFrame = $("mapFrame");
  if (!mapFrame) return false;

  const text = (mapFrame.textContent || "").trim();
  const hasPlot = !!mapFrame.querySelector(".js-plotly-plot");
  const hasIframe = !!mapFrame.querySelector("iframe");
  const hasSvg = !!mapFrame.querySelector("svg");

  if (hasPlot || hasIframe || hasSvg) return true;
  if (!text) return false;

  return !/^(failed to load map\.?|no map|empty)$/i.test(text);
}

function syncMapCardVisibility() {
  toggleCard("mapCard", hasMapContent());
}

function syncJsonCardVisibility(value) {
  toggleCard("jsonCard", hasJsonContent(value));
}

async function setActiveSummaryEntity(entityName, options = {}) {
  const { syncDropdown = true, scrollToRow = true } = options || {};

  activeSummaryEntity = entityName || null;

 

  if (!summaryTable || !entityName) return;

  if (typeof summaryTable.deselectRow === "function") {
    summaryTable.deselectRow();
  }

  const row = summaryTable
    .getRows()
    .find((r) => (r.getData()?.entity || "") === entityName);

  if (!row) return;

  try {
    if (scrollToRow && typeof row.pageTo === "function") {
      await row.pageTo();
    }

    if (typeof row.select === "function") {
      row.select();
    }

    if (scrollToRow && typeof row.scrollTo === "function") {
      await row.scrollTo("center", true);
    }
  } catch (error) {
    console.warn("Could not page/scroll to summary row:", error);

    if (typeof row.select === "function") {
      row.select();
    }
  }
}

function escapeHtml(s) {
  return (s ?? "")
    .toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function fmtNum(value, digits = 3) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "";
}

function formatOverlapRange(overlapRange) {
  if (!overlapRange || overlapRange.start == null || overlapRange.end == null) {
    return "–";
  }
  return `${overlapRange.start}–${overlapRange.end}`;
}

function setStatus(text, type = "idle") {
  if (!statusEl) return;

  statusEl.textContent = text;
  statusEl.className = "status-badge";

  if (type === "success") {
    statusEl.classList.add("is-success");
  } else if (type === "error") {
    statusEl.classList.add("is-error");
  }

  statusEl.style.transition = "all 0.2s ease";
}

function clearError() {
  err.textContent = "";
  err.classList.remove("show");
}

function showError(message) {
  err.textContent = message;
  err.classList.add("show");
  setStatus("Error", "error");
}

function setEmptyState(el, text) {
  el.innerHTML = `<div class="empty-state">${escapeHtml(text)}</div>`;
}

function resetKpis() {
  kpiEntities.textContent = "0";
  kpiPairs.textContent = "0";
  kpiWarnings.textContent = "0";
}

function clearSummaryTable() {
  if (summaryTable) {
    summaryTable.destroy();
    summaryTable = null;
  }

  if ($("summarySearch")) $("summarySearch").value = "";
  if ($("significantOnly")) $("significantOnly").checked = false;
  if ($("hideSpurious")) $("hideSpurious").checked = false;

  setEmptyState(summaryWrap, "Run a summary analysis to see results here.");
  hideCard("summaryCard");
  activeSummaryEntity = null;
}

function clearWarnings() {
  setEmptyState(warnWrap, "No warnings yet.");
  hideCard("warningsCard");
}

function clearOverall() {
  setEmptyState(
    overallWrap,
    "Overall statistics will appear here after analysis.",
  );
  hideCard("overallCard");
}

function clearPrompt() {
  promptOut.textContent = "";
  hideCard("promptCard");
}

function clearJson() {
  out.textContent = "{}";
  syncJsonCardVisibility("{}");
}

function clearEntityChart() {
  if (entityChartMeta) {
    entityChartMeta.textContent = "Load an entity to see the chart.";
  }
  if (entityChartLegend) {
    entityChartLegend.innerHTML = "";
  }
  if (entityChartMount) {
    entityChartMount.innerHTML = `<div class="empty-state">No chart yet.</div>`;
  }
  hideCard("entityChartCard");
}

function resetOutputs() {
  clearJson();
  clearPrompt();
  resetKpis();
  clearEntityChart();
  clearSummaryTable();
  clearOverall();
  clearWarnings();
  syncMapCardVisibility();
  currentEntityJson = null;
}

function updateKpisFromSummary(summaryJson) {
  const entitiesObj = summaryJson.entities || {};
  const overallPairsObj = (summaryJson.overall || {}).pairwise || {};
  const metaWarnings = (summaryJson.meta || {}).warnings || [];

  const entityCount = Object.keys(entitiesObj).length;
  const overallPairCount = Object.keys(overallPairsObj).length;

  let entityWarningCount = 0;
  for (const entData of Object.values(entitiesObj)) {
    entityWarningCount += (entData.warnings || []).length;
  }

  const totalWarnings = metaWarnings.length + entityWarningCount;

  kpiEntities.textContent = String(entityCount);
  kpiPairs.textContent = String(overallPairCount);
  kpiWarnings.textContent = String(totalWarnings);
}

function renderWarnings(summaryJson) {
  const metaWarn = (summaryJson.meta || {}).warnings || [];
  const entWarnCount = Object.values(summaryJson.entities || {}).reduce(
    (acc, e) => acc + (e.warnings || []).length,
    0,
  );

  if (metaWarn.length === 0 && entWarnCount === 0) {
    clearWarnings();
    return;
  }

  let html = `<div class="section-title">Warnings</div>`;

  if (metaWarn.length) {
    html += `<div class="muted" style="margin-bottom:8px;"><b>Global warnings</b></div>`;
    html += `<ul class="warning-list">`;
    for (const w of metaWarn) {
      html += `<li>${escapeHtml(w)}</li>`;
    }
    html += `</ul>`;
  }

  const ents = summaryJson.entities || {};
  let shown = 0;
  const limit = 10;

  html += `<div class="muted" style="margin-top:14px; margin-bottom:8px;"><b>Entity warnings</b></div>`;
  html += `<ul class="warning-list">`;

  for (const [ename, edata] of Object.entries(ents)) {
    for (const w of edata.warnings || []) {
      if (shown >= limit) break;
      html += `<li><span class="mono">${escapeHtml(ename)}</span>: ${escapeHtml(w)}</li>`;
      shown += 1;
    }
    if (shown >= limit) break;
  }

  html += `</ul>`;

  if (entWarnCount > limit) {
    html += `<div class="muted" style="margin-top:10px;">(+${entWarnCount - limit} more warnings not shown)</div>`;
  }

  warnWrap.innerHTML = html;
  showCard("warningsCard");
}

function formatP(p) {
  if (p === null || p === undefined) return "–";
  if (typeof p === "string") return p;

  const num = Number(p);
  if (!Number.isFinite(num)) return "–";

  if (num < 0.001) return "<0.001";
  if (num < 0.01) return num.toFixed(3);
  if (num < 0.1) return num.toFixed(2);

  return num.toFixed(2);
}

function isSignificant(p) {
  if (p === null || p === undefined) return false;

  if (typeof p === "string") {
    if (p.trim() === "<1e-4") return true;
    const num = Number(p);
    return Number.isFinite(num) && num < 0.05;
  }

  const num = Number(p);
  return Number.isFinite(num) && num < 0.05;
}

function corrClass(v) {
  if (v === null || v === undefined) return "";

  const n = Number(v);
  if (!Number.isFinite(n)) return "";

  const a = Math.abs(n);

  if (a > 0.8) return n > 0 ? "corr-strong-pos" : "corr-strong-neg";
  if (a > 0.5) return n > 0 ? "corr-med-pos" : "corr-med-neg";
  return "corr-weak";
}

function renderSummaryTable(summaryJson) {
  const entities = summaryJson.entities || {};
  const rows = [];

  for (const [ename, edata] of Object.entries(entities)) {
    const pairs = Array.isArray(edata.top_pairs) ? edata.top_pairs : [];

    if (pairs.length === 0) {
      continue;
    }

    for (const pair of pairs) {
      if (!pair || pair.best_overlap_n == null) {
        continue;
      }

      rows.push({
        entity: ename,
        rangeText: formatOverlapRange(edata.overlap_range),
        n: edata.n_points,
        A: pair.series_A || "–",
        B: pair.series_B || "–",
        overlap0: pair.overlap_n_lag0 ?? null,
        bestOverlap: pair.best_overlap_n ?? null,
        bestLag: pair.best_lag ?? null,
        bestCorr: pair.best_corr ?? null,
        maxAbs: pair.max_abs_corr ?? null,
        corr0: pair.corr_lag0 ?? null,
        pCorr: pair.pearson_p_value ?? null,
        significant: isSignificant(pair.pearson_p_value ?? null),
        trend: pair.trend_corr ?? null,
        resid: pair.residual_corr ?? null,
        diff: pair.diff_corr ?? null,
        pDiff: pair.diff_p_value ?? null,
        spurious: pair.spurious_risk ?? false,
        season: pair.seasonality_overlap ?? null,
      });
    }
  }

  if (rows.length === 0) {
    clearSummaryTable();
    return;
  }

  if (summaryTable) {
    summaryTable.destroy();
    summaryTable = null;
  }

  summaryWrap.classList.remove("empty-state");
  summaryWrap.style.pointerEvents = "auto";
  summaryWrap.innerHTML = `<div id="summaryGrid"></div>`;

  summaryTable = new Tabulator("#summaryGrid", {
    data: rows,
    height: "500px",
    maxHeight: "500px",
    layout: "fitDataStretch",
    responsiveLayout: false,
    pagination: true,
    paginationSize: 10,
    movableColumns: true,
    resizableColumns: true,
    initialSort: [{ column: "maxAbs", dir: "desc" }],
    selectableRows: 1,

    rowFormatter: function (row) {
      const el = row.getElement();
      const data = row.getData() || {};
      el.dataset.entity = data.entity || "";
      el.style.cursor = "pointer";
    },

    columns: [
      {
        title: "Entity",
        field: "entity",
        minWidth: 170,
        frozen: true,
        responsive: 0,
      },
      {
        title: "Range",
        field: "rangeText",
        minWidth: 120,
        frozen: true,
        responsive: 2,
        formatter: (cell) =>
          `<span class="metric-muted">${escapeHtml(cell.getValue() || "–")}</span>`,
      },
      {
        title: "n",
        field: "n",
        hozAlign: "right",
        sorter: "number",
        width: 80,
        responsive: 2,
      },
      {
        title: "Series A",
        field: "A",
        minWidth: 200,
        maxWidth: 280,
        tooltip: true,
        responsive: 0,
        formatter: (cell) =>
          `<span class="series-pill">${escapeHtml(cell.getValue() || "–")}</span>`,
      },
      {
        title: "Series B",
        field: "B",
        minWidth: 200,
        maxWidth: 280,
        tooltip: true,
        responsive: 0,
        formatter: (cell) =>
          `<span class="series-pill">${escapeHtml(cell.getValue() || "–")}</span>`,
      },
      {
        title: "overlap@0",
        field: "overlap0",
        hozAlign: "right",
        sorter: "number",
        width: 110,
        responsive: 2,
        formatter: (cell) => {
          const v = cell.getValue();
          return v == null ? "–" : `<span class="metric-muted">${v}</span>`;
        },
      },
      {
        title: "overlap@best",
        field: "bestOverlap",
        hozAlign: "right",
        sorter: "number",
        width: 130,
        responsive: 2,
        formatter: (cell) => {
          const v = cell.getValue();
          return v == null ? "–" : `<span class="metric-muted">${v}</span>`;
        },
      },
      {
        title: "Best lag",
        field: "bestLag",
        hozAlign: "right",
        sorter: "number",
        width: 100,
        responsive: 1,
        formatter: (cell) => {
          const v = cell.getValue();
          return v == null ? "–" : `<span class="metric-strong">${v}</span>`;
        },
      },
      {
        title: "Best corr",
        field: "bestCorr",
        hozAlign: "right",
        sorter: "number",
        responsive: 0,
        formatter: (cell) => {
          const v = cell.getValue();
          if (v == null) return "–";
          return `<span class="metric-strong ${corrClass(v)}">${fmtNum(v)}</span>`;
        },
      },
      {
        title: "|corr|",
        field: "maxAbs",
        hozAlign: "right",
        sorter: "number",
        responsive: 1,
        formatter: (cell) => {
          const v = cell.getValue();
          if (v == null) return "–";
          return `<span class="metric-strong">${fmtNum(v)}</span>`;
        },
      },
      {
        title: "corr@0",
        field: "corr0",
        hozAlign: "right",
        sorter: "number",
        responsive: 1,
        formatter: (cell) => {
          const v = cell.getValue();
          if (v == null) return "–";
          return `<span class="${corrClass(v)}">${fmtNum(v)}</span>`;
        },
      },
      {
        title: "p(corr)",
        field: "pCorr",
        sorter: "string",
        responsive: 2,
        formatter: (cell) => formatP(cell.getValue()),
      },
      {
        title: "signif",
        field: "significant",
        sorter: "boolean",
        responsive: 1,
        formatter: (cell) => {
          const v = cell.getValue();
          return v
            ? `<span class="tab-badge-yes">Yes</span>`
            : `<span class="tab-badge-no">No</span>`;
        },
      },
      {
        title: "trend",
        field: "trend",
        hozAlign: "right",
        sorter: "number",
        responsive: 2,
        formatter: (cell) => {
          const v = cell.getValue();
          return v == null ? "–" : fmtNum(v);
        },
      },
      {
        title: "resid",
        field: "resid",
        hozAlign: "right",
        sorter: "number",
        responsive: 2,
        formatter: (cell) => {
          const v = cell.getValue();
          return v == null ? "–" : fmtNum(v);
        },
      },
      {
        title: "diff",
        field: "diff",
        hozAlign: "right",
        sorter: "number",
        responsive: 2,
        formatter: (cell) => {
          const v = cell.getValue();
          return v == null ? "–" : fmtNum(v);
        },
      },
      {
        title: "p(diff)",
        field: "pDiff",
        sorter: "string",
        responsive: 2,
        formatter: (cell) => formatP(cell.getValue()),
      },
      {
        title: "spurious",
        field: "spurious",
        sorter: "boolean",
        responsive: 1,
        formatter: (cell) => {
          const v = cell.getValue();
          return v
            ? `<span class="tab-badge-warn">Risk</span>`
            : `<span class="tab-badge-ok">Low</span>`;
        },
      },
      {
        title: "season",
        field: "season",
        sorter: "boolean",
        responsive: 2,
        formatter: (cell) => {
          const v = cell.getValue();
          if (v == null) return "–";
          return v
            ? `<span class="tab-badge-yes">Yes</span>`
            : `<span class="tab-badge-no">No</span>`;
        },
      },
    ],
  });

  const summarySearch = $("summarySearch");
  const summarySignifOnly = $("significantOnly");
  const summaryHideSpurious = $("hideSpurious");
  function applySummaryFilters() {
    if (!summaryTable) return;

    const searchValue = (summarySearch?.value || "").trim().toLowerCase();
    const signifOnly = !!summarySignifOnly?.checked;
    const hideSpurious = !!summaryHideSpurious?.checked;

    const filters = [];

    if (signifOnly) {
      filters.push({ field: "significant", type: "=", value: true });
    }

    if (hideSpurious) {
      filters.push({ field: "spurious", type: "=", value: false });
    }

    if (searchValue) {
      filters.push([
        { field: "entity", type: "like", value: searchValue },
        { field: "A", type: "like", value: searchValue },
        { field: "B", type: "like", value: searchValue },
      ]);
    }

    summaryTable.setFilter(filters);
  }
  if (summarySearch) summarySearch.oninput = applySummaryFilters;
  if (summarySignifOnly) summarySignifOnly.onchange = applySummaryFilters;
  if (summaryHideSpurious) summaryHideSpurious.onchange = applySummaryFilters;

  const summaryGridEl = $("summaryGrid");

  if (summaryGridEl) {
    summaryGridEl.onclick = async function (e) {
      const rowEl = e.target.closest(".tabulator-row");
      if (!rowEl) return;

      const entityName = rowEl.dataset.entity;
      if (!entityName) return;

      summaryGridEl.querySelectorAll(".tabulator-row").forEach((r) => {
        r.classList.remove("is-active");
      });

      rowEl.classList.add("is-active");
      rowEl.classList.add("is-loading");

      await setActiveSummaryEntity(entityName, {
        syncDropdown: true,
        scrollToRow: false,
      });

      await loadEntityByName(entityName);

      rowEl.classList.remove("is-loading");

      $("entityChartWrap")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    };
  }

  if (activeSummaryEntity) {
    setActiveSummaryEntity(activeSummaryEntity, {
      syncDropdown: false,
      scrollToRow: true,
    });
  }

  showCard("summaryCard");
}

function renderOverallTable(summaryJson) {
  const pairs = (summaryJson.overall || {}).pairwise || {};
  const rows = [];

  for (const [pairKey, v] of Object.entries(pairs)) {
    rows.push({
      pair: pairKey,
      n: v.n_entities,
      mean: v.mean_corr_lag0,
      median: v.median_corr_lag0,
      pctNeg: v.pct_negative,
      pctPos: v.pct_positive,
      nNeg: v.n_negative,
      nPos: v.n_positive,
    });
  }

  if (rows.length === 0) {
    clearOverall();
    return;
  }

  rows.sort((a, b) => Math.abs(b.mean ?? 0) - Math.abs(a.mean ?? 0));

  let html = `<div class="table-wrap"><table><thead><tr>
    <th>Pair</th>
    <th>#Entities</th>
    <th>Mean corr@0</th>
    <th>Median corr@0</th>
    <th>%Negative</th>
    <th>%Positive</th>
    <th>Neg</th>
    <th>Pos</th>
  </tr></thead><tbody>`;

  for (const r of rows) {
    const negTxt =
      typeof r.pctNeg === "number" && Number.isFinite(r.pctNeg)
        ? (r.pctNeg * 100).toFixed(1) + "%"
        : "";

    const posTxt =
      typeof r.pctPos === "number" && Number.isFinite(r.pctPos)
        ? (r.pctPos * 100).toFixed(1) + "%"
        : "";

    html += `<tr>
      <td class="mono">${escapeHtml(r.pair)}</td>
      <td>${r.n ?? ""}</td>
      <td>${fmtNum(r.mean)}</td>
      <td>${fmtNum(r.median)}</td>
      <td>${negTxt}</td>
      <td>${posTxt}</td>
      <td>${r.nNeg ?? ""}</td>
      <td>${r.nPos ?? ""}</td>
    </tr>`;
  }

  html += `</tbody></table></div>`;
  overallWrap.innerHTML = html;
  showCard("overallCard");
}



function buildBaseFormData() {
  const filesInput = $("files");

  if (!filesInput.files || filesInput.files.length === 0) {
    return null;
  }

  const form = new FormData();

  for (const f of filesInput.files) {
    form.append("files", f);
  }

  form.append("period", "1");
  return form;
}

function buildLinePathWithScales(xs, ys, xPos, yPos) {
  const valid = [];

  for (let i = 0; i < xs.length; i += 1) {
    const x = xs[i];
    const y = ys[i];

    if (
      typeof x === "number" &&
      Number.isFinite(x) &&
      typeof y === "number" &&
      Number.isFinite(y)
    ) {
      valid.push([x, y]);
    }
  }

  if (valid.length < 2) {
    return "";
  }

  return valid
    .map(
      ([x, y], idx) =>
        `${idx === 0 ? "M" : "L"} ${xPos(x).toFixed(2)} ${yPos(y).toFixed(2)}`,
    )
    .join(" ");
}

function renderEntityChart(json) {
  clearEntityChart();

  const entities = json.entities || {};
  const entityName = Object.keys(entities)[0];
  if (!entityName) {
    return;
  }

  const ent = entities[entityName] || {};
  const chartData = ent.chart_data;
  const seriesKey = getSeriesKeyForMode(currentChartMode);
  if (!chartData || !chartData.series) {
    entityChartMeta.textContent = "No chart data available for this entity.";
    entityChartMount.innerHTML = `<div class="empty-state">No chart data available.</div>`;
    hideCard("entityChartCard");
    return;
  }

  const allYears = chartData.years || [];
  const seriesEntries = Object.entries(chartData.series || {});
  const usableSeries = seriesEntries.filter(
    ([, s]) =>
      Array.isArray(s[seriesKey]) &&
      s[seriesKey].some((v) => typeof v === "number" && Number.isFinite(v)),
  );

  if (usableSeries.length === 0) {
    entityChartMeta.textContent =
      "No plottable series available for this entity.";
    entityChartMount.innerHTML = `<div class="empty-state">No plottable series available.</div>`;
    hideCard("entityChartCard");
    return;
  }

  entityChartMeta.textContent = `${entityName} · ${formatOverlapRange(ent.overlap_range)} · ${getChartModeLabel(currentChartMode, chartData)} view`;
  const palette = [
    "#2563eb",
    "#dc2626",
    "#059669",
    "#7c3aed",
    "#ea580c",
    "#0891b2",
  ];
  function getValueLabel(mode) {
    if (mode === "raw") return "Raw value";
    if (mode === "trend") return "Trend value";
    if (mode === "residual") return "Residual value";
    if (mode === "differenced") return "Differenced value";
    return "Normalized value";
  }

  entityChartLegend.innerHTML = usableSeries
    .map(
      ([name], idx) => `
        <span class="entity-chart-legend-item">
          <span class="entity-chart-swatch" style="background:${palette[idx % palette.length]}"></span>
          ${escapeHtml(name)}
        </span>
      `,
    )
    .join("");

  const width = 960;
  const height = 360;
  const pad = { top: 20, right: 20, bottom: 40, left: 50 };

  const allNumericY = [];
  for (const [, s] of usableSeries) {
    for (const v of s[seriesKey] || []) {
      if (typeof v === "number" && Number.isFinite(v)) {
        allNumericY.push(v);
      }
    }
  }

  const yearsNumeric = allYears.filter(
    (v) => typeof v === "number" && Number.isFinite(v),
  );

  if (yearsNumeric.length === 0 || allNumericY.length === 0) {
    entityChartMeta.textContent =
      "No numeric chart data available for this entity.";
    entityChartMount.innerHTML = `<div class="empty-state">No numeric chart data available.</div>`;
    hideCard("entityChartCard");
    return;
  }

  const minYear = Math.min(...yearsNumeric);
  const maxYear = Math.max(...yearsNumeric);
  const minY = Math.min(...allNumericY);
  const maxY = Math.max(...allNumericY);

  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const xPos = (x) => {
    if (maxYear === minYear) return pad.left + innerW / 2;
    return pad.left + ((x - minYear) / (maxYear - minYear)) * innerW;
  };

  const yPos = (y) => {
    if (maxY === minY) return pad.top + innerH / 2;
    return pad.top + innerH - ((y - minY) / (maxY - minY)) * innerH;
  };

  const hasZeroLine = minY <= 0 && maxY >= 0;

  const yTicks = 5;
  const xTicks = Math.min(6, yearsNumeric.length);

  let svg = `
    <svg class="entity-chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Selected entity chart">
      <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"></rect>
  `;

  for (let i = 0; i < yTicks; i += 1) {
    const t = i / (yTicks - 1);
    const yVal = maxY - (maxY - minY) * t;
    const y = yPos(yVal);
    svg += `
      <line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="#e5e7eb" stroke-width="1"></line>
      <text x="${pad.left - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#6b7280">${yVal.toFixed(2)}</text>
    `;
  }

  for (let i = 0; i < xTicks; i += 1) {
    const t = xTicks === 1 ? 0 : i / (xTicks - 1);
    const xVal = Math.round(minYear + (maxYear - minYear) * t);
    const x = xPos(xVal);
    svg += `
      <line x1="${x}" y1="${pad.top}" x2="${x}" y2="${height - pad.bottom}" stroke="#f3f4f6" stroke-width="1"></line>
      <text x="${x}" y="${height - 12}" text-anchor="middle" font-size="11" fill="#6b7280">${xVal}</text>
    `;
  }

  if (hasZeroLine) {
    const y0 = yPos(0);
    svg += `
      <line
        x1="${pad.left}"
        y1="${y0}"
        x2="${width - pad.right}"
        y2="${y0}"
        stroke="#9ca3af"
        stroke-width="1.5"
        stroke-dasharray="4 4"
      ></line>
      <text
        x="${pad.left - 8}"
        y="${y0 - 6}"
        text-anchor="end"
        font-size="11"
        fill="#6b7280"
      >0</text>
    `;
  }

  svg += `
    <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#374151" stroke-width="1.2"></line>
    <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#374151" stroke-width="1.2"></line>
  `;

  usableSeries.forEach(([name, s], idx) => {
    const color = palette[idx % palette.length];
    const values = s[seriesKey] || [];
    const path = buildLinePathWithScales(allYears, values, xPos, yPos);

    if (path) {
      svg += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></path>`;
    }

    values.forEach((v, i) => {
      const year = allYears[i];
      if (
        typeof year !== "number" ||
        !Number.isFinite(year) ||
        typeof v !== "number" ||
        !Number.isFinite(v)
      ) {
        return;
      }

      const cx = xPos(year);
      const cy = yPos(v);

      svg += `
        <circle
          cx="${cx}"
          cy="${cy}"
          r="4"
          fill="${color}"
          opacity="0.9"
          class="entity-chart-point"
          style="pointer-events: all;"
          data-series="${escapeHtml(name)}"
          data-year="${year}"
          data-value="${v.toFixed(3)}"
        ></circle>
      `;
    });
  });

  svg += `</svg>`;
  entityChartMount.innerHTML = svg;

  const chartSvg = entityChartMount.querySelector(".entity-chart-svg");

  if (chartSvg) {
    chartSvg.addEventListener("mousemove", (e) => {
      const point = e.target.closest(".entity-chart-point");

      if (!point) {
        if (entityChartTooltip) {
          entityChartTooltip.classList.add("is-hidden");
        }
        return;
      }

      if (!entityChartTooltip) return;

      const series = point.dataset.series || "";
      const year = point.dataset.year || "";
      const value = point.dataset.value || "";

      const valueLabel = getValueLabel(currentChartMode);

      entityChartTooltip.innerHTML = `
      <div><strong>${escapeHtml(series)}</strong></div>
      <div>Year: ${escapeHtml(year)}</div>
      <div>${escapeHtml(valueLabel)}: ${escapeHtml(value)}</div>
      `;

      const rect = entityChartMount.getBoundingClientRect();
      entityChartTooltip.style.left = `${e.clientX - rect.left + 12}px`;
      entityChartTooltip.style.top = `${e.clientY - rect.top + 12}px`;
      entityChartTooltip.classList.remove("is-hidden");
    });

    chartSvg.addEventListener("mouseleave", () => {
      if (entityChartTooltip) {
        entityChartTooltip.classList.add("is-hidden");
      }
    });
  }
  showCard("entityChartCard");
}

async function postAnalyze(form) {
  const res = await fetch("/api/analyze/", {
    method: "POST",
    body: form,
  });

  const text = await res.text();
  let json = null;

  try {
    json = JSON.parse(text);
  } catch (_) {
    json = null;
  }

  if (!res.ok) {
    const msg =
      json && (json.error || json.detail)
        ? json.error || json.detail
        : `HTTP ${res.status} ${res.statusText}`;

    throw new Error(msg);
  }

  return json;
}
function setJsonCollapsed(collapsed) {
  if (!toggleJsonBtn || !jsonCardBody) return;

  if (collapsed) {
    jsonCardBody.style.display = "none";
    toggleJsonBtn.textContent = "Expand";
  } else {
    jsonCardBody.style.display = "";
    toggleJsonBtn.textContent = "Collapse";
  }
}

summaryBtn.addEventListener("click", async () => {
  clearError();
  clearJson();
  clearPrompt();
  clearEntityChart();
  setStatus("Analyzing summary...");
  startLoading("Analyzing summary...");

  const form = buildBaseFormData();
  if (!form) {
    showError("Please select CSV files first.");
    stopLoading();
    return;
  }

  form.append("return_mode", "summary");

  try {
    const json = await postAnalyze(form);

    setStatus("Summary loaded.", "success");
    out.textContent = JSON.stringify(json, null, 2);
    syncJsonCardVisibility(json);

    updateKpisFromSummary(json);
    renderWarnings(json);
    renderSummaryTable(json);
    renderOverallTable(json);
    syncMapCardVisibility();

    window.dispatchEvent(new CustomEvent("analysis:updated"));
  } catch (e) {
    showError(e.toString());
    clearWarnings();
    clearSummaryTable();
    clearOverall();
    clearEntityChart();
    clearPrompt();
    clearJson();
  } finally {
    stopLoading();
  }
});

async function loadEntityByName(entityName) {
  clearError();
  clearJson();
  clearPrompt();
  clearEntityChart();
  setStatus("Loading selected entity...");
  startLoading(`Loading ${entityName}...`);

  const form = buildBaseFormData();
  if (!form) {
    showError("Please select CSV files first.");
    stopLoading();
    return;
  }

  if (!entityName) {
    showError("Select an entity first.");
    stopLoading();
    return;
  }

  form.append("return_mode", "entity");
  form.append("entity", entityName);
  form.append("include_prompt", "true");
  form.append("top_pairs", "10");
  form.append("top_freqs", "5");

  try {
    const json = await postAnalyze(form);
    currentEntityJson = json;

    setStatus("Entity loaded.", "success");
    out.textContent = JSON.stringify(json, null, 2);
    syncJsonCardVisibility(json);

    if (hasPrompt(json)) {
      promptOut.textContent = json.llm_prompt;
      showCard("promptCard");
    } else {
      clearPrompt();
    }

    renderEntityChart(json);

    window.dispatchEvent(new CustomEvent("entity:loaded"));
  } catch (e) {
    showError(e.toString());
    clearPrompt();
    clearEntityChart();
    clearJson();
  } finally {
    stopLoading();
  }
}



exportBtn.addEventListener("click", async () => {
  clearError();
  setStatus("Preparing ZIP export...");
  startLoading("Preparing ZIP export...");

  const form = buildBaseFormData();
  if (!form) {
    showError("Please select CSV files first.");
    stopLoading();
    return;
  }

  form.append("return_mode", "export");

  try {
    const res = await fetch("/api/analyze/", {
      method: "POST",
      body: form,
    });

    if (!res.ok) {
      const t = await res.text();
      throw new Error(`Export failed: HTTP ${res.status}\n\n${t}`);
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "tsproj_results.zip";
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
    setStatus("ZIP downloaded.", "success");
  } catch (e) {
    showError(e.toString());
  } finally {
    stopLoading();
  }
});

if (pdfExportBtn) {
  pdfExportBtn.addEventListener("click", () => {
    clearError();

    if (!summaryTable) {
      showError("Run a summary analysis first so the PDF report has data.");
      return;
    }

    setStatus("Opening PDF report...");
    downloadPdfReport();
    setStatus("PDF report ready for print/save.", "success");
  });
}

window.setActiveSummaryEntity = setActiveSummaryEntity;
window.loadEntityByName = loadEntityByName;

if (toggleJsonBtn && jsonCardBody) {
  toggleJsonBtn.addEventListener("click", () => {
    isJsonCollapsed = !isJsonCollapsed;
    setJsonCollapsed(isJsonCollapsed);
  });
}

function startLoading(text = "Loading…") {
  const el = $("globalLoader");
  if (!el) return;

  const textEl = el.querySelector(".loader-text");
  if (textEl) textEl.textContent = text;

  loaderTimeout = setTimeout(() => {
    el.classList.add("active");
  }, 120);
}

function stopLoading() {
  clearTimeout(loaderTimeout);
  const el = $("globalLoader");
  if (!el) return;
  el.classList.remove("active");
}

document.addEventListener("DOMContentLoaded", () => {
  if (statusEl) {
    setStatus("Ready");
  }

  resetOutputs();
  hideCardsForEmptyState();
  setJsonCollapsed(true);

  setTimeout(() => {
    syncMapCardVisibility();
  }, 300);
});

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let cookie of cookies) {
      cookie = cookie.trim();
      if (cookie.startsWith(name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function hasAnalysisLoaded() {
  return Number(kpiEntities?.textContent || 0) > 0 || hasMapContent();
}

function setChatStatus(message) {
  if (chatStatus) chatStatus.textContent = message;
}

function appendChatMessage(role, text) {
  if (!chatMessages) return;

  const isEmpty = chatMessages.querySelector(".chat-empty");
  if (isEmpty) isEmpty.remove();

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}`;

  const label = document.createElement("div");
  label.className = "chat-role";
  label.textContent = role === "user" ? "You" : "Assistant";

  const body = document.createElement("div");
  body.className = "chat-body";
  body.textContent = text;

  bubble.appendChild(label);
  bubble.appendChild(body);
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage() {
  if (!chatInput || !chatSendBtn) return;

  const message = chatInput.value.trim();
  if (!message) return;

  if (!hasAnalysisLoaded()) {
    setChatStatus("Run an analysis first so the assistant has context.");
    return;
  }

  const entity = activeSummaryEntity  || "";
  appendChatMessage("user", message);
  chatInput.value = "";
  chatSendBtn.disabled = true;
  setChatStatus("Thinking…");

  try {
    const res = await fetch("/api/chat/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({ message, entity }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `Chat failed with HTTP ${res.status}`);
    }

    appendChatMessage("assistant", data.answer || "");
    setChatStatus("Ready for the next question.");
  } catch (error) {
    appendChatMessage("assistant", `Error: ${error.message || error}`);
    setChatStatus("Chat request failed.");
  } finally {
    chatSendBtn.disabled = false;
    chatInput?.focus();
  }
}
async function resetChat() {
  if (!chatMessages) return;

  try {
    await fetch("/api/chat/reset/", {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
    });
  } catch (error) {
    console.warn("Could not reset server chat history:", error);
  }

  chatMessages.innerHTML =
    '<div class="chat-empty">Run an analysis, then ask the assistant to explain the results.</div>';
  setChatStatus("Chat cleared.");
}
if (chatSendBtn) {
  chatSendBtn.addEventListener("click", sendChatMessage);
}

if (chatInput) {
  chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChatMessage();
    }
  });
}

if (resetChatBtn) {
  resetChatBtn.addEventListener("click", resetChat);
}

const explainEntityBtn = document.getElementById("explainEntityBtn");

function explainSelectedEntity() {
  if (!chatInput) return;

  const entity = activeSummaryEntity || "";

  if (!entity) {
    setChatStatus("Select an entity from the summary table first.");
    return;
  }

  if (currentEntityJson && hasPrompt(currentEntityJson)) {
    const message = `${currentEntityJson.llm_prompt}
    Extra rules:
- Be strict with dates and historical facts.
- If uncertain about a specific law or reform, use broader historical context instead.
- Focus mainly on pairwise metrics, residual correlation, differenced correlation, and lag.
- If both series were differenced, interpret the relationship as co-movement in changes.
`.trim();

    chatInput.value = message.trim();
    sendChatMessage();
  } else {
    const message = `Explain the most important insights for ${entity} based on the analysis.`;

    chatInput.value = message;
    sendChatMessage();
  }
}

if (explainEntityBtn) {
  explainEntityBtn.addEventListener("click", explainSelectedEntity);
}
const entityChartTooltip = document.getElementById("entityChartTooltip");

document.querySelectorAll(".chart-toggle button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document
      .querySelectorAll(".chart-toggle button")
      .forEach((b) => b.classList.remove("active"));

    btn.classList.add("active");

    currentChartMode = btn.dataset.mode;

    if (currentEntityJson) {
      renderEntityChart(currentEntityJson);
    }
  });
});


function buildPdfTableHtmlFromSummary() {
  if (!summaryTable) {
    return `<div class="report-empty">No summary results available.</div>`;
  }

  const rows = summaryTable.getData("active") || [];

  if (!rows.length) {
    return `<div class="report-empty">No summary rows match the current filters.</div>`;
  }

  const headers = [
    "Entity",
    "Range",
    "n",
    "Series A",
    "Series B",
    "Best lag",
    "Best corr",
    "|corr|",
    "corr@0",
    "p(corr)",
    "diff",
    "spurious",
  ];

  const body = rows
    .map((row) => `
      <tr>
        <td>${escapeHtml(row.entity || "–")}</td>
        <td>${escapeHtml(row.rangeText || "–")}</td>
        <td>${escapeHtml(row.n ?? "–")}</td>
        <td>${escapeHtml(row.A || "–")}</td>
        <td>${escapeHtml(row.B || "–")}</td>
        <td>${escapeHtml(row.bestLag ?? "–")}</td>
        <td>${escapeHtml(row.bestCorr == null ? "–" : fmtNum(row.bestCorr))}</td>
        <td>${escapeHtml(row.maxAbs == null ? "–" : fmtNum(row.maxAbs))}</td>
        <td>${escapeHtml(row.corr0 == null ? "–" : fmtNum(row.corr0))}</td>
        <td>${escapeHtml(formatP(row.pCorr))}</td>
        <td>${escapeHtml(row.diff == null ? "–" : fmtNum(row.diff))}</td>
        <td>${row.spurious ? "Risk" : "Low"}</td>
      </tr>
    `)
    .join("");

  return `
    <div class="report-table-wrap">
      <table class="report-table">
        <thead>
          <tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function buildReportHtml() {
  const now = new Date();
  const entityChartSvg = entityChartMount?.querySelector("svg")?.outerHTML || "";
  const warningsHtml = warnWrap?.innerHTML || `<div class="report-empty">No warnings available.</div>`;
  const overallHtml = overallWrap?.innerHTML || `<div class="report-empty">No overall statistics available.</div>`;
  const mapHtml = $("mapFrame")?.innerHTML || `<div class="report-empty">No map available.</div>`;

  const filters = [
    $("summarySearch")?.value ? `Search: ${$("summarySearch").value}` : null,
    $("significantOnly")?.checked ? "Significant only" : null,
    $("hideSpurious")?.checked ? "Hide spurious" : null,
    activeSummaryEntity ? `Selected entity: ${activeSummaryEntity}` : null,
  ].filter(Boolean);

  return `<!doctype html>
  <html>
    <head>
      <meta charset="utf-8" />
      <title>Time Series Analysis Report</title>
      <style>
        body { font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 24px; }
        h1, h2, h3 { margin: 0 0 10px; }
        .report-header { margin-bottom: 20px; padding-bottom: 14px; border-bottom: 2px solid #e5e7eb; }
        .report-meta { color: #4b5563; font-size: 13px; margin-top: 8px; }
        .report-kpis { display: flex; gap: 12px; margin: 16px 0 20px; flex-wrap: wrap; }
        .report-kpi { border: 1px solid #d1d5db; border-radius: 10px; padding: 12px 14px; min-width: 120px; }
        .report-kpi-label { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
        .report-kpi-value { font-size: 22px; font-weight: 700; }
        .report-section { margin: 22px 0; page-break-inside: avoid; }
        .report-note { font-size: 12px; color: #4b5563; margin-top: 6px; }
        .report-table-wrap { overflow: visible; }
        .report-table { width: 100%; border-collapse: collapse; font-size: 11px; }
        .report-table th, .report-table td { border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; vertical-align: top; }
        .report-table th { background: #f3f4f6; }
        .report-svg-wrap svg { width: 100%; height: auto; border: 1px solid #e5e7eb; border-radius: 8px; background: white; }
        .report-empty { border: 1px dashed #d1d5db; padding: 12px; border-radius: 8px; color: #6b7280; }
        .report-chip { display: inline-block; background: #eef2ff; color: #3730a3; padding: 4px 8px; border-radius: 999px; margin: 4px 6px 0 0; font-size: 12px; }
        #mapFrame, .map-frame, iframe { width: 100% !important; }
        @page { size: A4 landscape; margin: 12mm; }
      </style>
    </head>
    <body>
      <div class="report-header">
        <h1>Time Series Analysis Report</h1>
        <div class="report-meta">Generated ${escapeHtml(now.toLocaleString())}</div>
        <div class="report-meta">This report uses the current frontend state, including active filters and the selected entity chart.</div>
        <div>${filters.length ? filters.map((x) => `<span class="report-chip">${escapeHtml(x)}</span>`).join("") : `<span class="report-chip">No active filters</span>`}</div>
      </div>

      <div class="report-kpis">
        <div class="report-kpi"><div class="report-kpi-label">Entities</div><div class="report-kpi-value">${escapeHtml(kpiEntities?.textContent || "0")}</div></div>
        <div class="report-kpi"><div class="report-kpi-label">Pairs</div><div class="report-kpi-value">${escapeHtml(kpiPairs?.textContent || "0")}</div></div>
        <div class="report-kpi"><div class="report-kpi-label">Warnings</div><div class="report-kpi-value">${escapeHtml(kpiWarnings?.textContent || "0")}</div></div>
      </div>

      <section class="report-section">
        <h2>Summary Table</h2>
        <div class="report-note">Includes all currently active summary rows, not just the current pagination page.</div>
        ${buildPdfTableHtmlFromSummary()}
      </section>

      <section class="report-section">
        <h2>Overall Pairwise Across Entities</h2>
        ${overallHtml}
      </section>

      <section class="report-section">
        <h2>Warnings</h2>
        ${warningsHtml}
      </section>

      <section class="report-section">
        <h2>Selected Entity Chart</h2>
        ${entityChartSvg ? `<div class="report-svg-wrap">${entityChartSvg}</div>` : `<div class="report-empty">Load an entity first to include its chart.</div>`}
      </section>

      <section class="report-section">
        <h2>Map Overview</h2>
        ${mapHtml}
      </section>
    </body>
  </html>`;
}

function downloadPdfReport() {
  const reportHtml = buildReportHtml();

  // Δημιουργία blob
  const blob = new Blob([reportHtml], { type: "text/html" });
  const url = URL.createObjectURL(blob);

  // Άνοιγμα στο ίδιο tab (δεν μπλοκάρεται)
  const newWindow = window.open(url, "_blank");

  if (!newWindow) {
    // fallback: redirect στο ίδιο tab
    window.location.href = url;
    return;
  }

  newWindow.onload = () => {
    newWindow.focus();
    newWindow.print();
  };
}