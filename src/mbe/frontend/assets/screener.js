/* Progressive advanced screener. The Python registry generates every field definition. */
(function (global) {
  "use strict";

  const STATIC = Object.freeze({ fields: "/api/v1/screener-fields.json", data: "/api/v1/screener.json" });
  const API = Object.freeze({ fields: "/api/v1/screener/fields", query: "/api/v1/screener/query" });
  const DEFAULT_COLUMNS = ["company", "nse_symbol", "sector", "rank", "multibagger_score", "confidence", "risk_score", "technical_trend", "main_positive_signal", "main_risk"];
  const REQUIRED_COLUMNS = new Set(["company", "nse_symbol"]);
  const OPERATOR_LABELS = Object.freeze({ gt: "is greater than", gte: "is at least", lt: "is less than", lte: "is at most", eq: "equals", ne: "does not equal", between: "is between (inclusive)", is_available: "is available", is_missing: "is missing", any_of: "is any of", none_of: "is none of", contains: "contains", starts_with: "starts with", is_true: "is true", is_false: "is false" });
  const PAGE_SIZES = new Set([10, 25, 50, 100]);
  const MAX_URL_LENGTH = 4000;
  const storageKey = "mbe-screener-api-unavailable";

  function fieldMap(metadata) { return new Map((metadata?.fields || []).map(field => [field.field_id, field])); }
  function makeId() { return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`; }
  function defaultQuery() { return { schema_version: "1.0", logic: "and", conditions: [], sorts: [{ field_id: "rank", direction: "asc" }], columns: DEFAULT_COLUMNS.slice(), page: 1, page_size: 25, build_id: null, count_only: false }; }
  function defaultState() { return { query: defaultQuery(), density: "standard", preset: null }; }

  function encodeShareState(state) {
    const json = JSON.stringify({ v: 1, q: state.query, d: state.density, p: state.preset || null });
    const bytes = new TextEncoder().encode(json);
    let binary = "";
    bytes.forEach(byte => { binary += String.fromCharCode(byte); });
    return global.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function decodeShareState(search) {
    const params = new URLSearchParams(search || "");
    const encoded = params.get("screen");
    if (!encoded || encoded.length > MAX_URL_LENGTH) return { state: defaultState(), warnings: encoded ? ["The shared screen was too long and was reset."] : [] };
    try {
      const padded = encoded.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (encoded.length % 4)) % 4);
      const binary = global.atob(padded);
      const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
      const parsed = JSON.parse(new TextDecoder().decode(bytes));
      if (parsed.v !== 1 || !parsed.q || parsed.q.schema_version !== "1.0") throw new Error("schema");
      return { state: { query: parsed.q, density: parsed.d, preset: parsed.p || null }, warnings: [] };
    } catch (_) { return { state: defaultState(), warnings: ["The shared screen could not be read and was reset."] }; }
  }

  function sanitizeState(input, metadata) {
    const defaults = defaultState();
    const fields = fieldMap(metadata);
    const limits = metadata?.limits || {};
    const warnings = [];
    const source = input && typeof input === "object" ? input : defaults;
    const raw = source.query && typeof source.query === "object" ? source.query : defaults.query;
    const query = defaultQuery();
    query.conditions = [];
    for (const condition of Array.isArray(raw.conditions) ? raw.conditions.slice(0, limits.max_conditions || 12) : []) {
      const field = fields.get(condition.field_id);
      if (!field || !field.filterable || !field.operators.includes(condition.operator)) { warnings.push(`Removed an unavailable condition: ${condition.field_id || "unknown field"}.`); continue; }
      const next = { condition_id: String(condition.condition_id || makeId()).slice(0, 64), field_id: field.field_id, operator: condition.operator, value: condition.value ?? null, value_to: condition.value_to ?? null, values: Array.isArray(condition.values) ? condition.values.slice(0, limits.max_categorical_values || 20).map(String) : null };
      if (["is_missing", "is_available", "is_true", "is_false"].includes(next.operator)) { next.value = null; next.value_to = null; next.values = null; }
      else if (field.data_type === "number") {
        next.value = Number(next.value); next.value_to = next.operator === "between" ? Number(next.value_to) : null; next.values = null;
        if (!Number.isFinite(next.value) || (next.operator === "between" && (!Number.isFinite(next.value_to) || next.value > next.value_to))) { warnings.push(`Removed an invalid ${field.label} condition.`); continue; }
      } else if (["any_of", "none_of"].includes(next.operator)) {
        next.value = null; next.value_to = null;
        if (!next.values?.length) { warnings.push(`Removed an empty ${field.label} condition.`); continue; }
      } else {
        next.value = String(next.value || "").slice(0, limits.max_text_length || 80);
        next.value_to = null; next.values = null;
        if (!next.value) { warnings.push(`Removed an empty ${field.label} condition.`); continue; }
      }
      query.conditions.push(next);
    }
    const rawColumns = Array.isArray(raw.columns) ? raw.columns : DEFAULT_COLUMNS;
    query.columns = [...new Set([...REQUIRED_COLUMNS, ...rawColumns.filter(id => fields.get(id)?.exportable)])].slice(0, limits.max_columns || 16);
    if (query.columns.length !== new Set([...REQUIRED_COLUMNS, ...rawColumns]).size) warnings.push("Unavailable result columns were removed.");
    query.sorts = [];
    for (const sort of Array.isArray(raw.sorts) ? raw.sorts.slice(0, limits.max_sorts || 3) : []) {
      if (fields.get(sort.field_id)?.sortable && !query.sorts.some(item => item.field_id === sort.field_id)) query.sorts.push({ field_id: sort.field_id, direction: sort.direction === "desc" ? "desc" : "asc" });
    }
    if (!query.sorts.length) query.sorts = [{ field_id: "rank", direction: "asc" }];
    query.page = Math.max(1, Number.isInteger(Number(raw.page)) ? Number(raw.page) : 1);
    query.page_size = PAGE_SIZES.has(Number(raw.page_size)) ? Number(raw.page_size) : 25;
    query.build_id = null;
    return { state: { query, density: ["compact", "standard", "comfortable"].includes(source.density) ? source.density : "standard", preset: source.preset || null }, warnings };
  }

  function passes(actual, condition) {
    const op = condition.operator;
    if (op === "is_missing") return actual == null;
    if (op === "is_available") return actual != null;
    if (op === "is_true") return actual === true;
    if (op === "is_false") return actual === false;
    if (actual == null) return false;
    if (op === "gt") return Number(actual) > Number(condition.value);
    if (op === "gte") return Number(actual) >= Number(condition.value);
    if (op === "lt") return Number(actual) < Number(condition.value);
    if (op === "lte") return Number(actual) <= Number(condition.value);
    if (op === "between") return Number(actual) >= Number(condition.value) && Number(actual) <= Number(condition.value_to);
    if (op === "any_of") return condition.values.map(String).includes(String(actual));
    if (op === "none_of") return !condition.values.map(String).includes(String(actual));
    const left = String(actual).toLocaleLowerCase("en-IN"); const right = String(condition.value).toLocaleLowerCase("en-IN");
    if (op === "eq") return left === right;
    if (op === "ne") return left !== right;
    if (op === "contains") return left.includes(right);
    if (op === "starts_with") return left.startsWith(right);
    return false;
  }

  function staticQuery(rows, query) {
    const matching = rows.filter(row => query.conditions.every(condition => passes(row.values[condition.field_id], condition)));
    matching.sort((left, right) => {
      for (const sort of query.sorts) {
        const a = left.values[sort.field_id]; const b = right.values[sort.field_id];
        if (a == null && b == null) continue;
        if (a == null) return 1; if (b == null) return -1;
        const result = typeof a === "string" || typeof b === "string" ? String(a).localeCompare(String(b), "en-IN") : Number(a) - Number(b);
        if (result) return sort.direction === "desc" ? -result : result;
      }
      return String(left.instrument_id).localeCompare(String(right.instrument_id));
    });
    const total = matching.length; const totalPages = total ? Math.ceil(total / query.page_size) : 0; const page = Math.min(query.page, Math.max(1, totalPages)); const start = (page - 1) * query.page_size;
    const selected = matching.slice(start, start + query.page_size).map(row => ({ instrument_id: row.instrument_id, report_url: row.report_url || null, values: Object.fromEntries(query.columns.map(id => [id, row.values[id] ?? null])), matched_conditions: query.conditions.map(condition => ({ ...condition, actual_value: row.values[condition.field_id] ?? null })) }));
    return { rows: selected, all_matching_rows: matching, pagination: { page, page_size: query.page_size, total, total_pages: totalPages }, applied_filters: query.conditions, effective_sorting: query.sorts, requested_columns: query.columns };
  }

  function formulaSafe(value) {
    const text = String(value == null ? "" : value);
    return /^[\s]*[=+\-@]/.test(text) ? `'${text}` : text;
  }
  function csvCell(value) { return `"${formulaSafe(value).replace(/"/g, '""')}"`; }
  function csvFor(rows, columns, fields, metadata) {
    const labels = new Map(fields.map(field => [field.field_id, field.label]));
    const fixed = ["instrument_id", "model_build_id", "data_cutoff", "generated_at"];
    const header = [...fixed, ...columns].map(id => csvCell(labels.get(id) || id));
    const buildId = metadata?.build?.build_id || metadata?.build_id || ""; const cutoff = metadata?.data_cutoff || metadata?.build?.data_cutoff || ""; const generated = metadata?.generated_at || metadata?.build?.built_at || "";
    return [header.join(","), ...rows.map(row => [row.instrument_id, buildId, cutoff, generated, ...columns.map(id => row.values[id])].map(csvCell).join(","))].join("\n");
  }

  function compatible(metadata, dataset) {
    if (!metadata || !dataset) return false;
    const registry = metadata.field_registry_version; const datasetRegistry = dataset.field_registry_version;
    const build = metadata.build?.build_id; const datasetBuild = dataset.build_id || dataset.build?.build_id;
    return registry === datasetRegistry && (!build || !datasetBuild || build === datasetBuild);
  }

  const pure = { defaultState, encodeShareState, decodeShareState, sanitizeState, passes, staticQuery, formulaSafe, csvFor, compatible, reportDestination };
  global["MBEScreener"] = pure;
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (!global.document) return;

  const document = global.document;
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const create = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text != null) node.textContent = String(text); return node; };
  const announce = message => { const node = qs("[data-announcer]"); if (node) node.textContent = message; };
  const root = qs("[data-screener-app]");
  if (!root) return;

  let metadata = null; let fields = new Map(); let dataset = null; let mode = "static"; let state = defaultState(); let currentResult = null; let sequence = 0; let initialWarnings = [];
  const preference = document.body.dataset.dataMode || "auto";
  const table = qs("[data-screener-table]", root); const tbody = qs("[data-screener-rows]", root); const head = qs("[data-screener-head]", root);

  async function fetchJson(url, options = {}) {
    const controller = new AbortController(); const timeout = global.setTimeout(() => controller.abort(), options.timeout || 7000);
    try { const response = await global.fetch(url, { method: options.method || "GET", headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) }, body: options.body, credentials: "same-origin", signal: controller.signal }); const payload = await response.json(); if (!response.ok) { const error = new Error(payload.errors?.[0]?.message || `Request failed (${response.status})`); error["code"] = payload.errors?.[0]?.code || `http_${response.status}`; throw error; } return payload; } finally { global.clearTimeout(timeout); }
  }

  async function loadStaticContracts() {
    const [fieldPayload, dataPayload] = await Promise.all([fetchJson(STATIC.fields), fetchJson(STATIC.data)]);
    if (!compatible(fieldPayload.data, dataPayload.data)) { const error = new Error("The static field registry and dataset describe incompatible builds."); error["code"] = "incompatible_snapshot"; throw error; }
    metadata = fieldPayload.data; dataset = dataPayload.data; mode = "static";
  }

  async function selectMode() {
    const session = global.sessionStorage;
    if (preference === "static" || (preference === "auto" && session?.getItem(storageKey) === "1")) return loadStaticContracts();
    try { const payload = await fetchJson(API.fields); metadata = payload.data; dataset = null; mode = "api"; }
    catch (error) { if (preference === "api") throw error; session?.setItem(storageKey, "1"); await loadStaticContracts(); }
  }

  function updateUrl(push = false) {
    const url = new URL(global.location.href); const encoded = encodeShareState(state); url.search = encoded ? `?screen=${encoded}` : "";
    global.history[push ? "pushState" : "replaceState"]({}, "", url);
  }

  function showWarnings(warnings) {
    const panel = qs("[data-screener-warning]", root); const copy = qs("[data-screener-warning-copy]", root); const unique = [...new Set(warnings.filter(Boolean))];
    panel.hidden = !unique.length; if (unique.length) copy.textContent = unique.join(" ");
  }

  function formatValue(field, value) {
    if (value == null) return "Unavailable";
    if (field?.display_format === "percent") return `${(Number(value) * 100).toFixed(0)}%`;
    if (["score", "signed_decimal"].includes(field?.display_format)) return `${field.display_format === "signed_decimal" && Number(value) > 0 ? "+" : ""}${Number(value).toFixed(1)}`;
    if (["integer", "signed_integer"].includes(field?.display_format)) return `${field.display_format === "signed_integer" && Number(value) > 0 ? "+" : ""}${Math.round(Number(value))}`;
    if (field?.display_format === "trend") return String(value).replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
    if (field?.display_format === "boolean") return value ? "Yes" : "No";
    return String(value);
  }

  function conditionText(condition, actual) {
    const field = fields.get(condition.field_id); const label = field?.label || condition.field_id; const op = OPERATOR_LABELS[condition.operator] || condition.operator;
    let requested = "";
    if (condition.operator === "between") requested = `${formatValue(field, condition.value)} and ${formatValue(field, condition.value_to)}`;
    else if (["any_of", "none_of"].includes(condition.operator)) requested = condition.values.map(value => formatValue(field, value)).join(", ");
    else if (!["is_available", "is_missing", "is_true", "is_false"].includes(condition.operator)) requested = formatValue(field, condition.value);
    return { summary: `${label} ${op}${requested ? ` ${requested}` : ""}`, actual: actual === undefined ? "" : `${formatValue(field, actual)} passed` };
  }

  function renderConditions() {
    const list = qs("[data-condition-list]", root); list.replaceChildren(); qs("[data-condition-count]", root).textContent = `${state.query.conditions.length} active`;
    if (!state.query.conditions.length) { list.append(create("li", "empty-condition", "No conditions yet. The default screen shows the complete scored universe.")); return; }
    state.query.conditions.forEach(condition => { const text = conditionText(condition); const item = create("li", "condition-item"); const copy = create("span", "condition-copy"); copy.append(create("strong", "", text.summary), create("span", "cell-note", fields.get(condition.field_id)?.description || "")); const actions = create("span", "condition-actions"); const edit = create("button", "button button-small button-quiet", "Edit"); edit.type = "button"; edit.addEventListener("click", () => editCondition(condition)); const remove = create("button", "button button-small button-quiet", "Remove"); remove.type = "button"; remove.setAttribute("aria-label", `Remove ${text.summary}`); remove.addEventListener("click", () => { state.query.conditions = state.query.conditions.filter(item => item.condition_id !== condition.condition_id); state.preset = null; state.query.page = 1; renderConditions(); updateUrl(true); execute(); announce(`Removed condition: ${text.summary}`); }); actions.append(edit, remove); item.append(copy, actions); list.append(item); });
  }

  function populateFields() {
    const select = qs("[data-field-select]", root); select.replaceChildren(new Option("Choose a field", ""));
    for (const category of metadata.categories) { const group = document.createElement("optgroup"); group.label = category; metadata.fields.filter(field => field.category === category && field.filterable).forEach(field => { const option = new Option(field.label, field.field_id); option.title = field.description; group.append(option); }); if (group.children.length) select.append(group); }
    const sort = qs("[data-screener-sort]", root); sort.replaceChildren(); metadata.fields.filter(field => field.sortable).forEach(field => sort.append(new Option(`Sort: ${field.label}`, field.field_id)));
  }

  function populatePresets() {
    const list = qs("[data-preset-list]", root); list.replaceChildren();
    metadata.presets.forEach(preset => { const button = create("button", "button button-small button-quiet", preset.label); button.type = "button"; button.title = preset.description; button.addEventListener("click", () => { state.query.conditions = preset.conditions.map((condition, index) => ({ condition_id: `${preset.preset_id}-${index}`, value: null, value_to: null, values: null, ...condition })); state.preset = preset.preset_id; state.query.page = 1; renderConditions(); updateUrl(true); execute(); announce(`${preset.label} preset applied. Its conditions are editable.`); }); list.append(button); });
  }

  function renderValueControl(field, operator, values = {}) {
    const host = qs("[data-value-host]", root); host.replaceChildren();
    if (!field || ["is_available", "is_missing", "is_true", "is_false"].includes(operator)) { host.append(create("span", "cell-note", operator ? "This operator does not need a value." : "Choose an operator.")); return; }
    const label = create("label", "", field.unit ? `Value (${field.unit})` : "Value"); label.htmlFor = "screener-value"; host.append(label);
    if (field.data_type === "number" && operator === "between") { const wrap = create("span", "range-control"); const first = create("input", "input"); first.id = "screener-value"; first.dataset.conditionValue = "from"; first.type = "number"; first.step = "any"; first.value = values.value ?? ""; const second = create("input", "input"); second.dataset.conditionValue = "to"; second.type = "number"; second.step = "any"; second.value = values.value_to ?? ""; wrap.append(first, create("span", "cell-note", "to"), second); host.append(wrap); return; }
    if (field.data_type === "categorical") { const select = create("select", "select"); select.id = "screener-value"; select.dataset.conditionValue = "value"; const multi = ["any_of", "none_of"].includes(operator); select.multiple = multi; if (multi) select.classList.add("multi-select"); (field.allowed_values || []).forEach(value => { const option = new Option(formatValue(field, value), value); option.selected = multi ? (values.values || []).includes(value) : values.value === value; select.append(option); }); host.append(select); return; }
    const input = create("input", "input"); input.id = "screener-value"; input.dataset.conditionValue = "value"; input.type = field.data_type === "number" ? "number" : "text"; input.step = field.data_type === "number" ? "any" : ""; input.maxLength = 80; input.value = values.value ?? ""; host.append(input);
  }

  function resetEditor() { const form = qs("[data-condition-form]", root); form.reset(); qs("[data-condition-id]", root).value = ""; qs("[data-operator-select]", root).replaceChildren(new Option("Choose an operator", "")); qs("[data-operator-select]", root).disabled = true; renderValueControl(null, ""); qs("[data-add-condition]", root).textContent = "Add condition"; qs("[data-condition-error]", root).hidden = true; }
  function editCondition(condition) { const fieldSelect = qs("[data-field-select]", root); fieldSelect.value = condition.field_id; populateOperators(fields.get(condition.field_id), condition.operator); renderValueControl(fields.get(condition.field_id), condition.operator, condition); qs("[data-condition-id]", root).value = condition.condition_id; qs("[data-add-condition]", root).textContent = "Update condition"; fieldSelect.focus(); }
  function populateOperators(field, selected = "") { const select = qs("[data-operator-select]", root); select.replaceChildren(new Option("Choose an operator", "")); if (!field) { select.disabled = true; return; } field.operators.forEach(operator => select.append(new Option(OPERATOR_LABELS[operator] || operator, operator))); select.disabled = false; select.value = selected; }

  function readCondition() {
    const field = fields.get(qs("[data-field-select]", root).value); const operator = qs("[data-operator-select]", root).value; if (!field || !operator) throw new Error("Choose a field and operator.");
    const condition = { condition_id: qs("[data-condition-id]", root).value || makeId(), field_id: field.field_id, operator, value: null, value_to: null, values: null };
    if (["is_available", "is_missing", "is_true", "is_false"].includes(operator)) return condition;
    if (["any_of", "none_of"].includes(operator)) { condition.values = qsa("option:checked", qs("[data-value-host]", root)).map(option => option.value); if (!condition.values.length) throw new Error("Select at least one value."); return condition; }
    const first = qs('[data-condition-value="from"], [data-condition-value="value"]', root); if (!first || first.value === "") throw new Error("Enter a value."); condition.value = field.data_type === "number" ? Number(first.value) : first.value.trim();
    if (operator === "between") { const second = qs('[data-condition-value="to"]', root); condition.value_to = Number(second?.value); if (!Number.isFinite(condition.value_to) || condition.value > condition.value_to) throw new Error("Enter an inclusive range from a lower to a higher value."); }
    return condition;
  }

  function populateColumnControls() {
    const list = qs("[data-screener-column-list]", root); list.replaceChildren(); metadata.fields.filter(field => field.exportable).forEach(field => { const label = create("label", "check-row"); const input = create("input"); input.type = "checkbox"; input.checked = state.query.columns.includes(field.field_id); input.disabled = REQUIRED_COLUMNS.has(field.field_id); input.addEventListener("change", () => { if (input.checked) state.query.columns.push(field.field_id); else state.query.columns = state.query.columns.filter(id => id !== field.field_id); state.query.columns = [...new Set(state.query.columns)]; if (state.query.columns.length > metadata.limits.max_columns) { state.query.columns.pop(); input.checked = false; showWarnings([`At most ${metadata.limits.max_columns} columns may be shown.`]); return; } state.query.page = 1; updateUrl(true); execute(); }); label.append(input, create("span", "", field.label)); list.append(label); });
  }

  function reportDestination(row) { if (row.report_url) return row.report_url; if (/^[A-Za-z0-9-]{1,80}$/.test(String(row.instrument_id || ""))) return `/company/${row.instrument_id}.html`; return "/"; }
  function renderResult(result) {
    currentResult = result; table.dataset.density = state.density; head.replaceChildren(); const headerRow = create("tr");
    state.query.columns.forEach(fieldId => { const field = fields.get(fieldId); const th = create("th", fieldId === "company" ? "company-col" : field?.data_type === "number" ? "number" : ""); th.scope = "col"; th.dataset.field = fieldId; if (field?.sortable) { const button = create("button", "sort-button", field.label); const active = state.query.sorts[0]?.field_id === fieldId; th.setAttribute("aria-sort", active ? (state.query.sorts[0].direction === "asc" ? "ascending" : "descending") : "none"); button.type = "button"; button.append(create("span", "sort-indicator", active ? (state.query.sorts[0].direction === "asc" ? " ↑" : " ↓") : "")); button.addEventListener("click", () => { const current = state.query.sorts[0]; state.query.sorts = [{ field_id: fieldId, direction: current?.field_id === fieldId && current.direction === "asc" ? "desc" : "asc" }]; state.query.page = 1; syncToolbar(); updateUrl(true); execute(); }); th.append(button); } else th.textContent = field?.label || fieldId; headerRow.append(th); }); const actionsHeader = create("th"); actionsHeader.scope = "col"; actionsHeader.append(create("span", "sr-only", "Actions")); headerRow.append(actionsHeader); head.append(headerRow);
    tbody.replaceChildren();
    result.rows.forEach(row => { const tr = create("tr"); tr.dataset.instrumentId = row.instrument_id; state.query.columns.forEach(fieldId => { const field = fields.get(fieldId); const td = create("td", `${fieldId === "company" ? "company-col" : ""} ${field?.data_type === "number" ? "number" : ""}`.trim()); td.dataset.field = fieldId; const value = row.values[fieldId]; if (fieldId === "company") { const link = create("a", "company-link", formatValue(field, value)); link.href = reportDestination(row); td.append(link); } else { td.textContent = formatValue(field, value); if (value == null) td.classList.add("screener-value-missing"); } tr.append(td); }); const actions = create("td"); const detail = create("button", "row-action", "Why matched"); detail.type = "button"; detail.setAttribute("aria-expanded", "false"); detail.addEventListener("click", () => { const existing = qs(`[data-match-for="${row.instrument_id}"]`, tbody); if (existing) { existing.remove(); detail.setAttribute("aria-expanded", "false"); return; } const detailRow = create("tr"); detailRow.dataset.matchFor = row.instrument_id; const cell = create("td", "details-cell"); cell.colSpan = state.query.columns.length + 1; cell.append(create("strong", "", "Why this company matched every active condition")); const list = create("ul", "match-list"); if (!row.matched_conditions.length) list.append(create("li", "cell-note", "No conditions are active; this row belongs to the selected build universe.")); row.matched_conditions.forEach(condition => { const text = conditionText(condition, condition.actual_value); const item = create("li", ""); item.append(create("span", "match-pass", "Passed · "), create("span", "", `${text.summary} · actual ${formatValue(fields.get(condition.field_id), condition.actual_value)}`)); list.append(item); }); cell.append(list, create("p", "cell-note", "A screen match is a research filter, not a performance forecast or recommendation.")); detailRow.append(cell); tr.after(detailRow); detail.setAttribute("aria-expanded", "true"); }); const link = create("a", "button button-small", row.report_url ? "Report" : "Analyze"); link.href = reportDestination(row); actions.append(detail, link); tr.append(actions); tbody.append(tr); });
    const pages = result.pagination.total_pages; qs("[data-screener-count]", root).textContent = `${result.pagination.total} ${result.pagination.total === 1 ? "company" : "companies"}`; qs("[data-screener-page]", root).textContent = pages ? `Page ${result.pagination.page} of ${pages}` : "No pages"; qs("[data-screener-prev]", root).disabled = result.pagination.page <= 1; qs("[data-screener-next]", root).disabled = !pages || result.pagination.page >= pages; table.hidden = !result.rows.length; qs("[data-screener-empty]", root).hidden = Boolean(result.rows.length); qs("[data-screener-status]", root).textContent = mode === "api" ? "from the database-backed API" : `from the bounded ${dataset?.universe?.total || 0}-company static build`; qs("[data-screener-mode]").textContent = mode === "api" ? "Live API" : "Static snapshot"; qs("[data-screener-mode]").className = `badge ${mode === "api" ? "badge-positive" : "badge-warning"}`; announce(`${result.pagination.total} screener results loaded in ${mode === "api" ? "API" : "static"} mode.`);
  }

  async function execute() {
    const run = ++sequence; table.setAttribute("aria-busy", "true"); qs("[data-screener-status]", root).textContent = "screening…";
    try {
      let result;
      if (mode === "api") { const payload = await fetchJson(API.query, { method: "POST", body: JSON.stringify(state.query) }); result = payload.data; result.warnings = payload.warnings || []; }
      else { result = staticQuery(dataset.rows, state.query); result.dataset = dataset; result.build = metadata.build; result.mode = "static"; result.warnings = []; }
      if (run !== sequence) return; state.query.page = result.pagination.page; table.removeAttribute("aria-busy"); renderResult(result); showWarnings([...initialWarnings, ...(result.warnings || [])]); updateUrl(false);
    } catch (error) {
      if (run !== sequence) return;
      if (mode === "api" && preference === "auto") { global.sessionStorage?.setItem(storageKey, "1"); await loadStaticContracts(); fields = fieldMap(metadata); const sanitized = sanitizeState(state, metadata); state = sanitized.state; initialWarnings.push("The database-backed screener was unavailable; the page switched to the compatible weekly snapshot.", ...sanitized.warnings); populateAll(); return execute(); }
      table.removeAttribute("aria-busy"); table.hidden = true; const empty = qs("[data-screener-empty]", root); empty.hidden = false; qs("[data-screener-state-title]", root).textContent = "Screener unavailable"; qs("[data-screener-state-copy]", root).textContent = error.message || "The screen could not be evaluated."; showWarnings([...initialWarnings, error.message]); announce("Screener unavailable.");
    }
  }

  function syncToolbar() { qs("[data-screener-sort]", root).value = state.query.sorts[0].field_id; qs("[data-screener-direction]", root).value = state.query.sorts[0].direction; qs("[data-screener-page-size]", root).value = String(state.query.page_size); qs("[data-screener-density]", root).value = state.density; }
  function populateAll() { populateFields(); populatePresets(); renderConditions(); populateColumnControls(); syncToolbar(); resetEditor(); }

  qs("[data-field-search]", root).addEventListener("input", event => { const term = event.target.value.toLocaleLowerCase("en-IN"); qsa("option", qs("[data-field-select]", root)).forEach(option => { if (!option.value) return; const field = fields.get(option.value); option.hidden = Boolean(term) && !`${field.label} ${field.description} ${field.category}`.toLocaleLowerCase("en-IN").includes(term); }); });
  qs("[data-field-select]", root).addEventListener("change", event => { const field = fields.get(event.target.value); populateOperators(field); renderValueControl(field, ""); });
  qs("[data-operator-select]", root).addEventListener("change", event => renderValueControl(fields.get(qs("[data-field-select]", root).value), event.target.value));
  qs("[data-condition-form]", root).addEventListener("submit", event => { event.preventDefault(); const error = qs("[data-condition-error]", root); try { const condition = readCondition(); const duplicate = state.query.conditions.some(item => item.condition_id !== condition.condition_id && JSON.stringify({ ...item, condition_id: null }) === JSON.stringify({ ...condition, condition_id: null })); if (duplicate) throw new Error("That exact condition is already active."); const index = state.query.conditions.findIndex(item => item.condition_id === condition.condition_id); if (index >= 0) state.query.conditions[index] = condition; else state.query.conditions.push(condition); if (state.query.conditions.length > metadata.limits.max_conditions) { state.query.conditions.pop(); throw new Error(`At most ${metadata.limits.max_conditions} conditions are allowed.`); } state.query.page = 1; state.preset = null; error.hidden = true; renderConditions(); resetEditor(); updateUrl(true); execute(); } catch (reason) { error.textContent = reason.message; error.hidden = false; } });
  qs("[data-clear-conditions]", root).addEventListener("click", () => { state.query.conditions = []; state.preset = null; state.query.page = 1; renderConditions(); updateUrl(true); execute(); });
  qs("[data-screener-sort]", root).addEventListener("change", event => { state.query.sorts = [{ field_id: event.target.value, direction: qs("[data-screener-direction]", root).value }]; state.query.page = 1; updateUrl(true); execute(); });
  qs("[data-screener-direction]", root).addEventListener("change", event => { state.query.sorts[0].direction = event.target.value; state.query.page = 1; updateUrl(true); execute(); });
  qs("[data-screener-page-size]", root).addEventListener("change", event => { state.query.page_size = Number(event.target.value); state.query.page = 1; updateUrl(true); execute(); });
  qs("[data-screener-density]", root).addEventListener("change", event => { state.density = event.target.value; table.dataset.density = state.density; updateUrl(true); announce(`${state.density} table density selected.`); });
  qs("[data-screener-prev]", root).addEventListener("click", () => { state.query.page = Math.max(1, state.query.page - 1); updateUrl(true); execute(); }); qs("[data-screener-next]", root).addEventListener("click", () => { state.query.page += 1; updateUrl(true); execute(); });
  qs("[data-screener-columns]", root).addEventListener("click", event => { const popover = qs("[data-screener-column-popover]", root); popover.hidden = !popover.hidden; event.currentTarget.setAttribute("aria-expanded", String(!popover.hidden)); if (!popover.hidden) qs("input", popover)?.focus(); });
  qs("[data-screener-column-reset]", root).addEventListener("click", () => { state.query.columns = DEFAULT_COLUMNS.slice(); populateColumnControls(); state.query.page = 1; updateUrl(true); execute(); });
  qs("[data-reset-screen]", root).addEventListener("click", () => { state = defaultState(); const sanitized = sanitizeState(state, metadata); state = sanitized.state; populateAll(); updateUrl(true); execute(); });
  qsa("[data-share-screen]").forEach(button => button.addEventListener("click", async () => { updateUrl(false); try { await global.navigator.clipboard.writeText(global.location.href); announce("Shareable screen link copied."); button.textContent = "Link copied"; global.setTimeout(() => { button.textContent = "Copy screen link"; }, 1800); } catch (_) { announce("Could not copy the screen link."); } }));
  qs("[data-screener-export]", root).addEventListener("click", async () => {
    if (!currentResult) return;
    const limit = metadata.limits.max_export_rows; let rows = [];
    try {
      if (mode === "static") rows = staticQuery(dataset.rows, { ...state.query, page: 1, page_size: limit }).all_matching_rows;
      else {
        const pageSize = metadata.limits.max_page_size; const pages = Math.min(Math.ceil(currentResult.pagination.total / pageSize), Math.ceil(limit / pageSize));
        for (let page = 1; page <= pages; page += 1) { const payload = await fetchJson(API.query, { method: "POST", body: JSON.stringify({ ...state.query, page, page_size: pageSize }) }); rows.push(...payload.data.rows); }
      }
      const limited = rows.slice(0, limit); const csv = csvFor(limited, state.query.columns, metadata.fields, currentResult.dataset || dataset || { build: currentResult.build }); const blob = new Blob([csv], { type: "text/csv;charset=utf-8" }); const link = create("a"); link.href = URL.createObjectURL(blob); link.download = `mbe-screen-${currentResult.build?.build_id?.slice(0, 8) || dataset?.build_id?.slice(0, 8) || "snapshot"}.csv`; link.click(); global.setTimeout(() => URL.revokeObjectURL(link.href), 0); announce(`Exported ${limited.length} screener rows${currentResult.pagination.total > limited.length ? "; export was truncated" : ""}.`);
    } catch (_) { announce("The active screen could not be exported."); }
  });
  tbody.addEventListener("keydown", event => { if (!["ArrowDown", "ArrowUp"].includes(event.key)) return; const row = event.target.closest("tr[data-instrument-id]"); if (!row) return; const rows = qsa("tr[data-instrument-id]", tbody); const next = rows[rows.indexOf(row) + (event.key === "ArrowDown" ? 1 : -1)]; const target = next && qs("a,button", next); if (target) { event.preventDefault(); target.focus(); } });
  global.addEventListener("popstate", () => { const decoded = decodeShareState(global.location.search); const sanitized = sanitizeState(decoded.state, metadata); state = sanitized.state; initialWarnings = [...decoded.warnings, ...sanitized.warnings]; populateAll(); execute(); });

  (async function init() {
    try { await selectMode(); fields = fieldMap(metadata); const decoded = decodeShareState(global.location.search); const sanitized = sanitizeState(decoded.state, metadata); state = sanitized.state; initialWarnings = [...decoded.warnings, ...sanitized.warnings]; populateAll(); updateUrl(false); await execute(); }
    catch (error) { table.hidden = true; const empty = qs("[data-screener-empty]", root); empty.hidden = false; qs("[data-screener-state-title]", root).textContent = "Screener unavailable"; qs("[data-screener-state-copy]", root).textContent = error.message || "Compatible screener metadata could not be loaded."; showWarnings([error.message]); }
  })();
})(/** @type {Window & typeof globalThis} */ (globalThis));
