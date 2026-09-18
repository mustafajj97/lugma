const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const bd = n => `BD ${Number(n).toFixed(3)}`;
const PAGE = 48;

const SOURCES = {
  talabat:   { label: "Talabat",   color: "var(--talabat)", link: "Open on Talabat" },
  instagram: { label: "Instagram", color: "var(--insta)",   link: "View post" },
  news:      { label: "News",      color: "var(--news)",    link: "Read story" },
  manual:    { label: "Added by me", color: "var(--manual)", link: "Open link" },
};
const CHANNEL = { delivery: "Delivery", "in-person": "Dine-in / pickup", both: "Dine-in & delivery" };

// Today's date in Bahrain, from THIS device's clock — so offers expire on time even if the
// data hasn't been refreshed (e.g. you open the app 4 days after the last update).
const bhToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Bahrain" });
const fmtDay = iso => new Date(iso + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

const state = {
  local: false,          // true when running on the PC server (Refresh + Settings available)
  offers: [], cuisines: [], sources: {}, today: bhToday(), generatedAt: null,
  q: "", cuisine: new Set(), channel: "all", src: new Set(Object.keys(SOURCES)),
  minPct: 0, area: "", sort: "pct", newOnly: false, shown: PAGE, deals: new Set(),
};

// persist filters between visits (per-browser convenience only)
function remember() {
  try {
    localStorage.setItem("lugma.f", JSON.stringify({ cuisine: [...state.cuisine], deals: [...state.deals], channel: state.channel, src: [...state.src],
      minPct: state.minPct, area: state.area, sort: state.sort }));
  } catch {}
}
function recall() {
  try {
    const f = JSON.parse(localStorage.getItem("lugma.f") || "null");
    if (!f) return;
    state.cuisine = new Set(f.cuisine || []); state.deals = new Set(f.deals || []); state.channel = f.channel || "all";
    state.src = new Set(f.src?.length ? f.src : Object.keys(SOURCES));
    Object.assign(state, { minPct: f.minPct || 0, area: f.area || "", sort: f.sort || "pct" });
  } catch {}
}

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

// Offers you add yourself are saved on this device only
function myOffers() {
  try { return JSON.parse(localStorage.getItem("lugma.mine") || "[]"); } catch { return []; }
}
function saveMine(list) {
  try { localStorage.setItem("lugma.mine", JSON.stringify(list)); } catch { alert("Couldn't save on this device."); }
}

async function load() {
  let d = { offers: [], sources: {}, cuisines: [] };
  try {
    const r = await fetch(`data/offers.json?t=${Date.now()}`, { cache: "no-cache" });
    if (r.ok) d = await r.json();
  } catch {}   // offline and nothing cached yet: show the empty state
  state.today = bhToday();
  state.generatedAt = d.generatedAt || null;
  lastLoad = Date.now();
  state.offers = [...d.offers, ...myOffers()].map(prep);
  // "new" only means something after a source's first run: compare with the earliest sighting per source
  state.firstRun = {};
  for (const o of state.offers) if (!state.firstRun[o.source] || o.firstSeen < state.firstRun[o.source]) state.firstRun[o.source] = o.firstSeen;
  state.cuisines = d.cuisines?.length ? d.cuisines : [...new Set(state.offers.flatMap(o => o.cuisines || []))];
  state.sources = d.sources;
  buildChips(); buildSources(); buildAreas(); render(); footer(); staleBanner();
}

// Deal types, detected from item names, offer titles and captions (English + Arabic).
// test(text, pct) runs on one item or on the offer's own text.
const NOT_FREE = /\b(gluten|sugar|fat|lactose|dairy|nut|caffeine|cage|guilt|hands|oil|msg|carb|soy)[- ]free\b/gi;
const DEALS = [
  { id: "half",   label: "50% off or more",   test: (t, p) => p >= 50 },
  { id: "bogo",   label: "Buy 1 Get 1",       test: t => /buy\s*(1|one)\s*get\s*(1|one)|\bb1g1\b|\bbogo\b|\b1\s*\+\s*1\b|\b2\s*for\s*1\b|two for one|second\s+\w+\s+(is\s+)?free|اشتر[يِ]?\s*(1|واحد|واحدة)|واحد\s*و\s*واحد|1\s*[+و]\s*1/i.test(t) },
  { id: "pct",    label: "% off",             test: (t, p) => p > 0 || /\d{1,2}\s?%|خصم/.test(t) },
  { id: "free",   label: "Free item",         test: t => { const s = t.replace(NOT_FREE, ""); return /\bfree\b(?!\s*delivery)|complimentary|on the house|مجان[اًي]?|ببلاش/i.test(s); } },
  { id: "combo",  label: "Combos & meal deals", test: t => /\bcombo|meal deal|\bbundle|family (meal|box|deal)|\bfeast\b|\bbox for\b|sharing box|\bmeal for \d|value meal|وجبة|بوكس|كومبو/i.test(t) },
  { id: "fixed",  label: "Fixed-price deals", test: t => /\b(only|just|for|@)\s*(bd|bhd)\s*\d|\b(only|just|for)\s*\d+(\.\d+)?\s*(bd|bhd)\b|\d+(\.\d+)?\s*(bd|bhd)\s*only|بـ?\s*\d+(\.\d+)?\s*(دينار|د\.ب)|فقط/i.test(t) },
  { id: "time",   label: "Day & time deals",  test: t => /happy hour|\b(every|on)\s+(mon|tues|wednes|thurs|fri|satur|sun)days?\b|weekday|weekend|lunch (deal|offer|special)|breakfast (deal|offer)|late night|midnight|\d\s*(am|pm)\s*(-|to|–)\s*\d|limited time|today only|الجمعة|الخميس|وقت محدود/i.test(t) },
  { id: "unl",    label: "Unlimited & buffets", test: t => /unlimited|all you can eat|\bbuffet|\bbrunch\b|bottomless|refill|بوفيه|مفتوح/i.test(t) },
  { id: "fdel",   label: "Free delivery",     test: t => /free delivery|توصيل مجاني/i.test(t) },
];

function dealTypes(text, pct) {
  const s = new Set();
  for (const d of DEALS) if (d.test(text || "", pct || 0)) s.add(d.id);
  return s;
}

// Precompute a lowercase search blob once per offer
function prep(o) {
  o.items = o.items || [];
  for (const i of o.items) i._deals = dealTypes(`${i.name} ${i.desc || ""}`, i.pct);
  o._deals = dealTypes(`${o.title} ${o.detail || ""}`, o.items.length ? 0 : o.maxPct);
  for (const i of o.items) for (const d of i._deals) o._deals.add(d);
  if (o.deliveryFee === "0") o._deals.add("fdel");
  o._hay = [o.restaurant, o.handle, o.branch, o.title, o.detail, ...(o.cuisines || []), ...(o.rawCuisines || []),
            ...o.items.map(i => i.name + " " + (i.desc || ""))].join(" ").toLowerCase();
  o.validUntil = o.validUntil || o.expires || null;
  return o;
}

function tokens() { return state.q.toLowerCase().split(/\s+/).filter(Boolean); }

// Cuisine matching works on DISHES: picking "Fried Chicken" shows a desi restaurant only if one of its
// discounted dishes is fried chicken — unless fried chicken is the restaurant's main thing (KFC, a broast
// place), where every dish counts.
const mainCuisines = o => o.primary || o.cuisines || [];
const itemCuisine = (o, i, c) => (i.cuisines || []).includes(c) || mainCuisines(o).includes(c);
const offerCuisine = (o, c) => o.items.length ? o.items.some(i => itemCuisine(o, i, c)) : (o.cuisines || []).includes(c);
const filtering = toks => toks.length || state.cuisine.size || state.deals.size;

// Filters combine per DISH: with "Fried Chicken" + "Combos" picked, a dish must be a fried-chicken combo.
// Within one dropdown any tick counts (Pizza OR Burgers).
const textMatch = (i, toks) => {
  const t = (i.name + " " + (i.desc || "")).toLowerCase();
  return toks.every(k => t.includes(k) || (/^\d+%?$/.test(k) && i.pct >= parseInt(k)));
};
const cuisineOk = (o, i, set = state.cuisine) => !set.size || [...set].some(c => itemCuisine(o, i, c));
// free delivery belongs to the restaurant, not a dish
const dealOk = (o, i, set = state.deals) => !set.size || [...set].some(d => i._deals.has(d) || (d === "fdel" && o._deals.has(d)));

// Does this dish match what you're looking for? textOnItems: whether the search words appear in any
// of this restaurant's dishes (if they only match the restaurant's name, the dishes aren't filtered by them).
function itemHit(o, i, toks, textOnItems = toks.length > 0 && o.items.some(x => textMatch(x, toks))) {
  if (!state.cuisine.size && !state.deals.size && !textOnItems) return false;
  return cuisineOk(o, i) && dealOk(o, i) && (!textOnItems || textMatch(i, toks));
}

function matches(o, toks, ignoreCuisine = false, ignoreDeals = false) {
  if (!state.src.has(o.source)) return false;
  if (o.validUntil && o.validUntil < state.today) return false;   // expired: never shown
  if (state.channel !== "all" && o.channel !== state.channel && o.channel !== "both") return false;
  if (state.minPct && o.maxPct < state.minPct) return false;
  if (state.area && !(o.areas || []).includes(state.area)) return false;
  if (state.newOnly && !isNew(o, 7)) return false;
  if (!ignoreDeals && state.deals.size && ![...state.deals].some(d => o._deals.has(d))) return false;
  if (o.items.length && !ignoreCuisine && !ignoreDeals && (state.cuisine.size || state.deals.size)
      && !o.items.some(i => cuisineOk(o, i) && dealOk(o, i))) return false;
  if (!ignoreCuisine && state.cuisine.size) {
    const any = [...state.cuisine].some(c => offerCuisine(o, c));
    if (!any) return false;
  }
  for (const k of toks) {
    const pct = k.match(/^(\d{1,2})%$/);
    if (pct) { if (o.maxPct < +pct[1]) return false; continue; }
    if (!o._hay.includes(k)) return false;
  }
  return true;
}

function isNew(o, days) {
  return o.source !== "manual" && o.firstSeen > state.firstRun[o.source] && daysAgo(o.firstSeen) <= days;
}
function daysAgo(iso) {
  if (!iso) return 999;
  return Math.round((Date.parse(state.today || new Date()) - Date.parse(iso)) / 864e5);
}
function ago(iso) {
  const d = daysAgo(iso);
  return d <= 0 ? "today" : d === 1 ? "yesterday" : d < 30 ? `${d} days ago` : new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function sorted(list) {
  const by = {
    pct: (a, b) => (b._pct ?? b.maxPct) - (a._pct ?? a.maxPct) || (b._hits?.length || b.items.length) - (a._hits?.length || a.items.length),
    new: (a, b) => (b.date || b.firstSeen || "").localeCompare(a.date || a.firstSeen || ""),
    rating: (a, b) => (b.rating || 0) - (a.rating || 0),
    items: (a, b) => b.items.length - a.items.length,
    az: (a, b) => a.restaurant.localeCompare(b.restaurant),
    ending: (a, b) => (a.validHow === "stated" || a.source === "manual" ? 0 : 1) - (b.validHow === "stated" || b.source === "manual" ? 0 : 1)
                      || (a.validUntil || "9999").localeCompare(b.validUntil || "9999"),
  }[state.sort];
  return list.sort(by);
}

function fillPicker(sel, rows, set, allLabel) {
  const el = $(sel), list = el.querySelector(".picker-list"), top = list.scrollTop;
  list.innerHTML = rows.map(r => `<label class="pick ${!r.n && !set.has(r.v) ? "none" : ""}">
      <input type="checkbox" value="${esc(r.v)}" ${set.has(r.v) ? "checked" : ""}><span>${esc(r.label)}</span><b>${r.n}</b></label>`).join("");
  list.scrollTop = top;
  const picked = rows.filter(r => set.has(r.v)).map(r => r.label);
  el.querySelector(".picker-value").textContent = !picked.length ? allLabel : picked.length <= 2 ? picked.join(", ") : `${picked[0]} +${picked.length - 1}`;
  el.classList.toggle("on", picked.length > 0);
}

function buildPickers() {
  const toks = tokens();
  const baseC = state.offers.filter(o => matches(o, toks, true));          // counts ignore their own filter
  const baseD = state.offers.filter(o => matches(o, toks, false, true));
  const one = x => new Set([x]);
  const nC = c => baseC.filter(o => o.items.length ? o.items.some(i => cuisineOk(o, i, one(c)) && dealOk(o, i)) : offerCuisine(o, c)).length;
  const nD = d => baseD.filter(o => o.items.length && d !== "fdel" ? o.items.some(i => dealOk(o, i, one(d)) && cuisineOk(o, i)) : o._deals.has(d)).length;
  fillPicker("#cuisinePicker", state.cuisines.map(c => ({ v: c, label: c, n: nC(c) })), state.cuisine, "All cuisines");
  fillPicker("#dealPicker", DEALS.map(d => ({ v: d.id, label: d.label, n: nD(d.id) })), state.deals, "Any deal");
  // what's selected, as removable chips under the dropdowns
  $("#activeFilters").innerHTML =
    [...state.cuisine].map(c => `<button class="chip on" data-rm-c="${esc(c)}">${esc(c)} ✕</button>`).join("") +
    DEALS.filter(d => state.deals.has(d.id)).map(d => `<button class="chip deal" data-rm-d="${d.id}">${esc(d.label)} ✕</button>`).join("");
}

function buildChips() { buildPickers(); }

function buildSources() {
  $("#sourceToggles").innerHTML = Object.entries(SOURCES).map(([k, s]) => {
    const n = state.offers.filter(o => o.source === k).length;
    return `<label title="${n} offers"><input type="checkbox" data-s="${k}" ${state.src.has(k) ? "checked" : ""}>
      <span class="dot" style="background:${s.color}"></span>${s.label}</label>`;
  }).join("");
}

function buildAreas() {
  const areas = [...new Set(state.offers.flatMap(o => o.areas || []))].sort();
  $("#area").innerHTML = `<option value="">All areas</option>` + areas.map(a => `<option ${a === state.area ? "selected" : ""}>${esc(a)}</option>`).join("");
  $("#minPct").value = state.minPct; $("#sort").value = state.sort;
  document.querySelectorAll("#channelSeg button").forEach(b => b.classList.toggle("on", b.dataset.v === state.channel));
}

function hl(text, toks) {
  let s = esc(text);
  for (const k of toks) {
    if (k.length < 2 || /%$/.test(k)) continue;
    s = s.replace(new RegExp(`(${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"), "<mark>$1</mark>");
  }
  return s;
}

// How long is this offer good for? Shown on every card so you know how fresh it is.
function validity(o) {
  const left = o.validUntil ? daysBetween(state.today, o.validUntil) : null;
  const ends = left === 0 ? "Ends today" : left === 1 ? "Ends tomorrow" : o.validUntil ? `Ends ${fmtDay(o.validUntil)}` : "";
  if (o.source === "talabat") {
    const h = o.checkedAt ? Math.max(0, Math.round((Date.now() - Date.parse(o.checkedAt)) / 36e5)) : null;
    const when = h == null ? "" : h < 1 ? "just now" : h < 24 ? `${h}h ago` : `${Math.round(h / 24)} days ago`;
    return { line: when ? `Price checked on Talabat ${when}` : "" };
  }
  if (o.source === "manual") return { badge: o.validUntil ? `<span class="badge warn">${ends}</span>` : "" };
  if (o.validHow === "stated") return { badge: `<span class="badge warn">${ends}</span>`, line: "End date from the post" };
  if (o.validHow === "recurring") return { badge: `<span class="badge">Recurring deal</span>`, line: `Repeats regularly · shown until ${fmtDay(o.validUntil)}, check the post` };
  return { line: `No end date given · hidden after ${fmtDay(o.validUntil)}` };
}
function daysBetween(a, b) { return Math.round((Date.parse(b) - Date.parse(a)) / 864e5); }

// Every card ends with where the offer came from, so it can be checked at the source
function sourceLink(o) {
  if (!o.url) return `<div class="source none">Source · added by you (no link)</div>`;
  let host = "";
  try { host = new URL(o.url).hostname.replace(/^www\./, ""); } catch {}
  const what = {
    talabat: "Check on Talabat",
    instagram: o.handle ? `Instagram post by @${esc(o.handle)}` : "Open the Instagram post",
    news: `Read the story${o.restaurant && o.restaurant !== "News" ? ` · ${esc(o.restaurant)}` : ""}`,
    manual: "Open your link",
  }[o.source] || "Open source";
  return `<a class="source" href="${esc(o.url)}" target="_blank" rel="noopener"><span>Source · ${what}</span><span class="host">${esc(host)} ↗</span></a>`;
}

function card(o, toks) {
  const src = SOURCES[o.source];
  const initials = esc((o.restaurant || "?").replace(/[^A-Za-z؀-ۿ ]/g, "").trim().slice(0, 1).toUpperCase() || "?");
  const logo = o.image ? `<img class="card-logo" src="${esc(o.image)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'card-logo',textContent:'${initials}'}))">`
                       : `<div class="card-logo">${initials}</div>`;
  const meta = [];
  if (o.rating) meta.push(`★ ${o.rating}`);
  if (o.handle) meta.push(`@${esc(o.handle)}`);
  if (o.date) meta.push(ago(o.date));
  else if (o.source === "instagram") meta.push("date not shown");
  if (o.deliveryTime) meta.push(esc(o.deliveryTime));
  if (o.deliveryFee === "0") meta.push("free delivery");

  const badges = [`<span class="badge src-${o.source}">${src.label}</span>`, `<span class="badge">${CHANNEL[o.channel] || "—"}</span>`];
  if (isNew(o, 2)) badges.push(`<span class="badge new">New</span>`);
  const v = validity(o);
  if (v.badge) badges.push(v.badge);
  for (const d of DEALS) if (!["pct", "half", "fdel"].includes(d.id) && o._deals.has(d.id)) badges.push(`<span class="badge deal ${state.deals.has(d.id) ? "on" : ""}">${esc(d.label)}</span>`);
  for (const c of o.cuisines.slice(0, 4)) badges.push(`<span class="badge">${esc(c)}</span>`);

  let body = "";
  if (o.items.length) {
    const hits = o._hits || o.items.filter(i => itemHit(o, i, toks));
    const rest = o.items.filter(i => !hits.includes(i));
    const ordered = [...hits, ...rest];
    const focused = o._focused ?? (filtering(toks) && hits.length > 0);      // a filter is on: list only what matched
    const head = focused ? hits.slice(0, 8) : ordered.slice(0, 4);
    const li = i => `<li><span class="nm ${hits.includes(i) ? "hit" : ""}">${hl(i.name, toks)}</span><span><s>${bd(i.was)}</s> <span class="now">${bd(i.now)}</span></span><span class="off">−${i.pct}%</span></li>`;
    body = focused
      ? `<div class="offer-line"><span class="match-line">${hits.length} matching dish${hits.length > 1 ? "es" : ""}${hits.length > 1 ? ` · up to ${o._pct}% off` : ` · ${o._pct}% off`}</span></div>`
      : `<div class="offer-line">${esc(o.title)}</div>`;
    body += `
      <ul class="items" data-all="${o.items.length}">${head.map(li).join("")}</ul>
      ${ordered.length > head.length ? `<button class="textbtn" data-expand="${esc(o.id)}">${focused ? `Show all ${o.items.length} discounted items` : `Show all ${o.items.length} items`}</button>` : ""}`;
    if (o.detail) body += `<div class="caption">${hl(o.detail, toks)}</div>`;
  } else {
    body = o.source === "instagram"
      ? `<div class="caption">${hl(o.detail || o.title, toks)}</div>`
      : `<div class="offer-line">${hl(o.title, toks)}</div>${o.detail ? `<div class="caption">${hl(o.detail, toks)}</div>` : ""}`;
  }
  if (v.line) body += `<div class="validity">${v.line}</div>`;
  const areas = (o.areas || []).length ? `<span class="meta">Delivers to ${esc(o.areas.slice(0, 3).join(", "))}${o.areas.length > 3 ? ` +${o.areas.length - 3}` : ""}</span>` : "<span></span>";
  const del = o.source === "manual" ? `<button class="textbtn" data-del="${esc(o.id)}">Remove</button>` : "";
  return `<article class="card">
    <div class="card-head">${logo}
      <div class="card-title"><h3>${hl(o.restaurant, toks)}</h3><div class="meta">${meta.join("<span>·</span>")}</div></div>
      ${(o._pct ?? o.maxPct) ? `<span class="pct">${(o._focused ? o._hits.length : o.items.length) > 1 ? "≤" : ""}${o._pct ?? o.maxPct}%</span>` : ""}
    </div>
    <div class="badges">${badges.join("")}</div>
    ${body}
    ${areas !== "<span></span>" || del ? `<div class="card-foot">${areas}${del}</div>` : ""}
    ${sourceLink(o)}
  </article>`;
}

let current = [];
function render(resetPage = false) {
  if (resetPage) state.shown = PAGE;
  const toks = tokens();
  const focus = filtering(toks);
  current = state.offers.filter(o => matches(o, toks));
  for (const o of current) {
    const onItems = toks.length > 0 && o.items.some(x => textMatch(x, toks));
    o._hits = o.items.filter(i => itemHit(o, i, toks, onItems));
    o._focused = focus && o._hits.length > 0;
    o._pct = o._focused ? Math.max(...o._hits.map(i => i.pct)) : o.maxPct;   // best deal among what you asked for
  }
  current = sorted(current);
  const items = current.reduce((n, o) => n + (o._focused ? o._hits.length : o.items.length), 0);
  $("#results").innerHTML = current.slice(0, state.shown).map(o => card(o, toks)).join("");
  $("#moreBtn").hidden = current.length <= state.shown;
  $("#moreBtn").textContent = `Show more (${current.length - state.shown} left)`;
  const bySrc = Object.keys(SOURCES).map(k => [k, current.filter(o => o.source === k).length]).filter(x => x[1]);
  $("#summary").innerHTML = current.length
    ? `<strong>${current.length.toLocaleString()}</strong> offers${items ? ` · ${items.toLocaleString()} ${current.some(o => o._focused) ? "matching dishes" : "discounted menu items"}` : ""} · ${bySrc.map(([k, n]) => `${n} ${SOURCES[k].label}`).join(", ")}`
    : "";
  const empty = $("#empty");
  empty.hidden = current.length > 0;
  if (!state.offers.length) {
    empty.innerHTML = state.local
      ? `<h2>No offers yet</h2><p>Hit <strong>Refresh offers</strong> to pull today's deals from Talabat, Instagram and Bahrain news.<br>Talabat takes a few minutes the first time — Instagram and news come in first.</p>`
      : `<h2>No offers right now</h2><p>Offers update every morning. If this stays empty, the daily refresh may have failed.</p>`;
  } else if (!current.length && !state.offers.some(o => !o.validUntil || o.validUntil >= state.today)) {
    empty.innerHTML = `<h2>All saved offers have ended</h2><p>Nothing here is still valid today, so it's all hidden.` +
      (state.generatedAt ? ` Offers were last updated ${agoTime(state.generatedAt)} — the daily refresh may have failed.` : "") + `</p>`;
  } else if (!current.length) {
    empty.innerHTML = `<h2>Nothing matches</h2><p>Try a different cuisine, fewer words, or turn more sources on.</p>`;
  }
  buildChips();
  // how many non-default filters are on (shown on the phone's "Filters" button)
  const n = (state.channel !== "all") + (state.src.size !== Object.keys(SOURCES).length) + !!state.minPct + !!state.area + state.newOnly + (state.sort !== "pct");
  $("#filterCount").textContent = n || "";
}

function footer() {
  const parts = Object.entries(state.sources).map(([k, s]) =>
    `${SOURCES[k]?.label || k}: ${s.count} offers, updated ${new Date(s.updatedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` +
    (s.ok === false ? ` <span class="warn-text">(last run had a problem${s.note ? ": " + esc(s.note) : ""})</span>` : ""));
  $("#foot").innerHTML = (parts.length ? parts.join(" · ") : "Not refreshed yet") +
    `<br>Expired offers are hidden automatically. Talabat offers disappear if a refresh hasn't re-confirmed them within a day; ` +
    `Instagram and news offers use the end date in the post, or a short window after posting if none is given. Always check the post for conditions.`;
  const up = $("#updated");
  if (up) up.textContent = state.generatedAt ? `Updated ${agoTime(state.generatedAt)}` : "";
}

function agoTime(iso) {
  const h = (Date.now() - Date.parse(iso)) / 36e5;
  return h < 1 ? "just now" : h < 24 ? `${Math.round(h)}h ago` : `${Math.round(h / 24)} day${h >= 36 ? "s" : ""} ago`;
}

// Warn when the data itself is old (daily refresh failing) — offers are still expiry-filtered either way
function staleBanner() {
  const b = $("#stale");
  const h = state.generatedAt ? (Date.now() - Date.parse(state.generatedAt)) / 36e5 : 0;
  b.hidden = !(h > 30);
  if (h > 30) b.innerHTML = `Offers were last updated <strong>${agoTime(state.generatedAt)}</strong>. Expired deals are already hidden, but new offers may be missing — the daily refresh may have failed.`;
}

// ---------- refresh ----------
let polling = null;
async function refresh(sources) {
  $("#refreshMenu").hidden = true;
  try { await api(`/api/refresh?sources=${sources}`, { method: "POST" }); }
  catch (e) { if (!/already running/.test(e.message)) return alert(e.message); }
  watch();
}
function watch() {
  $("#progress").hidden = false;
  $("#refreshBtn").disabled = true;
  $("#refreshBtn").textContent = "Refreshing…";
  clearInterval(polling);
  let lastSource = null;
  polling = setInterval(async () => {
    const s = await api("/api/status").catch(() => null);
    if (!s) return;
    $("#progStage").textContent = s.stage || "Finishing…";
    const bar = $("#progBar").parentElement;
    bar.classList.toggle("indeterminate", !s.total);
    $("#progBar").style.width = s.total ? `${(100 * s.done / s.total).toFixed(1)}%` : "";
    $("#progCount").textContent = s.total ? `${s.done} / ${s.total}` : "";
    $("#progLog").textContent = s.log.slice(-8).join("\n");
    if (lastSource && s.source !== lastSource) load();   // show each source's results as soon as it lands
    lastSource = s.source;
    if (!s.running) {
      clearInterval(polling);
      $("#refreshBtn").disabled = false;
      $("#refreshBtn").textContent = "Refresh offers";
      await load();
      setTimeout(() => { $("#progress").hidden = true; }, 4000);
    }
  }, 1000);
}

// ---------- add offer ----------
const addSel = new Set();
// rough cuisine guess for offers typed in by hand (chip names + a few common dishes)
function guessCuisines(text) {
  const t = text.toLowerCase();
  const extra = { "Pakistani": /karahi|nihari|haleem/, "Burgers": /burger/, "Pizza": /pizza/, "Shawarma": /shawarma/,
                  "Fried Chicken": /broast|fried chicken|wings/, "Coffee & Drinks": /coffee|karak|latte|tea/, "Desserts": /cake|dessert|ice cream|kunafa/ };
  return state.cuisines.filter(c => t.includes(c.toLowerCase()) || extra[c]?.test(t));
}

function openAdd() {
  addSel.clear();
  $("#addCuisines").innerHTML = state.cuisines.map(c => `<button type="button" class="chip" data-c="${esc(c)}">${esc(c)}</button>`).join("");
  $("#addForm").reset();
  $("#addDlg").showModal();
}
$("#addCuisines").addEventListener("click", e => {
  const b = e.target.closest("[data-c]"); if (!b) return;
  const c = b.dataset.c; addSel.has(c) ? addSel.delete(c) : addSel.add(c); b.classList.toggle("on");
});
$("#addForm").addEventListener("submit", async e => {
  if (e.submitter?.value !== "save") return;
  const f = Object.fromEntries(new FormData($("#addForm")));
  const today = bhToday();
  const plus14 = new Date(Date.now() + 14 * 864e5).toLocaleDateString("en-CA", { timeZone: "Asia/Bahrain" });
  const text = `${f.restaurant} ${f.title} ${f.detail || ""}`;
  const o = {
    id: `manual:${Date.now()}`, source: "manual", channel: f.channel || "in-person",
    restaurant: f.restaurant.trim(), handle: "", branch: "", rawCuisines: [],
    cuisines: addSel.size ? [...addSel] : guessCuisines(text), title: f.title.trim(), detail: (f.detail || "").trim(),
    items: [], maxPct: +f.pct || 0, url: (f.url || "").trim(), image: "", rating: null, areas: [],
    date: today, firstSeen: today, validUntil: f.expires || plus14,   // no end date → kept 2 weeks
  };
  saveMine([...myOffers(), o]);
  await load();
});

// ---------- settings ----------
let allAreas = null;
async function openSettings() {
  const s = await api("/api/settings");
  const f = $("#setForm");
  f.igAccounts.value = s.igAccounts.join("\n");
  f.igQueries.value = s.igQueries.join("\n");
  f.igDefaultDays.value = s.igDefaultDays;
  f.newsDefaultDays.value = s.newsDefaultDays;
  $("#areaFilter").value = "";
  $("#setDlg").showModal();
  const chosen = new Set(s.areas);
  try {
    allAreas = allAreas || await api("/api/areas");
    $("#areaList").innerHTML = allAreas.map(a =>
      `<label data-n="${esc(a.name.toLowerCase())}"><input type="checkbox" value="${a.id}" ${chosen.has(a.id) ? "checked" : ""}>${esc(a.name)}</label>`).join("");
  } catch (e) { $("#areaList").innerHTML = `<p class="muted">Couldn't load areas (${esc(e.message)}).</p>`; }
}
$("#areaFilter").addEventListener("input", e => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#areaList label").forEach(l => { l.hidden = !l.dataset.n.includes(q); });
});
$("#setForm").addEventListener("submit", async e => {
  if (e.submitter?.value !== "save") return;
  const f = $("#setForm");
  const lines = v => v.split("\n").map(x => x.trim()).filter(Boolean);
  const areas = [...document.querySelectorAll("#areaList input:checked")].map(i => i.value);
  const body = { igAccounts: lines(f.igAccounts.value), igQueries: lines(f.igQueries.value),
                 igDefaultDays: +f.igDefaultDays.value || 7, newsDefaultDays: +f.newsDefaultDays.value || 10 };
  if (areas.length) body.areas = areas;
  await api("/api/settings", { method: "POST", body: JSON.stringify(body) }).catch(e => alert(e.message));
});

// ---------- phone refresh: asks GitHub to run the refresh job now ----------
const GH_API = "https://api.github.com";
const WORKFLOW = "refresh.yml";
function ghConf() { try { return JSON.parse(localStorage.getItem("lugma.gh") || "null"); } catch { return null; } }
function guessRepo() {   // on GitHub Pages the address itself says whose repo it is: <user>.github.io/<repo>/
  const m = location.hostname.match(/^([\w-]+)\.github\.io$/i);
  const seg = location.pathname.split("/").filter(Boolean)[0];
  return m ? `${m[1]}/${seg || location.hostname}` : "";
}
async function gh(path, opts = {}) {
  const c = ghConf();
  const r = await fetch(`${GH_API}/repos/${c.repo}${path}`, { ...opts, cache: "no-store", headers: {
    Accept: "application/vnd.github+json", Authorization: `Bearer ${c.token}`, "X-GitHub-Api-Version": "2022-11-28",
    ...(opts.body ? { "Content-Type": "application/json" } : {}) } });
  if (r.status === 401) throw new Error("GitHub didn't accept the key — it may have expired. Add a new one in Refresh settings.");
  if (r.status === 403 || r.status === 404) throw new Error(`This key can't start refreshes for ${c.repo}. Check the repository name and that the key has "Actions: Read and write".`);
  if (!r.ok) throw new Error(`GitHub error ${r.status}`);
  return r.status === 204 ? null : r.json();
}
const latestRun = async () => (await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`)).workflow_runs[0];

function openGh() {
  const c = ghConf() || {};
  const f = $("#ghForm");
  f.repo.value = c.repo || guessRepo();
  f.token.value = c.token || "";
  $("#ghForget").hidden = !c.token;
  $("#ghDlg").showModal();
}
$("#ghForm").addEventListener("submit", async e => {
  const v = e.submitter?.value;
  if (v === "forget") { try { localStorage.removeItem("lugma.gh"); } catch {} return; }
  if (v !== "save") return;
  const f = $("#ghForm");
  const conf = { repo: f.repo.value.trim().replace(/^https?:\/\/github\.com\//, "").replace(/\/$/, ""), token: f.token.value.trim() };
  try { localStorage.setItem("lugma.gh", JSON.stringify(conf)); } catch { return alert("Couldn't save on this device."); }
  try { await latestRun(); alert("Connected ✓ — tap Refresh to update offers now."); }
  catch (err) { alert(err.message); }
});

async function cloudRefresh(sources) {
  $("#refreshMenu").hidden = true;
  const since = Date.now() - 30e3;
  try {
    const run = await latestRun();
    if (run && run.status !== "completed") return watchCloud(Date.parse(run.created_at) - 1);   // one's already going
    const branch = (await gh("")).default_branch || "main";
    await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: branch, inputs: { sources } }) });
  } catch (e) { return alert(e.message); }
  watchCloud(since);
}

let cloudTimer = null;
function watchCloud(since) {
  clearTimeout(cloudTimer);
  $("#progress").hidden = false;
  $("#refreshBtn").disabled = true;
  $("#refreshBtn").textContent = "Refreshing…";
  $("#progBar").parentElement.classList.add("indeterminate");
  $("#progStage").textContent = "Asking GitHub to start…";
  $("#progCount").textContent = "";
  $("#progLog").textContent = "";
  const done = (msg, reload) => {
    $("#refreshBtn").disabled = false;
    $("#refreshBtn").textContent = "Refresh";
    $("#progStage").innerHTML = msg;
    $("#progBar").parentElement.classList.remove("indeterminate");
    $("#progBar").style.width = "100%";
    if (reload) setTimeout(load, 15000);   // give GitHub Pages a moment to publish
    setTimeout(() => { $("#progress").hidden = true; }, 20000);
  };
  const tick = async () => {
    let run;
    try { run = await latestRun(); } catch (e) { return done(esc(e.message)); }
    if (!run || Date.parse(run.created_at) < since) {       // our run hasn't appeared yet
      if (Date.now() - since > 3 * 6e4) return done("GitHub didn't start the refresh. Try again in a minute.");
      cloudTimer = setTimeout(tick, 4000); return;
    }
    const mins = Math.max(0, Math.round((Date.now() - Date.parse(run.run_started_at || run.created_at)) / 6e4));
    if (run.status === "completed") {
      const link = ` <a href="${esc(run.html_url)}" target="_blank" rel="noopener">details</a>`;
      return run.conclusion === "success"
        ? done("Refreshed ✓ — loading new offers…", true)
        : done(`Finished with a problem (${esc(run.conclusion)}) — other sources still updated.${link}`, true);
    }
    let step = run.status === "queued" ? "Waiting for a GitHub runner…" : "Working…";
    try {
      const jobs = (await gh(`/actions/runs/${run.id}/jobs`)).jobs;
      const steps = jobs[0]?.steps || [];
      const cur = steps.find(s => s.status === "in_progress");
      const names = { "Collect offers": "Collecting offers (Talabat is the slow part)", "Run actions/upload-pages-artifact@v3": "Publishing…", "Run actions/deploy-pages@v4": "Publishing…" };
      if (cur) step = names[cur.name] || cur.name;
      const fin = steps.filter(s => s.status === "completed").length;
      if (steps.length) {
        $("#progBar").parentElement.classList.remove("indeterminate");
        $("#progBar").style.width = `${Math.max(5, 100 * fin / steps.length)}%`;
      }
    } catch {}
    $("#progStage").textContent = step;
    $("#progCount").textContent = `${mins} min`;
    $("#progLog").innerHTML = `Running on GitHub — you can close the app; the new offers will be there when you come back. <a href="${esc(run.html_url)}" target="_blank" rel="noopener">View run</a>`;
    cloudTimer = setTimeout(tick, 10000);
  };
  tick();
}

// ---------- mode ----------
async function detectMode() {
  if (!/^(localhost|127\.0\.0\.1)$/.test(location.hostname)) { state.local = false; }
  else try { const r = await fetch("api/status", { cache: "no-store" }); state.local = r.ok && (await r.json()).log !== undefined; }
  catch { state.local = false; }
  document.body.classList.toggle("local", state.local);
  $("#settingsBtn").title = state.local ? "Settings" : "Refresh settings";
  if (!state.local) {
    $("#refreshBtn").textContent = "Refresh";
    $("#refreshMenu").innerHTML = `
      <button data-cloud="news,instagram">Quick refresh <small>Instagram + news · ~3 min</small></button>
      <button data-cloud="news,instagram,talabat">Full refresh <small>incl. Talabat · ~20 min</small></button>
      <button data-ghsetup="1">Refresh settings…</button>`;
  }
}

// ---------- wiring ----------
$("#filtersToggle").addEventListener("click", () => {
  const open = $("#filters").classList.toggle("open");
  $("#filtersToggle").setAttribute("aria-expanded", open);
});
let tq;
$("#q").addEventListener("input", e => { clearTimeout(tq); tq = setTimeout(() => { state.q = e.target.value.trim(); render(true); }, 120); });
function closePickers() {
  document.querySelectorAll(".picker-panel").forEach(p => { p.hidden = true; });
  document.querySelectorAll(".picker-btn").forEach(b => b.setAttribute("aria-expanded", "false"));
}
document.querySelectorAll(".picker").forEach(p => {
  const btn = p.querySelector(".picker-btn"), panel = p.querySelector(".picker-panel");
  const set = () => p.dataset.kind === "cuisine" ? state.cuisine : state.deals;
  btn.addEventListener("click", e => {
    e.stopPropagation();
    const opening = panel.hidden;
    closePickers();
    panel.hidden = !opening;
    btn.setAttribute("aria-expanded", opening);
  });
  panel.addEventListener("click", e => e.stopPropagation());
  panel.addEventListener("change", e => {
    const v = e.target.value;
    e.target.checked ? set().add(v) : set().delete(v);
    remember(); render(true);
  });
  panel.querySelector("[data-clear]").addEventListener("click", () => { set().clear(); remember(); render(true); });
  panel.querySelector("[data-done]").addEventListener("click", closePickers);
});
document.addEventListener("click", closePickers);
document.addEventListener("keydown", e => { if (e.key === "Escape") closePickers(); });
$("#activeFilters").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.rmC) state.cuisine.delete(b.dataset.rmC);
  if (b.dataset.rmD) state.deals.delete(b.dataset.rmD);
  remember(); render(true);
});
$("#channelSeg").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  state.channel = b.dataset.v;
  document.querySelectorAll("#channelSeg button").forEach(x => x.classList.toggle("on", x === b));
  remember(); render(true);
});
$("#sourceToggles").addEventListener("change", e => {
  const k = e.target.dataset.s; e.target.checked ? state.src.add(k) : state.src.delete(k); remember(); render(true);
});
$("#minPct").addEventListener("change", e => { state.minPct = +e.target.value; remember(); render(true); });
$("#area").addEventListener("change", e => { state.area = e.target.value; remember(); render(true); });
$("#sort").addEventListener("change", e => { state.sort = e.target.value; remember(); render(true); });
$("#newOnly").addEventListener("change", e => { state.newOnly = e.target.checked; render(true); });
$("#moreBtn").addEventListener("click", () => { state.shown += PAGE; render(); });
$("#results").addEventListener("click", async e => {
  const x = e.target.closest("[data-expand]");
  if (x) {
    const o = state.offers.find(o => o.id === x.dataset.expand);
    const toks = tokens();
    const ul = x.previousElementSibling;
    const hitSet = new Set(o._hits || []);
    const sortedItems = [...o.items.filter(i => hitSet.has(i)), ...o.items.filter(i => !hitSet.has(i))];
    ul.innerHTML = sortedItems.map(i => `<li><span class="nm ${hitSet.has(i) ? "hit" : ""}">${hl(i.name, toks)}</span><span><s>${bd(i.was)}</s> <span class="now">${bd(i.now)}</span></span><span class="off">−${i.pct}%</span></li>`).join("");
    x.remove();
    return;
  }
  const d = e.target.closest("[data-del]");
  if (d && confirm("Remove this offer?")) { saveMine(myOffers().filter(o => o.id !== d.dataset.del)); load(); }
  const cap = e.target.closest(".caption");
  if (cap) cap.classList.toggle("open");
});
$("#refreshBtn").addEventListener("click", e => {
  if (state.local) return refresh("talabat,instagram,news");
  e.stopPropagation();
  if (!ghConf()) return openGh();
  $("#refreshMenu").hidden = !$("#refreshMenu").hidden;
});
$("#refreshMenuBtn").addEventListener("click", e => { e.stopPropagation(); $("#refreshMenu").hidden = !$("#refreshMenu").hidden; });
$("#refreshMenu").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.src) refresh(b.dataset.src);
  else if (b.dataset.cloud) cloudRefresh(b.dataset.cloud);
  else if (b.dataset.ghsetup) { $("#refreshMenu").hidden = true; openGh(); }
});
document.addEventListener("click", () => { $("#refreshMenu").hidden = true; });
$("#addBtn").addEventListener("click", openAdd);
$("#settingsBtn").addEventListener("click", () => state.local ? openSettings() : openGh());
document.addEventListener("keydown", e => { if (e.key === "/" && document.activeElement !== $("#q") && !$("dialog[open]")) { e.preventDefault(); $("#q").focus(); } });

recall();
detectMode().then(load).then(async () => {
  if (state.local) { const s = await api("/api/status"); if (s.running) watch(); return; }
  if (ghConf()) {
    try { const run = await latestRun(); if (run && run.status !== "completed") watchCloud(Date.parse(run.created_at) - 1); } catch {}
  }
});
// coming back to the app (e.g. next morning): pick up the new day + fresh data
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && (bhToday() !== state.today || Date.now() - lastLoad > 30 * 6e4)) load();
});
let lastLoad = Date.now();
if ("serviceWorker" in navigator && !state.local && location.protocol === "https:") {
  addEventListener("load", () => setTimeout(() => navigator.serviceWorker.register("sw.js").catch(() => {}), 1500));
}
