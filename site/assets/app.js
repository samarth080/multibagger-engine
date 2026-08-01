/* Multibagger Engine progressive application layer. No provider-shaped data
 * crosses the normalization boundary below. */
/** @param {Window & typeof globalThis} global */
(function bootstrap(global) {
  "use strict";

  const STATIC = Object.freeze({
    rankings: "/api/v1/rankings.json",
    instruments: "/api/v1/instruments.json",
    // Search universe: every NSE-listed company the platform can identify —
    // deliberately wider than instruments.json (the research/ranking master
    // of 250 modeled companies). See docs/HANDOVER.md "Search, research and
    // ranking universes".
    searchIndex: "/api/v1/search-index.json",
    status: "/api/v1/status.json",
  });
  const API = Object.freeze({
    rankings: "/api/v1/rankings",
    lookup: "/api/v1/instruments/lookup",
    search: "/api/v1/search",
    status: "/api/v1/status",
    quotes: "/api/v1/quotes",
  });
  const DEFAULT_COLUMNS = ["rank", "company", "sector", "industry", "score", "investment", "confidence", "risk", "trend", "quote", "signals", "freshness", "actions"];
  const OPTIONAL_COLUMNS = ["sector", "industry", "investment", "trend", "quote", "signals", "freshness"];
  const STORAGE = Object.freeze({ theme: "mbe-theme", recent: "mbe-recent-searches", columns: "mbe-ranking-columns", density: "mbe-ranking-density", failedApi: "mbe-api-unavailable" });
  const MAX_RECENT = 6;
  const SNAPSHOT_STALE_MS = 10 * 24 * 60 * 60 * 1000;

  /** @returns {Storage | null} */
  function safeStorage(kind) {
    try {
      if (kind === "localStorage") return global.localStorage;
      if (kind === "sessionStorage") return global.sessionStorage;
      return null;
    } catch (_) { return null; }
  }

  function clamp(value, min, max, fallback) {
    if (value == null || value === "") return fallback;
    const number = Number(value);
    return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback;
  }

  function normalizeText(value) {
    return String(value || "").normalize("NFKD").toLocaleLowerCase("en-IN")
      .replace(/[^a-z0-9&\s]/g, " ").replace(/\s+/g, " ").trim();
  }

  function symbolText(value) {
    return String(value || "").trim().toUpperCase().replace(/\.(NS|BO)$/, "");
  }

  function suffixlessName(value) {
    const suffixes = new Set(["limited", "ltd", "private", "pvt", "inc", "corporation", "corp", "company", "co", "plc"]);
    const tokens = normalizeText(value).split(" ").filter(Boolean);
    while (tokens.length && suffixes.has(tokens[tokens.length - 1])) tokens.pop();
    return tokens.join(" ");
  }

  function similarity(left, right) {
    const a = normalizeText(left);
    const b = normalizeText(right);
    if (a === b) return 1;
    if (a.length < 2 || b.length < 2) return 0;
    const pairs = new Map();
    for (let i = 0; i < a.length - 1; i += 1) {
      const pair = a.slice(i, i + 2);
      pairs.set(pair, (pairs.get(pair) || 0) + 1);
    }
    let overlap = 0;
    for (let i = 0; i < b.length - 1; i += 1) {
      const pair = b.slice(i, i + 2);
      const count = pairs.get(pair) || 0;
      if (count) { overlap += 1; pairs.set(pair, count - 1); }
    }
    return (2 * overlap) / (a.length + b.length - 2);
  }

  function reportDestination(item) {
    if (item.report_url) return item.report_url;
    if (/^[A-Za-z0-9-]{1,80}$/.test(String(item.instrument_id || ""))) return `/company/${item.instrument_id}.html`;
    const symbol = symbolText(item.symbol);
    if (!symbol) return "/";
    const suffix = String(item.exchange || "NSE").toUpperCase() === "BSE" ? ".BO" : ".NS";
    return `/api/analyze?ticker=${encodeURIComponent(symbol + suffix)}`;
  }

  const _ALLOWED_EXCHANGES = new Set(["NSE", "BSE"]);
  /** Split an optional allowlisted exchange hint off a raw query — mirrors
   * mbe.search.ranking.parse_exchange_hint. Supports "NSE:TCS"/"BSE:500325"
   * (prefix) and "TCS NSE"/"Reliance BSE" (trailing whole-word suffix).
   * Anything else, including an unrecognized "word:word" shape, passes
   * through unchanged — this is a bounded allowlist match, not a URI parser. */
  function parseExchangeHint(query) {
    const raw = String(query || "").trim();
    const prefixMatch = /^(NSE|BSE):\s*(.+)$/i.exec(raw);
    if (prefixMatch) return { query: prefixMatch[2].trim(), exchange: prefixMatch[1].toUpperCase() };
    const suffixMatch = /^(.+?)\s+(NSE|BSE)$/i.exec(raw);
    if (suffixMatch && _ALLOWED_EXCHANGES.has(suffixMatch[2].toUpperCase())) {
      return { query: suffixMatch[1].trim(), exchange: suffixMatch[2].toUpperCase() };
    }
    return { query: raw, exchange: null };
  }

  function staticSearch(instruments, query, limit = 10, exchange = null) {
    const raw = String(query || "").trim();
    const nameQuery = normalizeText(raw);
    const symbolQuery = symbolText(raw);
    if (nameQuery.length < 2 && !/^\d{6}$/.test(raw) && !/^IN[A-Z0-9]{10}$/i.test(raw)) return [];
    const matches = [];
    for (const item of instruments || []) {
      if (exchange) {
        const listings = Array.isArray(item.listings) ? item.listings : [];
        const onExchange = listings.some(l => l.exchange === exchange) || item.exchange === exchange;
        if (!onExchange) continue;
      }
      let best = null;
      const consider = (score, matchedBy, matchedValue) => {
        if (!best || score > best.score) best = { score, matched_by: matchedBy, matched_value: matchedValue };
      };
      const symbol = symbolText(item.symbol || item.nse_symbol);
      const bse = String(item.bse_code || "");
      const isin = String(item.isin || "").toUpperCase();
      const names = [item.display_name, item.legal_name, item.current_legal_name].filter(Boolean);
      const aliases = Array.isArray(item.aliases) ? item.aliases : [];
      if (symbolQuery && symbolQuery === symbol) consider(100, "exact NSE symbol", symbol);
      if (raw === bse && bse) consider(98, "exact BSE code", bse);
      if (raw.toUpperCase() === isin && isin) consider(97, "exact ISIN", isin);
      for (const name of names) {
        const normalized = normalizeText(name);
        if (nameQuery === normalized || suffixlessName(raw) === suffixlessName(name)) consider(95, "exact company name", name);
        else if (nameQuery.length >= 3 && normalized.startsWith(nameQuery)) consider(82, "company-name prefix", name);
        else if (nameQuery.length >= 5 && Math.abs(nameQuery.length - normalized.length) <= Math.max(nameQuery.length, normalized.length) * .5) {
          const quality = similarity(nameQuery, normalized);
          if (quality >= .78) consider(60 + quality * 20, "fuzzy company name", name);
        }
      }
      for (const alias of aliases) {
        const value = typeof alias === "string" ? alias : alias.value;
        if (value && nameQuery === normalizeText(value)) consider(nameQuery.length <= 3 ? 78 : 90, `exact ${alias.type || "alias"}`, value);
      }
      if (best) {
        const match = /** @type {{score: number, matched_by: string, matched_value: string}} */ (best);
        matches.push({
        instrument_id: String(item.instrument_id),
        display_name: item.display_name || item.legal_name || symbol,
        symbol,
        bse_code: item.bse_code || (Array.isArray(item.listings) ? (item.listings.find(l => l.bse_code)?.bse_code || null) : null),
        isin: item.isin || null,
        exchange: item.exchange || "NSE",
        primary_exchange: item.primary_exchange || item.exchange || "NSE",
        listings: Array.isArray(item.listings) ? item.listings : [],
        industry: item.industry || null,
        sector: item.sector || null,
        market_cap_category: item.market_cap_category || null,
        listing_status: item.listing_status || "unknown",
        is_sme: item.is_sme == null ? null : Boolean(item.is_sme),
        report_url: item.report_url || null,
        result_type: item.result_type || (item.research_available ? "modeled" : "known"),
        research_available: Boolean(item.research_available),
        rank: item.rank == null ? null : Number(item.rank),
        multibagger_score: item.multibagger_score == null ? null : Number(item.multibagger_score),
          score: match.score,
          matched_by: match.matched_by,
          matched_value: match.matched_value,
        });
      }
    }
    return matches.sort((a, b) => b.score - a.score || String(a.display_name).localeCompare(String(b.display_name)) || a.instrument_id.localeCompare(b.instrument_id)).slice(0, limit);
  }

  function parseRankingState(search) {
    const params = new URLSearchParams(search || "");
    const allowedSort = new Set(["rank", "company", "score", "investment", "confidence", "risk"]);
    const sort = allowedSort.has(params.get("sort")) ? params.get("sort") : "rank";
    const dir = params.get("dir") === "desc" ? "desc" : "asc";
    const pageSize = [10, 25, 50, 100].includes(Number(params.get("pageSize"))) ? Number(params.get("pageSize")) : 25;
    return {
      q: String(params.get("q") || "").slice(0, 80),
      sector: String(params.get("sector") || "").slice(0, 80),
      industry: String(params.get("industry") || "").slice(0, 100),
      minScore: clamp(params.get("minScore"), 0, 100, null),
      minConfidence: clamp(params.get("minConfidence"), 0, 100, null),
      maxRisk: clamp(params.get("maxRisk"), 0, 100, null),
      trend: String(params.get("trend") || "").slice(0, 40),
      rankMin: clamp(params.get("rankMin"), 1, 100000, null),
      rankMax: clamp(params.get("rankMax"), 1, 100000, null),
      sort, dir, page: clamp(params.get("page"), 1, 100000, 1), pageSize,
    };
  }

  function stateToSearch(state) {
    const params = new URLSearchParams();
    for (const key of ["q", "sector", "industry", "trend"]) if (state[key]) params.set(key, String(state[key]));
    for (const key of ["minScore", "minConfidence", "maxRisk", "rankMin", "rankMax"]) if (state[key] != null) params.set(key, String(state[key]));
    if (state.sort !== "rank") params.set("sort", state.sort);
    if (state.dir !== "asc") params.set("dir", state.dir);
    if (state.page !== 1) params.set("page", String(state.page));
    if (state.pageSize !== 25) params.set("pageSize", String(state.pageSize));
    return params.toString();
  }

  function rankingRow(raw) {
    const confidence = Number(raw.confidence);
    const risk = Number(raw.risk_score ?? raw.risk);
    const rank = Number(raw.rank);
    const previousRank = raw.previous_rank == null ? null : Number(raw.previous_rank);
    return {
      instrument_id: String(raw.instrument_id || ""), rank,
      previous_rank: Number.isFinite(previousRank) ? previousRank : null,
      rank_change: raw.rank_change == null ? (Number.isFinite(previousRank) ? previousRank - rank : null) : Number(raw.rank_change),
      symbol: symbolText(raw.symbol || raw.legacy_ticker),
      legacy_ticker: raw.legacy_ticker || `${symbolText(raw.symbol)}.${String(raw.exchange || "NSE").toUpperCase() === "BSE" ? "BO" : "NS"}`,
      exchange: raw.exchange || "NSE", name: raw.name || raw.display_name || raw.symbol || "Unknown company",
      sector: raw.sector || null, industry: raw.industry || null,
      multibagger_score: Number(raw.multibagger_score ?? raw.mb), investment_score: Number(raw.investment_score ?? raw.inv),
      confidence: Number.isFinite(confidence) ? confidence : null, risk_score: Number.isFinite(risk) ? risk : null,
      investability: raw.investability || "Unavailable", positive_signal_count: Number(raw.positive_signal_count || 0),
      red_flag_count: Number(raw.red_flag_count || 0), coverage_quality: raw.coverage_quality == null ? null : Number(raw.coverage_quality),
      has_missing_data: Boolean(raw.has_missing_data), technical_trend: raw.technical_trend || raw.trend || "unknown",
      group_rank: raw.group_rank == null ? null : Number(raw.group_rank),
      main_positive_signal: raw.main_positive_signal || null, main_risk: raw.main_risk || null,
      components: Array.isArray(raw.components) ? raw.components : [], report_url: raw.report_url || null,
      recent_news: Array.isArray(raw.recent_news) ? raw.recent_news : [],
      price_at_build: raw.price_at_build == null ? null : Number(raw.price_at_build),
      freshness: raw.freshness || null,
    };
  }

  function normalizeRankingEnvelope(payload, mode) {
    if (!payload || !Array.isArray(payload.data)) throw new Error("corrupt_snapshot");
    const meta = payload.meta && typeof payload.meta === "object" ? payload.meta : {};
    return {
      rows: payload.data.map(rankingRow), mode,
      meta: {
        page: Number(meta.page || 1), page_size: Number(meta.page_size || payload.data.length || 25),
        total: Number(meta.total ?? payload.data.length), total_pages: Number(meta.total_pages ?? (payload.data.length ? 1 : 0)),
        sort: String(meta.sort || "rank"), build: meta.build || null,
      },
      errors: Array.isArray(payload.errors) ? payload.errors : [], warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
      freshness: payload.freshness || null,
    };
  }

  function stableFilterSort(rows, state) {
    const q = normalizeText(state.q);
    const filtered = rows.filter((row) => {
      if (q && !normalizeText(`${row.name} ${row.symbol}`).includes(q)) return false;
      if (state.sector && row.sector !== state.sector) return false;
      if (state.industry && row.industry !== state.industry) return false;
      if (state.minScore != null && row.multibagger_score < state.minScore) return false;
      if (state.minConfidence != null && (row.confidence == null || row.confidence * 100 < state.minConfidence)) return false;
      if (state.maxRisk != null && (row.risk_score == null || row.risk_score > state.maxRisk)) return false;
      if (state.trend && row.technical_trend !== state.trend) return false;
      if (state.rankMin != null && row.rank < state.rankMin) return false;
      if (state.rankMax != null && row.rank > state.rankMax) return false;
      return true;
    }).map((row, index) => ({ row, index }));
    const getters = {
      rank: row => row.rank, company: row => String(row.name).toLocaleLowerCase("en-IN"),
      score: row => row.multibagger_score, investment: row => row.investment_score,
      confidence: row => row.confidence ?? -1, risk: row => row.risk_score ?? 101,
    };
    const getter = getters[state.sort] || getters.rank;
    const direction = state.dir === "desc" ? -1 : 1;
    filtered.sort((a, b) => {
      const av = getter(a.row); const bv = getter(b.row);
      const result = typeof av === "string" ? av.localeCompare(String(bv)) : Number(av) - Number(bv);
      return result ? result * direction : a.index - b.index;
    });
    return filtered.map(item => item.row);
  }

  function median(values) {
    const sorted = values.filter(Number.isFinite).slice().sort((a, b) => a - b);
    if (!sorted.length) return null;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function summaryFor(rows) {
    const sectors = new Map();
    for (const row of rows) if (row.sector) sectors.set(row.sector, (sectors.get(row.sector) || 0) + 1);
    const topSector = [...sectors.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0] || ["Unavailable", 0];
    return {
      total: rows.length, medianScore: median(rows.map(row => row.multibagger_score)),
      medianConfidence: median(rows.map(row => row.confidence == null ? NaN : row.confidence * 100)),
      medianRisk: median(rows.map(row => row.risk_score ?? NaN)),
      highConfidence: rows.filter(row => row.confidence != null && row.confidence >= .9).length,
      topSector: topSector[0], topSectorCount: topSector[1],
    };
  }

  function csvFor(rows) {
    const fields = ["rank", "instrument_id", "name", "symbol", "exchange", "sector", "industry", "multibagger_score", "investment_score", "confidence", "risk_score", "technical_trend", "investability"];
    const quote = value => `"${String(value == null ? "" : value).replace(/"/g, '""')}"`;
    return [fields.join(","), ...rows.map(row => fields.map(field => quote(row[field])).join(","))].join("\n");
  }

  async function fetchJson(url, options = {}) {
    const controller = new AbortController();
    const timeout = global.setTimeout(() => controller.abort(), options.timeout || 4500);
    try {
      const response = await global.fetch(url, { headers: { Accept: "application/json" }, signal: options.signal || controller.signal, credentials: "same-origin" });
      if (!response.ok) throw new Error(`http_${response.status}`);
      return await response.json();
    } finally { global.clearTimeout(timeout); }
  }

  function apiQuery(state) {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
    const strings = { search: state.q, sector: state.sector, industry: state.industry, technical_trend: state.trend };
    for (const [key, value] of Object.entries(strings)) if (value) params.set(key, value);
    const numbers = { min_score: state.minScore, min_confidence: state.minConfidence == null ? null : state.minConfidence / 100, max_risk: state.maxRisk, min_rank: state.rankMin, max_rank: state.rankMax };
    for (const [key, value] of Object.entries(numbers)) if (value != null) params.set(key, String(value));
    const sorts = { rank: "rank", company: "name", score: "score", investment: "investment", confidence: "confidence", risk: "risk" };
    const sort = sorts[state.sort] || "rank";
    params.set("sort", state.dir === "desc" ? `-${sort}` : sort);
    return params.toString();
  }

  function buildCompatible(statusPayload, rankingPayload) {
    const statusBuild = statusPayload?.data?.latest_model_build?.build_id;
    const rankingBuild = rankingPayload?.meta?.build?.build_id;
    return !(statusBuild && rankingBuild && statusBuild !== rankingBuild);
  }

  async function chooseDataMode(preference, state) {
    const session = safeStorage("sessionStorage");
    if (preference === "static") return loadStatic(state);
    if (preference === "auto" && session?.getItem(STORAGE.failedApi) === "1") return loadStatic(state);
    try {
      const [status, rankings] = await Promise.all([fetchJson(API.status), fetchJson(`${API.rankings}?${apiQuery(state)}`)]);
      if (!buildCompatible(status, rankings)) throw new Error("build_version_mismatch");
      const normalized = normalizeRankingEnvelope(rankings, "api");
      normalized.status = status;
      return normalized;
    } catch (error) {
      if (preference === "api") throw error;
      session?.setItem(STORAGE.failedApi, "1");
      return loadStatic(state);
    }
  }

  async function loadStatic(state) {
    const [status, rankings] = await Promise.all([fetchJson(STATIC.status, { timeout: 7000 }), fetchJson(STATIC.rankings, { timeout: 7000 })]);
    if (!buildCompatible(status, rankings)) throw new Error("build_version_mismatch");
    const normalized = normalizeRankingEnvelope(rankings, "static");
    normalized.status = status;
    normalized.allRows = stableFilterSort(normalized.rows, state);
    normalized.meta.total = normalized.allRows.length;
    normalized.meta.total_pages = normalized.allRows.length ? Math.ceil(normalized.allRows.length / state.pageSize) : 0;
    normalized.meta.page = Math.min(state.page, Math.max(1, normalized.meta.total_pages));
    const offset = (normalized.meta.page - 1) * state.pageSize;
    normalized.rows = normalized.allRows.slice(offset, offset + state.pageSize);
    return normalized;
  }

  const pure = { normalizeText, similarity, staticSearch, parseExchangeHint, parseRankingState, stateToSearch, rankingRow, normalizeRankingEnvelope, stableFilterSort, summaryFor, csvFor, buildCompatible, apiQuery, reportDestination };
  global["MBEApp"] = pure;
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (!global.document) return;

  const document = global.document;
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const create = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  };
  const setText = (selector, value, root = document) => { const node = qs(selector, root); if (node) node.textContent = String(value); };
  const announce = message => setText("[data-announcer]", message);

  function focusables(root) {
    return qsa('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])', root).filter(node => !node.hidden && node.getAttribute("aria-hidden") !== "true");
  }

  function trapDialog(dialog, event) {
    if (event.key !== "Tab") return;
    const items = focusables(dialog);
    if (!items.length) return;
    const first = items[0]; const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function initTheme() {
    const storage = safeStorage("localStorage");
    const button = qs("[data-theme-toggle]");
    if (!button) return;
    const effective = () => document.documentElement.dataset.theme || (global.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const update = () => { const next = effective() === "dark" ? "light" : "dark"; button.title = `Use ${next} theme`; button.setAttribute("aria-label", `Use ${next} colour theme`); setText("[data-theme-icon]", effective() === "dark" ? "☼" : "☾", button); };
    button.addEventListener("click", () => { const next = effective() === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = next; storage?.setItem(STORAGE.theme, next); update(); announce(`${next[0].toUpperCase() + next.slice(1)} theme enabled`); });
    update();
  }

  function initMobileMenu() {
    const dialog = qs("#mobile-navigation"); const open = qs("[data-open-menu]"); const close = qs("[data-close-menu]");
    if (!dialog || !open || !close) return;
    let returnFocus = null;
    const closeMenu = () => { if (!dialog.open) return; dialog.close(); document.body.classList.remove("is-locked"); open.setAttribute("aria-expanded", "false"); returnFocus?.focus(); };
    open.addEventListener("click", () => { returnFocus = document.activeElement; dialog.showModal(); document.body.classList.add("is-locked"); open.setAttribute("aria-expanded", "true"); close.focus(); });
    close.addEventListener("click", closeMenu);
    dialog.addEventListener("cancel", event => { event.preventDefault(); closeMenu(); });
    dialog.addEventListener("keydown", event => trapDialog(dialog, event));
    dialog.addEventListener("click", event => { if (event.target === dialog) closeMenu(); });
    qsa("a", dialog).forEach(link => link.addEventListener("click", closeMenu));
  }

  function loadRecent() {
    const storage = safeStorage("localStorage");
    try { const value = JSON.parse(storage?.getItem(STORAGE.recent) || "[]"); return Array.isArray(value) ? value.slice(0, MAX_RECENT) : []; } catch (_) { return []; }
  }

  function saveRecent(item) {
    const storage = safeStorage("localStorage");
    const recent = [item, ...loadRecent().filter(old => old.instrument_id !== item.instrument_id)].slice(0, MAX_RECENT);
    try { storage?.setItem(STORAGE.recent, JSON.stringify(recent)); } catch (_) { /* optional preference */ }
  }

  function initSearch() {
    const dialog = qs("#instrument-search"); const input = qs("[data-search-input]"); const results = qs("[data-search-results]");
    const status = qs("[data-search-status]"); const recentBox = qs("[data-recent-searches]"); const close = qs("[data-close-search]");
    if (!dialog || !input || !results || !status || !recentBox || !close) return;
    let items = []; let selected = -1; let timer = 0; let searchController = null; let returnFocus = null; let staticSearchIndex = null;
    const preference = document.body.dataset.dataMode || "auto";
    const researchBadge = item => {
      if (item.result_type === "modeled" || item.research_available) {
        const bits = [Number.isFinite(item.rank) && `Rank #${item.rank}`, Number.isFinite(item.multibagger_score) && `Score ${Math.round(item.multibagger_score)}`].filter(Boolean);
        return create("span", "badge badge-positive", bits.length ? bits.join(" · ") : "Modeled");
      }
      return create("span", "badge badge-info", "Available");
    };
    const renderItems = (nextItems, query) => {
      items = nextItems; results.replaceChildren();
      const topTied = query.length <= 3 && items.length > 1 && items[0].score === items[1].score;
      const fuzzyFirst = items.length && items[0].score < 82;
      selected = topTied || fuzzyFirst ? -1 : (items.length ? 0 : -1);
      input.removeAttribute("aria-activedescendant");
      items.forEach((item, index) => {
        const li = create("li"); li.setAttribute("role", "option"); li.id = `search-option-${index}`; li.setAttribute("aria-selected", String(index === selected));
        const button = create("button", "search-result"); button.type = "button"; button.tabIndex = -1;
        const main = create("span"); main.append(create("span", "search-name", item.display_name || item.symbol), researchBadge(item));
        if (item.listing_status && !["active", "unknown"].includes(item.listing_status)) {
          main.append(create("span", "badge badge-negative", item.listing_status));
        }
        const bits = [item.symbol && `${item.exchange || "NSE"}: ${item.symbol}`, item.bse_code && `BSE ${item.bse_code}`, item.sector, item.industry, item.market_cap_category, item.is_sme ? "SME" : null].filter(Boolean);
        main.append(create("span", "search-meta", bits.join(" · ")));
        const match = create("span", "search-match", `${item.matched_by || "match"}\n${Math.round(item.score)} / 100`);
        button.append(main, match); button.addEventListener("click", () => openItem(item)); li.append(button); results.append(li);
      });
      if (selected >= 0) input.setAttribute("aria-activedescendant", `search-option-${selected}`);
      if (!items.length) status.textContent = `No matching listed company for “${query}”. Check the name or symbol.`;
      else if (topTied) status.textContent = `${items.length} matches. This short query is ambiguous; choose a result explicitly.`;
      else if (fuzzyFirst) status.textContent = `${items.length} approximate match${items.length === 1 ? "" : "es"}. Choose a result explicitly.`;
      else status.textContent = `${items.length} match${items.length === 1 ? "" : "es"}. Use arrow keys and Enter to open.`;
    };
    const openItem = item => { saveRecent({ instrument_id: item.instrument_id, display_name: item.display_name, symbol: item.symbol, exchange: item.exchange, report_url: item.report_url || null }); global.location.assign(reportDestination(item)); };
    const renderRecent = () => {
      const recent = loadRecent(); recentBox.replaceChildren(); if (!recent.length) return;
      const header = create("div", "recent-header"); header.append(create("span", "", "Recent searches"));
      const clear = create("button", "button button-small button-quiet", "Clear"); clear.type = "button"; clear.addEventListener("click", () => { safeStorage("localStorage")?.removeItem(STORAGE.recent); renderRecent(); }); header.append(clear); recentBox.append(header);
      const list = create("ul", "search-results");
      recent.forEach(item => { const li = create("li"); const button = create("button", "search-result"); button.type = "button"; button.append(create("span", "search-name", item.display_name), create("span", "search-match", `${item.exchange}: ${item.symbol}`)); button.addEventListener("click", () => openItem(item)); li.append(button); list.append(li); }); recentBox.append(list);
    };
    const staticLookup = async (query, exchange) => { if (!staticSearchIndex) { const payload = await fetchJson(STATIC.searchIndex, { timeout: 7000 }); if (!Array.isArray(payload.data)) throw new Error("snapshot_unavailable"); staticSearchIndex = payload.data; } return staticSearch(staticSearchIndex, query, 10, exchange); };
    const lookup = async (query, exchange) => {
      if (preference !== "static" && safeStorage("sessionStorage")?.getItem(STORAGE.failedApi) !== "1") {
        try {
          const exchangeParam = exchange ? `&exchange=${encodeURIComponent(exchange)}` : "";
          const payload = await fetchJson(`${API.search}?q=${encodeURIComponent(query)}&limit=10${exchangeParam}`, { signal: searchController?.signal });
          if (!Array.isArray(payload.data)) throw new Error("invalid_search");
          return payload.data.map(item => ({ ...item, matched_by: String(item.matched_by || "match").replaceAll("_", " "), report_url: item.report_url || null }));
        } catch (error) { if (preference === "api") throw error; safeStorage("sessionStorage")?.setItem(STORAGE.failedApi, "1"); }
      }
      return staticLookup(query, exchange);
    };
    const searchHelpText = "Search any listed Indian company on NSE or BSE. Full research, score and rank are available for the modeled research universe.";
    const run = async () => {
      const raw = input.value.trim(); recentBox.hidden = Boolean(raw); results.replaceChildren();
      const { query, exchange } = parseExchangeHint(raw);
      if (query.length < 2 && !/^\d{6}$/.test(query)) { items = []; selected = -1; status.textContent = raw ? "Type at least two characters to search safely." : searchHelpText; return; }
      status.textContent = "Searching listed companies…"; results.replaceChildren();
      for (let index = 0; index < 3; index += 1) { const item = create("li", "search-result"); item.setAttribute("aria-hidden", "true"); const bar = create("span", "skeleton"); bar.style.height = "2rem"; item.append(bar); results.append(item); }
      searchController?.abort(); searchController = new AbortController();
      try { renderItems(await lookup(query, exchange), query); } catch (_) { status.textContent = "Search is unavailable in the selected data mode. Try again later."; }
    };
    const openDialog = () => { returnFocus = document.activeElement; dialog.showModal(); document.body.classList.add("is-locked"); input.value = ""; results.replaceChildren(); recentBox.hidden = false; renderRecent(); status.textContent = searchHelpText; input.focus(); };
    const closeDialog = () => { if (!dialog.open) return; searchController?.abort(); dialog.close(); document.body.classList.remove("is-locked"); returnFocus?.focus(); };
    qsa("[data-open-search]").forEach(button => button.addEventListener("click", openDialog)); close.addEventListener("click", closeDialog);
    dialog.addEventListener("cancel", event => { event.preventDefault(); closeDialog(); });
    dialog.addEventListener("click", event => { if (event.target === dialog) closeDialog(); });
    dialog.addEventListener("keydown", event => trapDialog(dialog, event));
    input.addEventListener("input", () => { global.clearTimeout(timer); timer = global.setTimeout(run, 180); });
    input.addEventListener("keydown", event => {
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && items.length) { event.preventDefault(); selected = event.key === "ArrowDown" ? (selected + 1 + items.length) % items.length : (selected - 1 + items.length) % items.length; qsa('[role="option"]', results).forEach((node, index) => node.setAttribute("aria-selected", String(index === selected))); input.setAttribute("aria-activedescendant", `search-option-${selected}`); qs(`#search-option-${selected}`, results)?.scrollIntoView({ block: "nearest" }); }
      if (event.key === "Enter" && selected >= 0 && items[selected]) { event.preventDefault(); openItem(items[selected]); }
    });
    document.addEventListener("keydown", event => { if ((event.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "")) || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k")) { event.preventDefault(); if (!dialog.open) openDialog(); } });
  }

  function cell(tag, column, className) { const node = create(tag, className); node.dataset.column = column; return node; }
  function formatNumber(value, digits = 1) { return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "Unavailable"; }
  function confidenceLabel(value) { return value == null ? "Unavailable" : `${Math.round(value * 100)}%`; }
  function riskClass(value) { if (value == null) return "risk-medium"; if (value <= 25) return "risk-low"; if (value <= 60) return "risk-medium"; return "risk-high"; }
  function trendClass(value) { const trend = String(value || "unknown"); if (trend.includes("up")) return "trend-up"; if (trend.includes("down")) return "trend-down"; if (trend === "sideways") return "trend-sideways"; return "trend-unknown"; }

  function initRankings() {
    const root = qs("[data-rankings-app]"); if (!root) return;
    const tbody = qs("[data-ranking-rows]", root); const table = qs("[data-rankings-table]", root); const form = qs("[data-filter-form]", root);
    const tableState = qs("[data-table-state]", root); const preference = document.body.dataset.dataMode || "auto";
    let state = parseRankingState(global.location.search); let response = null; let requestSequence = 0; let quoteUnavailable = false;

    const syncForm = () => {
      for (const name of ["q", "sector", "industry", "trend", "minScore", "minConfidence", "maxRisk"]) { const input = form.elements.namedItem(name); if (input) input.value = state[name] == null ? "" : String(state[name]); }
      const rankMin = qs("[data-rank-min]", root); const rankMax = qs("[data-rank-max]", root); const size = qs("[data-page-size]", root);
      if (rankMin) rankMin.value = state.rankMin == null ? "" : String(state.rankMin); if (rankMax) rankMax.value = state.rankMax == null ? "" : String(state.rankMax); if (size) size.value = String(state.pageSize);
    };
    const updateUrl = () => { const query = stateToSearch(state); global.history.replaceState(null, "", `${global.location.pathname}${query ? `?${query}` : ""}${global.location.hash}`); };
    const showLoading = () => {
      table.setAttribute("aria-busy", "true"); table.hidden = false; tableState.hidden = true; setText("[data-result-count]", "Loading rankings…", root); tbody.replaceChildren();
      for (let rowIndex = 0; rowIndex < 5; rowIndex += 1) { const tr = create("tr"); tr.setAttribute("aria-hidden", "true"); for (let columnIndex = 0; columnIndex < DEFAULT_COLUMNS.length; columnIndex += 1) { const td = create("td"); const bar = create("span", "skeleton"); bar.style.height = "1rem"; bar.style.width = `${45 + ((rowIndex + columnIndex) % 4) * 12}%`; td.append(bar); tr.append(td); } tbody.append(tr); }
    };
    const showError = (code) => { table.hidden = true; tableState.hidden = false; const map = { build_version_mismatch: ["Incompatible build versions", "The status and ranking snapshots describe different builds. The page will not merge them."], corrupt_snapshot: ["Snapshot is corrupt", "The versioned ranking snapshot does not match the expected contract."], http_503: ["Ranking service unavailable", "The database-backed ranking service is not configured for this deployment."], default: ["Rankings unavailable", "Neither the selected API mode nor its compatible snapshot could be loaded."] }; const copy = map[code] || map.default; setText("[data-state-title]", copy[0], tableState); setText("[data-state-copy]", copy[1], tableState); announce(copy[0]); };
    const updateStatus = data => {
      const api = data.mode === "api"; setText("[data-mode-badge]", api ? "Live API" : "Static snapshot"); setText("[data-mode-copy]", api ? "from the database-backed API" : "from the versioned static snapshot");
      const badge = qs("[data-mode-badge]"); if (badge) badge.className = `badge ${api ? "badge-positive" : "badge-warning"}`;
      const trigger = qs("[data-status-trigger]"); const dot = qs(".status-dot", trigger); if (dot) dot.dataset.state = api ? "live" : "static"; setText(".status-label", api ? "Live API" : "Snapshot", trigger); trigger?.setAttribute("aria-label", `Data status: ${api ? "live API" : "static snapshot"}`);
      const built = data.meta.build?.built_at || data.status?.data?.latest_model_build?.built_at || root.dataset.builtAt; const age = Date.now() - Date.parse(built || ""); const stale = Number.isFinite(age) && age > SNAPSHOT_STALE_MS;
      const notice = qs("[data-stale-notice]"); if (notice) notice.hidden = !stale; if (stale) setText("[data-stale-message]", `The active build is ${Math.floor(age / 86400000)} days old.`, notice);
    };
    const updateSummary = rows => { const summary = summaryFor(rows); setText("[data-summary-total]", summary.total); setText("[data-summary-score]", summary.medianScore == null ? "—" : summary.medianScore.toFixed(1)); setText("[data-summary-confidence]", summary.medianConfidence == null ? "—" : `${Math.round(summary.medianConfidence)}%`); setText("[data-summary-risk]", summary.medianRisk == null ? "—" : summary.medianRisk.toFixed(0)); setText("[data-summary-high-confidence]", summary.highConfidence); setText("[data-summary-sector]", summary.topSector); setText("[data-summary-sector-note]", `${summary.topSectorCount} names`); };
    const renderChips = () => {
      const box = qs("[data-filter-chips]", root); box.replaceChildren(); const labels = { q: "Company", sector: "Sector", industry: "Industry", minScore: "Score ≥", minConfidence: "Confidence ≥", maxRisk: "Risk ≤", trend: "Trend", rankMin: "Rank from", rankMax: "Rank to" };
      for (const key of Object.keys(labels)) if (state[key] != null && state[key] !== "") { const chip = create("span", "filter-chip", `${labels[key]} ${state[key]}${key === "minConfidence" ? "%" : ""}`); const remove = create("button", "", "×"); remove.type = "button"; remove.setAttribute("aria-label", `Remove ${labels[key]} filter`); remove.addEventListener("click", () => { state[key] = key.startsWith("min") || key.startsWith("max") || key.startsWith("rank") ? null : ""; state.page = 1; syncForm(); updateUrl(); load(); }); chip.append(remove); box.append(chip); }
    };
    const buildDetails = row => {
      const tr = create("tr", "details-row"); tr.dataset.detailsFor = row.instrument_id; const td = create("td"); td.colSpan = DEFAULT_COLUMNS.length;
      const breakdown = create("div", "breakdown"); const components = row.components.length ? row.components : [{ name: "Multibagger", score: row.multibagger_score }, { name: "Investment", score: row.investment_score }, { name: "Confidence coverage", score: row.confidence == null ? null : row.confidence * 100 }, { name: "Risk flags", score: row.risk_score }];
      components.forEach(component => { const item = create("div", "breakdown-item"); item.append(create("span", "breakdown-label", String(component.name || "Component").replaceAll("_", " ")), create("strong", "", formatNumber(component.score))); const track = create("span", "score-track"); const fill = create("span", "score-fill"); fill.style.width = `${clamp(component.score, 0, 100, 0)}%`; track.append(fill); item.append(track); breakdown.append(item); }); td.append(breakdown);
      const reasons = create("div", "reason-grid"); const positive = create("div", "reason-card"); positive.append(create("strong", "", "Why it ranks"), create("p", "", row.main_positive_signal || `${row.positive_signal_count} high-scoring evidence signals; open the report for the underlying evidence.`)); const risk = create("div", "reason-card"); risk.append(create("strong", "", "Main risk context"), create("p", "", row.main_risk || `${row.red_flag_count} model flags. Risk is contextual, not a probability of loss.`)); reasons.append(positive, risk); td.append(reasons);
      if (row.recent_news.length) { const news = create("div", "reason-card"); news.style.marginTop = ".75rem"; news.append(create("strong", "", "Entity-matched company headlines")); const list = create("ul"); row.recent_news.slice(0, 3).forEach(item => { const li = create("li"); const link = create("a", "", item.title || "Untitled headline"); try { const url = new URL(item.link); if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsafe_url"); link.href = url.href; link.rel = "noopener noreferrer"; link.target = "_blank"; } catch (_) { link.removeAttribute("href"); } li.append(link, create("span", "cell-note", `${item.match_confidence || "reviewed"} match${item.relevance_score == null ? "" : ` · ${Math.round(item.relevance_score)}/100`}`)); list.append(li); }); news.append(list); td.append(news); }
      tr.append(td); return tr;
    };
    const renderRows = rows => {
      tbody.replaceChildren();
      for (const row of rows) {
        const tr = create("tr"); tr.dataset.instrumentId = row.instrument_id;
        const rank = cell("td", "rank"); rank.append(create("strong", "", row.rank)); const movement = row.rank_change > 0 ? `↑ ${row.rank_change}` : row.rank_change < 0 ? `↓ ${Math.abs(row.rank_change)}` : "—"; rank.append(create("span", "cell-note", movement)); tr.append(rank);
        const company = cell("td", "company", "company-col"); const link = create("a", "company-link", row.name); link.href = reportDestination(row); company.append(link, create("span", "company-meta", `${row.symbol} · ${row.exchange}`)); tr.append(company);
        tr.append(Object.assign(cell("td", "sector"), { textContent: row.sector || "Unavailable" })); tr.append(Object.assign(cell("td", "industry"), { textContent: row.industry || "Unavailable" }));
        const score = cell("td", "score", "number"); const scoreWrap = create("span", "score-bar"); scoreWrap.append(create("span", "score", formatNumber(row.multibagger_score))); const track = create("span", "score-track"); const fill = create("span", "score-fill"); fill.style.width = `${clamp(row.multibagger_score, 0, 100, 0)}%`; track.append(fill); scoreWrap.append(track); score.append(scoreWrap); tr.append(score);
        tr.append(Object.assign(cell("td", "investment", "number"), { textContent: formatNumber(row.investment_score) })); const conf = cell("td", "confidence", "number"); conf.append(create("span", "confidence-mark", confidenceLabel(row.confidence))); tr.append(conf);
        const risk = cell("td", "risk", "number"); risk.append(create("span", `risk-mark ${riskClass(row.risk_score)}`, formatNumber(row.risk_score, 0))); tr.append(risk);
        const trend = cell("td", "trend"); trend.append(create("span", `trend ${trendClass(row.technical_trend)}`, String(row.technical_trend).replaceAll("_", " "))); tr.append(trend);
        const quote = cell("td", "quote", "number"); const quoteSpan = create("span", "cell-note", "Loading…"); quoteSpan.dataset.quote = row.instrument_id; quoteSpan.dataset.symbol = row.legacy_ticker; quoteSpan.dataset.base = String(row.price_at_build || ""); quote.append(quoteSpan); tr.append(quote);
        const signals = cell("td", "signals"); signals.append(create("span", "", `${row.positive_signal_count} positive`), create("span", "cell-note", `${row.red_flag_count} flags`)); tr.append(signals);
        const freshness = cell("td", "freshness"); freshness.append(create("span", `badge ${row.has_missing_data ? "badge-warning" : "badge-positive"}`, row.has_missing_data ? "Partial inputs" : "Complete inputs")); tr.append(freshness);
        const actions = cell("td", "actions"); const group = create("span", "row-actions"); const report = create("a", "button button-small", "Research"); report.href = reportDestination(row); const details = create("button", "row-action", "⋯"); details.type = "button"; details.setAttribute("aria-label", `Show score details for ${row.name}`); details.setAttribute("aria-expanded", "false"); details.addEventListener("click", () => { const existing = qs(`[data-details-for="${row.instrument_id}"]`, tbody); if (existing) { existing.remove(); details.setAttribute("aria-expanded", "false"); } else { tr.after(buildDetails(row)); details.setAttribute("aria-expanded", "true"); } }); const copy = create("button", "row-action", "⧉"); copy.type = "button"; copy.setAttribute("aria-label", `Copy direct link for ${row.name}`); copy.addEventListener("click", async () => { try { await global.navigator.clipboard.writeText(new URL(report.href, global.location.href).href); announce(`Copied report link for ${row.name}`); } catch (_) { announce("Could not copy the link"); } }); group.append(report, details, copy); actions.append(group); tr.append(actions); tbody.append(tr);
      }
      applyColumns(); loadQuotes(rows);
    };
    const renderPagination = meta => { const pages = Math.max(0, meta.total_pages); setText("[data-page-summary]", pages ? `Page ${meta.page} of ${pages}` : "No pages", root); const previous = qs("[data-page-prev]", root); const next = qs("[data-page-next]", root); previous.disabled = meta.page <= 1; next.disabled = !pages || meta.page >= pages; };
    const renderSort = () => { qsa("th[aria-sort]", table).forEach(th => { const active = qs(`[data-sort="${state.sort}"]`, th); const isActive = Boolean(active); th.setAttribute("aria-sort", isActive ? (state.dir === "asc" ? "ascending" : "descending") : "none"); setText(".sort-indicator", isActive ? (state.dir === "asc" ? "↑" : "↓") : "", th); }); };
    const loadQuotes = async rows => {
      if (quoteUnavailable || !rows.length) return; const spans = qsa("[data-quote]", tbody); const ids = [...new Set(rows.map(row => row.instrument_id).filter(Boolean))].slice(0, 30);
      try {
        if (response.mode === "api") {
          const payload = await fetchJson(`${API.quotes}?instrument_ids=${encodeURIComponent(ids.join(","))}`, { timeout: 9000 }); const byId = new Map((payload.data?.quotes || []).map(quote => [quote.instrument_id, quote])); spans.forEach(span => renderQuote(span, byId.get(span.dataset.quote), "api"));
        } else {
          const symbols = [...new Set(rows.map(row => row.legacy_ticker).filter(Boolean))].slice(0, 30); const payload = await fetchJson(`/api/quotes?symbols=${encodeURIComponent(symbols.join(","))}`, { timeout: 9000 }); spans.forEach(span => renderQuote(span, payload.quotes?.[span.dataset.symbol], "legacy"));
        }
      } catch (_) { quoteUnavailable = true; spans.forEach(span => { span.textContent = "Unavailable"; span.title = "Quote service is unavailable; ranking data remains valid."; }); }
    };
    const renderQuote = (span, quote, mode) => {
      if (!quote) { span.textContent = "Unavailable"; span.title = "No usable quote for this instrument."; return; }
      const price = mode === "api" ? quote.last_price : quote.price; const change = mode === "api" ? quote.percentage_change : quote.day_change_pct; const stale = mode === "api" ? quote.freshness_state === "stale" : quote.is_stale; const delay = mode === "api" ? quote.reported_delay_minutes : quote.delay_minutes; const timestamp = mode === "api" ? quote.provider_timestamp : quote.as_of;
      span.className = stale || !Number.isFinite(change) ? "cell-note" : change >= 0 ? "quote-gain" : "quote-loss"; span.replaceChildren(create("strong", "", `₹${formatNumber(price, 2)}${Number.isFinite(change) ? ` ${change >= 0 ? "+" : ""}${formatNumber(change, 2)}%` : ""}`)); const notes = [stale ? "Stale" : null, quote.market_status, Number.isFinite(delay) && delay > 0 ? `${delay}m delay` : null, timestamp ? new Date(timestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " IST" : null].filter(Boolean); if (notes.length) span.append(create("span", "cell-note", notes.join(" · "))); span.title = quote.staleness_reason || quote.stale_reason || "";
    };
    const load = async () => {
      const sequence = ++requestSequence; showLoading(); renderChips(); renderSort();
      try {
        const data = await chooseDataMode(preference, state); if (sequence !== requestSequence) return; response = data; state.page = data.meta.page; updateUrl(); table.hidden = false; tableState.hidden = true; table.removeAttribute("aria-busy"); renderRows(data.rows); renderPagination(data.meta); updateStatus(data); updateSummary(data.allRows || data.rows); setText("[data-result-count]", `${data.meta.total} ${data.meta.total === 1 ? "company" : "companies"}`, root); announce(`${data.meta.total} ranking results loaded in ${data.mode === "api" ? "live API" : "static snapshot"} mode.`); if (!data.meta.total) { table.hidden = true; tableState.hidden = false; setText("[data-state-title]", "No rankings match these filters", tableState); setText("[data-state-copy]", "Remove one or more filters, or clear all to restore the published shortlist.", tableState); }
      } catch (error) { if (sequence !== requestSequence) return; table.removeAttribute("aria-busy"); showError(error.message); }
    };
    const readForm = () => { const formData = new FormData(form); state.q = String(formData.get("q") || "").trim(); state.sector = String(formData.get("sector") || ""); state.industry = String(formData.get("industry") || ""); state.trend = String(formData.get("trend") || ""); state.minScore = clamp(formData.get("minScore"), 0, 100, null); state.minConfidence = clamp(formData.get("minConfidence"), 0, 100, null); state.maxRisk = clamp(formData.get("maxRisk"), 0, 100, null); state.rankMin = clamp(qs("[data-rank-min]", root)?.value, 1, 100000, null); state.rankMax = clamp(qs("[data-rank-max]", root)?.value, 1, 100000, null); if (state.rankMin != null && state.rankMax != null && state.rankMin > state.rankMax) { const swap = state.rankMin; state.rankMin = state.rankMax; state.rankMax = swap; announce("Rank range was reordered from low to high."); } state.page = 1; };
    form.addEventListener("submit", event => { event.preventDefault(); readForm(); updateUrl(); syncForm(); load(); });
    tbody.addEventListener("keydown", event => { if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return; const row = event.target.closest('tr[data-instrument-id]'); if (!row) return; const rows = qsa('tr[data-instrument-id]', tbody); const index = rows.indexOf(row); const next = rows[index + (event.key === 'ArrowDown' ? 1 : -1)]; const target = next && qs('a,button', next); if (target) { event.preventDefault(); target.focus(); } });
    qs("[data-reset]", root)?.addEventListener("click", () => { state = parseRankingState(""); syncForm(); updateUrl(); load(); });
    qs("[data-rank-min]", root)?.addEventListener("change", () => { readForm(); updateUrl(); load(); }); qs("[data-rank-max]", root)?.addEventListener("change", () => { readForm(); updateUrl(); load(); });
    qs("[data-page-size]", root)?.addEventListener("change", event => { state.pageSize = Number(event.target.value); state.page = 1; updateUrl(); load(); });
    qs("[data-page-prev]", root)?.addEventListener("click", () => { state.page = Math.max(1, state.page - 1); updateUrl(); load(); }); qs("[data-page-next]", root)?.addEventListener("click", () => { state.page += 1; updateUrl(); load(); });
    qsa("[data-sort]", table).forEach(button => button.addEventListener("click", () => { const next = button.dataset.sort; if (state.sort === next) state.dir = state.dir === "asc" ? "desc" : "asc"; else { state.sort = next; state.dir = next === "rank" || next === "company" ? "asc" : "desc"; } state.page = 1; updateUrl(); load(); announce(`Sorted by ${next}, ${state.dir === "asc" ? "ascending" : "descending"}.`); }));
    qs("[data-retry]", root)?.addEventListener("click", () => { safeStorage("sessionStorage")?.removeItem(STORAGE.failedApi); load(); });
    const density = qs("[data-density]", root); const storage = safeStorage("localStorage"); const savedDensity = storage?.getItem(STORAGE.density); if (["compact", "standard", "comfortable"].includes(savedDensity)) density.value = savedDensity; table.dataset.density = density.value; density.addEventListener("change", () => { table.dataset.density = density.value; storage?.setItem(STORAGE.density, density.value); announce(`${density.value} table density selected.`); });
    const visibleColumns = () => { try { const saved = JSON.parse(storage?.getItem(STORAGE.columns) || "null"); return Array.isArray(saved) ? new Set([...saved, "rank", "company", "actions"]) : new Set(DEFAULT_COLUMNS); } catch (_) { return new Set(DEFAULT_COLUMNS); } };
    let columns = visibleColumns();
    function applyColumns() { qsa("[data-column]", table).forEach(node => { node.hidden = !columns.has(node.dataset.column); }); }
    const columnList = qs("[data-column-list]", root); for (const column of OPTIONAL_COLUMNS) { const label = create("label", "check-row"); const input = create("input"); input.type = "checkbox"; input.checked = columns.has(column); input.addEventListener("change", () => { if (input.checked) columns.add(column); else columns.delete(column); storage?.setItem(STORAGE.columns, JSON.stringify([...columns])); applyColumns(); }); label.append(input, create("span", "", column[0].toUpperCase() + column.slice(1))); columnList.append(label); }
    const popover = qs("[data-column-popover]", root); const columnTrigger = qs("[data-column-trigger]", root); columnTrigger.addEventListener("click", () => { popover.hidden = !popover.hidden; columnTrigger.setAttribute("aria-expanded", String(!popover.hidden)); if (!popover.hidden) qs("input", popover)?.focus(); }); qs("[data-column-reset]", root)?.addEventListener("click", () => { columns = new Set(DEFAULT_COLUMNS); storage?.removeItem(STORAGE.columns); qsa('input[type="checkbox"]', columnList).forEach(input => { input.checked = true; }); applyColumns(); });
    qs("[data-export]")?.addEventListener("click", () => { if (!response) return; const rows = response.allRows || response.rows; const blob = new Blob([csvFor(rows)], { type: "text/csv;charset=utf-8" }); const link = create("a"); link.href = URL.createObjectURL(blob); link.download = `multibagger-rankings-${response.meta.build?.build_id?.slice(0, 8) || "snapshot"}.csv`; link.click(); global.setTimeout(() => URL.revokeObjectURL(link.href), 0); announce(`Exported ${rows.length} filtered rankings.`); });
    syncForm(); applyColumns(); load();
  }

  function init() { initTheme(); initMobileMenu(); initSearch(); initRankings(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true }); else init();
})(/** @type {Window & typeof globalThis} */ (globalThis));
