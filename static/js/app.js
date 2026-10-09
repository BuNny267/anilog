/* ============================================================
   AniLog v4.8 — Complete JavaScript
   ============================================================ */
"use strict";

const $  = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const PLACEHOLDER = "/static/images/placeholder.svg";

window.MYLIST = window.MYLIST || new Set();

/* ---------- Utilities ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
async function api(url, opts = {}) {
  try {
    const res = await fetch(url, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok && !data.error) data.error = `Request failed (${res.status})`;
    return data;
  } catch (_) {
    return { error: "Network error — are you offline?" };
  }
}
function scoreFmt(v, d = 1) {
  if (v == null || v === "") return "";
  const n = Number(v);
  if (isNaN(n)) return "";
  const s = n > 10 ? n / 10 : n;
  return s.toFixed(d);
}
function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(String(ts).replace(" ", "T"));
  if (isNaN(d)) return "";
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  if (diff < 604800) return Math.floor(diff / 86400) + "d ago";
  return d.toLocaleDateString();
}

/* ---------- Live countdown ticker ---------- */
function fmtCountdown(d) {
  if (d <= 0) return "airing now";
  const dd = Math.floor(d / 86400), h = Math.floor((d % 86400) / 3600), m = Math.floor((d % 3600) / 60), s = d % 60;
  if (dd > 0) return `in ${dd}d ${h}h`;
  if (h > 0) return `in ${h}h ${m}m`;
  if (m > 0) return `in ${m}m ${s}s`;
  return `in ${s}s`;
}
function tickCountdowns() {
  const now = Math.floor(Date.now() / 1000);
  $$("[data-countdown]").forEach(el => {
    el.textContent = fmtCountdown(Number(el.dataset.countdown) - now);
  });
}
setInterval(tickCountdowns, 1000);

/* ---------- Global state sync ---------- */
function syncAnimeUI(malId, inList, entryData = null) {
  if (inList) MYLIST.add(Number(malId)); else MYLIST.delete(Number(malId));

  $$(".quickadd").forEach(btn => {
    try {
      const d = JSON.parse(btn.dataset.json);
      if (d.mal_id == malId) {
        btn.textContent = inList ? "✓" : "+";
        btn.setAttribute("aria-label", inList ? "Edit entry" : "Add to list");
      }
    } catch (_) {}
  });

  $$("[data-fav]").forEach(btn => {
    try {
      const d = JSON.parse(btn.dataset.fav);
      if (d.mal_id == malId && entryData && "favorite" in entryData) {
        btn.classList.toggle("on", !!entryData.favorite);
        const p = btn.querySelector("svg path");
        if (p) p.setAttribute("fill", entryData.favorite ? "currentColor" : "none");
      }
    } catch (_) {}
  });

  $$("[data-reladd]").forEach(btn => {
    try {
      const d = JSON.parse(btn.dataset.reladd);
      if (d.mal_id == malId) {
        if (inList) {
          btn.outerHTML = `<span class="franchise__check" title="In your list">✓</span>`;
        }
      }
    } catch (_) {}
  });

  $$(".card").forEach(card => {
    const link = card.querySelector(".card-link");
    if (link && link.getAttribute("href") === `/anime/${malId}`) {
      const qa = card.querySelector(".quickadd");
      if (qa) qa.textContent = inList ? "✓" : "+";
    }
  });

  if (document.body.dataset.page === "anime") {
    const holder = document.getElementById("sheet-data-holder");
    if (holder && entryData) {
      try {
        const h = JSON.parse(holder.dataset.json);
        h.in_list = inList;
        if (entryData.status !== undefined) h.status = entryData.status;
        if (entryData.current_episode !== undefined) h.current_episode = entryData.current_episode;
        if (entryData.total_episodes !== undefined) h.total_episodes = entryData.total_episodes;
        if (entryData.notes !== undefined) h.notes = entryData.notes;
        if (entryData.favorite !== undefined) h.favorite = entryData.favorite;
        holder.dataset.json = JSON.stringify(h);
      } catch (_) {}
    }
  }
}

/* ---------- Toast ---------- */
function toast(msg, kind = "", undoFn = null) {
  const box = $("#toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span>${esc(msg)}</span>`;
  if (undoFn) {
    const b = document.createElement("button");
    b.className = "toast-undo"; b.textContent = "Undo";
    b.onclick = () => { undoFn(); el.remove(); };
    el.appendChild(b);
  }
  box.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 4000);
  setTimeout(() => el.remove(), 4500);
}

/* ---------- Image fallback ---------- */
document.addEventListener("error", e => {
  if (e.target && e.target.tagName === "IMG" && !e.target.dataset.fell) {
    e.target.dataset.fell = "1";
    e.target.src = PLACEHOLDER;
  }
}, true);

/* ---------- Confirm dialog ---------- */
function confirmBox(title, message, danger = false) {
  return new Promise(resolve => {
    document.body.style.overflow = "hidden";
    const root = $("#overlay-root");
    root.innerHTML = `
      <div class="overlay center" id="ov">
        <div class="dialog-card" role="alertdialog" aria-modal="true">
          <h3>${esc(title)}</h3><p>${esc(message)}</p>
          <div class="row">
            <button class="btn" id="c-no">Cancel</button>
            <button class="btn ${danger ? "btn-danger" : "btn-primary"}" id="c-yes">${danger ? "Yes, delete" : "Confirm"}</button>
          </div>
        </div>
      </div>`;
    const ov = $("#ov");
    requestAnimationFrame(() => ov.classList.add("show"));
    const done = v => {
      ov.classList.remove("show");
      document.body.style.overflow = "";
      setTimeout(() => root.innerHTML = "", 250);
      resolve(v);
    };
    $("#c-yes").onclick = () => done(true);
    $("#c-no").onclick = () => done(false);
    ov.onclick = e => { if (e.target === ov) done(false); };
    $("#c-no").focus();
  });
}

/* ---------- Stats strip ---------- */
function updateStatsStrip() {
  const strip = $(".stat-strip");
  if (!strip) return;
  api("/api/list/stats").then(data => {
    if (data.error || !data.totals) return;
    const tiles = $$(".stat-tile b", strip);
    if (tiles.length === 5) {
      tiles[0].textContent = data.totals.completed;
      tiles[1].textContent = data.totals.episodes;
      tiles[2].textContent = data.totals.watching;
      tiles[3].textContent = data.totals.planned;
      tiles[4].textContent = data.totals.favorites;
    }
  });
}

/* ---------- Confetti ---------- */
function showConfetti() {
  const c = document.createElement("div");
  c.className = "confetti-container";
  const colors = ["#8b5cf6", "#a78bfa", "#42d392", "#ffd978", "#f16d7a", "#61a8ff"];
  for (let i = 0; i < 50; i++) {
    const p = document.createElement("div");
    p.className = "confetti";
    p.style.left = Math.random() * 100 + "%";
    p.style.background = colors[Math.floor(Math.random() * colors.length)];
    p.style.animationDelay = Math.random() * 0.5 + "s";
    p.style.borderRadius = Math.random() > 0.5 ? "50%" : "2px";
    p.style.width = (Math.random() * 8 + 6) + "px";
    p.style.height = (Math.random() * 8 + 6) + "px";
    c.appendChild(p);
  }
  document.body.appendChild(c);
  setTimeout(() => c.remove(), 3500);
}

/* ---------- Theme prefs ---------- */
function applyThemePref(key, value) {
  const el = document.documentElement;
  if (key === "theme") {
    el.dataset.themepref = value;
    el.dataset.theme = value === "system"
      ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
      : value;
  } else if (key === "animations") el.dataset.anim = value;
  else if (key === "accent_color") el.dataset.accent = value;
  else if (key === "card_layout") el.dataset.cardLayout = value;
}

/* ---------- Entry Sheet ---------- */
let sheetState = null;

function openEntrySheet(item) {
  sheetState = { ...item };
  const root = $("#overlay-root");
  const inList = !!item.in_list;
  const status = item.status || "plan_to_watch";
  const total = item.episodes || item.total_episodes;

  document.body.style.overflow = "hidden";
  root.innerHTML = `
  <div class="overlay" id="ov">
    <div class="sheet" role="dialog" aria-modal="true" aria-label="Anime entry">
      <div class="sheet-handle"></div>
      <button class="sheet-close" id="sh-close" aria-label="Close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
      </button>
      <div class="sheet-head">
        <img src="${esc(item.image_url || PLACEHOLDER)}" alt="">
        <div><h3>${esc(item.title)}</h3>
        <small>${esc(item.type || "")}${item.year ? " • " + esc(item.year) : ""}${item.score ? " • ★ " + scoreFmt(item.score, 2) : ""}</small></div>
      </div>
      <div class="sheet-label">Status</div>
      <div class="status-chips" id="sh-status">
        ${[["watching","Watching"],["completed","Completed"],["plan_to_watch","Plan to Watch"],["on_hold","On Hold"],["dropped","Dropped"]]
          .map(([v, l]) => `<button type="button" data-v="${v}" class="${v === status ? "on" : ""}">${l}</button>`).join("")}
      </div>
      <div class="sheet-label">Episode Progress</div>
      <div class="sheet-episode-section">
        <div class="stepper">
          <button type="button" id="sh-ep-minus">−</button>
          <div class="sheet-ep-display">
            <input type="number" id="sh-ep-input" class="sheet-ep-input" min="0"
                   ${total ? `max="${total}"` : ""} value="${item.current_episode || 0}" inputmode="numeric">
            <span class="sheet-ep-total">/ ${total || "?"}</span>
          </div>
          <button type="button" id="sh-ep-plus">+</button>
        </div>
        ${total ? `<div class="sheet-ep-bar"><span style="width:${Math.min(100, ((item.current_episode || 0) / total * 100))}%"></span></div>` : ""}
      </div>
      <div class="sheet-label">Notes</div>
      <textarea id="sh-notes" maxlength="4000" placeholder="Why did you start it? Thoughts so far…">${esc(item.notes || "")}</textarea>
      <div class="sheet-actions">
        ${inList ? '<button class="btn btn-danger" id="sh-delete">Remove</button>' : ""}
        <button class="btn btn-primary" id="sh-save">${inList ? "Save Changes" : "Add to List"}</button>
      </div>
    </div>
  </div>`;

  const ov = $("#ov");
  requestAnimationFrame(() => ov.classList.add("show"));
  const close = () => {
    ov.classList.remove("show");
    document.body.style.overflow = "";
    setTimeout(() => root.innerHTML = "", 250);
  };
  ov.onclick = e => { if (e.target === ov) close(); };
  $("#sh-close").onclick = close;

  $$("#sh-status button").forEach(b => b.onclick = () => {
    sheetState.status = b.dataset.v;
    $$("#sh-status button").forEach(x => x.classList.toggle("on", x === b));
  });

  const epInput = $("#sh-ep-input");
  const maxEp = total ? Number(total) : Infinity;
  const updateEp = v => {
    v = parseInt(v, 10);
    if (isNaN(v) || v < 0) v = 0;
    if (v > maxEp) v = maxEp;
    epInput.value = v;
    sheetState.current_episode = v;
    const bar = $(".sheet-ep-bar span");
    if (bar && total) bar.style.width = Math.min(100, (v / total * 100)) + "%";
  };
  $("#sh-ep-minus").onclick = () => updateEp(Number(epInput.value) - 1);
  $("#sh-ep-plus").onclick = () => updateEp(Number(epInput.value) + 1);
  epInput.addEventListener("input", () => updateEp(epInput.value));

  $("#sh-save").onclick = async () => {
    const payload = {
      mal_id: sheetState.mal_id, title: sheetState.title, image_url: sheetState.image_url,
      type: sheetState.type, year: sheetState.year, score: sheetState.score,
      episodes: sheetState.episodes || sheetState.total_episodes || null,
      status: sheetState.status || "plan_to_watch",
      current_episode: Number(epInput.value) || 0,
      notes: $("#sh-notes").value,
    };
    const data = await api("/api/list/save", { method: "POST", body: JSON.stringify(payload) });
    if (data.error) return toast(data.error, "error");
    syncAnimeUI(payload.mal_id, true, data.entry);
    updateStatsStrip();
    close();
    toast(sheetState.in_list ? "Entry updated ✓" : "Added to your list ✓", "success");
    if (document.body.dataset.page === "anime" && data.entry) {
      updateAnimePageEntry(data.entry);
      if (data.suggest_complete) suggestComplete(data.entry.mal_id);
    }
  };

  const del = $("#sh-delete");
  if (del) del.onclick = async () => {
    const ok = await confirmBox("Remove from list?", `"${sheetState.title}" will be removed.`, true);
    if (!ok) return;
    const data = await api("/api/list/delete", { method: "POST", body: JSON.stringify({ mal_id: sheetState.mal_id }) });
    if (data.error) return toast(data.error, "error");
    syncAnimeUI(sheetState.mal_id, false);
    updateStatsStrip();
    close();
    toast("Removed from list", "", () => {
      api("/api/list/save", { method: "POST", body: JSON.stringify({
        mal_id: sheetState.mal_id, title: sheetState.title, image_url: sheetState.image_url,
        type: sheetState.type, year: sheetState.year, score: sheetState.score,
        episodes: sheetState.episodes, status: sheetState.status || "plan_to_watch",
        current_episode: sheetState.current_episode || 0, notes: sheetState.notes || ""
      })}).then(d => { if (d.ok) syncAnimeUI(sheetState.mal_id, true, d.entry); });
    });
  };
}

/* ---------- Suggest complete ---------- */
function suggestComplete(malId) {
  const root = $("#overlay-root");
  if (root.innerHTML.trim()) return;
  showConfetti();
  root.innerHTML = `
    <div class="overlay center" id="ov">
      <div class="dialog-card">
        <h3>🎉 You've finished this anime.</h3>
        <p>Move it to Completed?</p>
        <div class="row">
          <button class="btn" id="sc-keep">Keep Watching</button>
          <button class="btn btn-primary" id="sc-yes">Yes, Completed</button>
        </div>
      </div>
    </div>`;
  const ov = $("#ov");
  requestAnimationFrame(() => ov.classList.add("show"));
  const close = () => { ov.classList.remove("show"); document.body.style.overflow = ""; setTimeout(() => root.innerHTML = "", 200); };
  $("#sc-keep").onclick = close;
  ov.onclick = e => { if (e.target === ov) close(); };
  $("#sc-yes").onclick = async () => {
    const data = await api("/api/list/save", { method: "POST", body: JSON.stringify({ mal_id: malId, status: "completed" }) });
    close();
    if (data.error) return toast(data.error, "error");
    syncAnimeUI(malId, true, data.entry);
    toast("Marked as completed 🎉", "success");
    if (document.body.dataset.page === "anime" && data.entry) updateAnimePageEntry(data.entry);
    updateStatsStrip();
  };
}

/* ---------- Anime page entry sync ---------- */
function updateAnimePageEntry(entry) {
  const labels = {
    watching:"Watching", completed:"Completed",
    plan_to_watch:"Plan to Watch", on_hold:"On Hold", dropped:"Dropped"
  };
  const statusLabel = labels[entry.status] || entry.status;

  const panel = document.getElementById("entry-panel");
  if (panel && panel.style.display === "none") {
    panel.style.display = "";
    panel.classList.add("panel-appear");
  }

  const statusPill = document.getElementById("status-pill");
  if (statusPill) statusPill.textContent = statusLabel;

  const epVal = document.getElementById("ep-val");
  if (epVal && entry.current_episode !== undefined) epVal.textContent = entry.current_episode;

  const bar = document.querySelector(".ani-progress-fill");
  const pctEl = document.querySelector(".ani-progress-pct");
  if (bar && entry.total_episodes) {
    const p = Math.min(100, Math.round((entry.current_episode / entry.total_episodes) * 100));
    bar.style.width = p + "%";
    if (pctEl) pctEl.textContent = p;
  }

  let mainBtn = document.getElementById("edit-full") || document.getElementById("add-main");
  if (mainBtn) {
    if (mainBtn.id === "add-main") {
      mainBtn.id = "edit-full";
      mainBtn.removeAttribute("data-json");
    }
    mainBtn.innerHTML = `✓ ${statusLabel}`;
    mainBtn.onclick = () => {
      const h = document.getElementById("sheet-data-holder");
      if (h) openEntrySheet(JSON.parse(h.dataset.json));
    };
  }

  const rwBtn = document.getElementById("rewatch-btn");
  if (rwBtn) rwBtn.style.display = entry.status === "completed" ? "" : "none";

  const holder = document.getElementById("sheet-data-holder");
  if (holder) {
    try {
      const h = JSON.parse(holder.dataset.json);
      h.in_list = true;
      h.status = entry.status;
      if (entry.current_episode !== undefined) h.current_episode = entry.current_episode;
      if (entry.total_episodes) h.total_episodes = entry.total_episodes;
      if (entry.notes !== undefined) h.notes = entry.notes;
      if (entry.favorite !== undefined) h.favorite = entry.favorite;
      holder.dataset.json = JSON.stringify(h);
    } catch (_) {}
  }
}

/* ---------- Anime page init ---------- */
function initAnimePage() {
  const addMain = $("#add-main");
  if (addMain) addMain.onclick = () => openEntrySheet(JSON.parse(addMain.dataset.json));
  const editFull = $("#edit-full");
  if (editFull) editFull.onclick = () => {
    const h = document.getElementById("sheet-data-holder");
    if (h) openEntrySheet(JSON.parse(h.dataset.json));
  };
  $$("[data-ep-delta]").forEach(btn => btn.onclick = async () => {
    const h = $("#sheet-data-holder");
    if (!h) return;
    const sd = JSON.parse(h.dataset.json);
    const cur = parseInt($("#ep-val")?.textContent || "0", 10);
    const delta = Number(btn.dataset.epDelta);
    if (delta < 0 && cur <= 0) return;
    if (delta > 0 && sd.episodes && cur >= sd.episodes) return;
    const data = await api("/api/list/progress", { method: "POST", body: JSON.stringify({ mal_id: sd.mal_id, delta }) });
    if (data.error) return toast(data.error, "error");
    syncAnimeUI(sd.mal_id, true, data.entry);
    updateAnimePageEntry(data.entry);
    if (data.suggest_complete) suggestComplete(data.entry.mal_id);
  });
  const epVal = $("#ep-val");
  if (epVal) epVal.onclick = () => {
    const h = $("#sheet-data-holder");
    if (!h) return;
    const sd = JSON.parse(h.dataset.json);
    openEpisodeInput(sd.mal_id, parseInt(epVal.textContent, 10) || 0, sd.episodes || 0);
  };
  loadFranchise();
  loadCast();
  loadStaff();
  loadRecommendations();
}

/* ---------- Manual episode input ---------- */
function openEpisodeInput(malId, currentEp, totalEp) {
  const root = $("#overlay-root");
  const hasMax = totalEp && totalEp > 0;
  document.body.style.overflow = "hidden";
  root.innerHTML = `
    <div class="overlay center" id="ov">
      <div class="dialog-card">
        <h3>Set Episode Progress</h3>
        <p>${hasMax ? `Currently ${currentEp} / ${totalEp} episodes` : `${currentEp} episodes watched`}</p>
        <div style="margin:18px 0;">
          <input type="number" id="ep-input" class="ep-input" min="0" ${hasMax ? `max="${totalEp}"` : ""} value="${currentEp}" inputmode="numeric">
        </div>
        <div class="row">
          <button class="btn" id="ep-cancel">Cancel</button>
          <button class="btn btn-primary" id="ep-save">Save</button>
        </div>
      </div>
    </div>`;
  const ov = $("#ov");
  requestAnimationFrame(() => ov.classList.add("show"));
  const close = () => { ov.classList.remove("show"); document.body.style.overflow = ""; setTimeout(() => root.innerHTML = "", 200); };
  $("#ep-cancel").onclick = close;
  ov.onclick = e => { if (e.target === ov) close(); };
  $("#ep-save").onclick = async () => {
    let v = parseInt($("#ep-input").value, 10);
    if (isNaN(v) || v < 0) v = 0;
    if (hasMax && v > totalEp) v = totalEp;
    close();
    const data = await api("/api/list/progress", { method: "POST", body: JSON.stringify({ mal_id: malId, set: v }) });
    if (data.error) return toast(data.error, "error");
    syncAnimeUI(malId, true, data.entry);
    updateAnimePageEntry(data.entry);
    if (data.suggest_complete) suggestComplete(data.entry.mal_id);
    toast(`Episode set to ${v} ✓`, "success");
  };
  setTimeout(() => { const i = $("#ep-input"); if (i) { i.focus(); i.select(); } }, 250);
}

/* ---------- Franchise ---------- */
async function loadFranchise() {
  const wrap = $("#franchise");
  if (!wrap) return;
  const mal = wrap.dataset.mal;
  const data = await api(`/api/anime/${mal}/franchise`);
  if (data.error) {
    wrap.innerHTML = `<p class="muted" style="font-size:12px">Couldn't load franchise data.</p>`;
    return;
  }
  const tl = data.timeline || [];
  if (!tl.length) {
    wrap.innerHTML = `<p class="muted" style="font-size:12px">No related anime found.</p>`;
    return;
  }
  wrap.innerHTML = tl.map((n, i) => {
    const num = String(i + 1).padStart(2, "0");
    const rel = n.current ? "Main series" : (n.relation || "Related");
    const meta = [n.type, n.year].filter(Boolean).join(" · ");
    return `
      <a class="franchise__item${n.current ? " current" : ""}" href="/anime/${n.mal_id}">
        <span class="franchise__marker">${num}</span>
        <span class="franchise__content">
          <span class="franchise__relation">${esc(rel)}</span>
          <span class="franchise__title">${esc(n.title)}</span>
          <span class="franchise__meta">${esc(meta || "—")}</span>
        </span>
        <img class="franchise__thumb" loading="lazy" src="${esc(n.image_url || PLACEHOLDER)}" alt="">
        ${n.in_list
          ? `<span class="franchise__check" title="In your list">✓</span>`
          : `<button class="franchise__add" data-reladd='${esc(JSON.stringify(n))}' title="Add to list">+</button>`}
      </a>`;
  }).join("");
  $$("[data-reladd]", wrap).forEach(b => {
    b.onclick = e => {
      e.preventDefault(); e.stopPropagation();
      const n = JSON.parse(b.dataset.reladd);
      openEntrySheet({ mal_id: n.mal_id, title: n.title, image_url: n.image_url, type: n.type, year: n.year, episodes: n.episodes, in_list: false });
    };
  });
}

/* ---------- Cast ---------- */
let currentVaLang = "jp";
let allCastData = [];

async function loadCast() {
  const wrap = $("#cast-list");
  if (!wrap) return;
  const h = $("#sheet-data-holder");
  if (!h) return;
  const mal = JSON.parse(h.dataset.json).mal_id;
  const data = await api(`/api/anime/${mal}/characters`);
  if (data.error || !data.characters || !data.characters.length) {
    wrap.innerHTML = `<p class="muted" style="font-size:12px">No cast data available.</p>`;
    return;
  }
  allCastData = data.characters;
  let hasJP = false;
  for (const ch of allCastData) for (const va of (ch.voice_actors || [])) {
    if (va.lang === "jp") hasJP = true;
  }
  if (!hasJP) currentVaLang = "en";
  renderCast(allCastData);
}

function renderCast(chars) {
  const wrap = $("#cast-list");
  if (!wrap) return;
  if (!chars.length) { wrap.innerHTML = `<p class="muted" style="font-size:12px">No cast data.</p>`; return; }
  wrap.innerHTML = chars.map(ch => {
    const va = (ch.voice_actors || []).find(v => v.lang === currentVaLang) || (ch.voice_actors || [])[0];
    return `
      <article class="person-card">
        <img class="person-card__image" loading="lazy" src="${esc(ch.image || PLACEHOLDER)}" alt="${esc(ch.name)}">
        <div class="person-card__body">
          <p class="person-card__name">${esc(ch.name)}</p>
          <p class="person-card__role">${esc(ch.role || "Character")}</p>
          ${va ? `<p class="person-card__va">🎙 ${esc(va.name)}</p>` : ""}
        </div>
      </article>`;
  }).join("");
}

/* ---------- Staff ---------- */
async function loadStaff() {
  const wrap = $("#staff-list");
  if (!wrap) return;
  const h = $("#sheet-data-holder");
  if (!h) return;
  const mal = JSON.parse(h.dataset.json).mal_id;
  const data = await api(`/api/anime/${mal}/staff`);
  if (data.error || !data.staff || !data.staff.length) {
    wrap.innerHTML = `<p class="muted" style="font-size:12px">No staff data available.</p>`;
    return;
  }
  wrap.innerHTML = data.staff.map(s => `
    <article class="person-card">
      <img class="person-card__image" loading="lazy" src="${esc(s.image || PLACEHOLDER)}" alt="${esc(s.name)}">
      <div class="person-card__body">
        <p class="person-card__name">${esc(s.name)}</p>
        <p class="person-card__role">${esc(s.role || "Staff")}</p>
      </div>
    </article>`).join("");
}

/* ---------- Recommendations ---------- */
async function loadRecommendations() {
  const list = $("#recommendations-list");
  if (!list) return;
  const h = $("#sheet-data-holder");
  if (!h) return;
  const mal = JSON.parse(h.dataset.json).mal_id;
  const data = await api(`/api/anime/${mal}/recommendations`);
  if (data.error || !data.items || !data.items.length) {
    list.innerHTML = `<p class="muted" style="font-size:12px">No recommendations available.</p>`;
    return;
  }
  list.innerHTML = data.items.map(it => {
    const inList = MYLIST.has(it.mal_id);
    const score = it.score != null ? scoreFmt(it.score) : null;
    return `
      <a class="recommendation-card" href="/anime/${it.mal_id}">
        <img loading="lazy" src="${esc(it.image_url || PLACEHOLDER)}" alt="${esc(it.title)}">
        <div class="recommendation-card__body">
          <p class="recommendation-card__title">${esc(it.title)}</p>
          <div class="recommendation-card__meta">
            ${score ? `<span class="rating">★ ${score}</span>` : ""}
            ${it.type ? `<span>${esc(it.type)}</span>` : ""}
            ${it.year ? `<span>${esc(it.year)}</span>` : ""}
          </div>
        </div>
        <button class="rec-add" data-json='${esc(JSON.stringify(it))}'>${inList ? "✓" : "+"}</button>
      </a>`;
  }).join("");
  $$(".rec-add", list).forEach(b => {
    b.onclick = e => {
      e.preventDefault(); e.stopPropagation();
      openEntrySheet(JSON.parse(b.dataset.json));
    };
  });
}

/* ---------- Quick add / favorites / progress ---------- */
function bindQuickAdds(scope = document) {
  $$(".quickadd", scope).forEach(q => {
    if (q.dataset.bound) return;
    q.dataset.bound = "1";
    const handler = e => {
      e.preventDefault(); e.stopPropagation();
      openEntrySheet(JSON.parse(q.dataset.json));
    };
    q.addEventListener("click", handler);
    q.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") handler(e); });
  });
}

function bindFavorites(scope = document) {
  $$("[data-fav]", scope).forEach(btn => {
    if (btn.dataset.boundFav) return;
    btn.dataset.boundFav = "1";
    btn.onclick = async e => {
      e.preventDefault(); e.stopPropagation();
      const info = JSON.parse(btn.dataset.fav);
      btn.disabled = true;
      const data = await api("/api/list/favorite", { method: "POST", body: JSON.stringify({ mal_id: info.mal_id }) });
      btn.disabled = false;
      if (data.error) return toast(data.error, "error");
      $$("[data-fav]").forEach(b => {
        try {
          const d = JSON.parse(b.dataset.fav);
          if (d.mal_id === info.mal_id) {
            b.classList.toggle("on", data.favorite);
            const p = b.querySelector("svg path");
            if (p) p.setAttribute("fill", data.favorite ? "currentColor" : "none");
          }
        } catch (_) {}
      });
      toast(data.favorite ? "Added to favorites ♥" : "Removed from favorites", "success");
      updateStatsStrip();
    };
  });
}

function bindProgressButtons() {
  $$("[data-progress]").forEach(btn => btn.onclick = async () => {
    const info = JSON.parse(btn.dataset.progress);
    const data = await api("/api/list/progress", { method: "POST", body: JSON.stringify({ mal_id: info.mal_id, delta: 1 }) });
    if (data.error) return toast(data.error, "error");
    toast(`Episode ${data.entry.current_episode} ✓`, "success");
    syncAnimeUI(info.mal_id, true, data.entry);
    if (data.suggest_complete) suggestComplete(info.mal_id);
    else {
      const card = btn.closest(".cw-card");
      if (card) {
        const epEl = $(".cw-ep", card), pb = $(".pbar span", card);
        if (epEl) epEl.textContent = `Episode ${data.entry.current_episode} / ${data.entry.total_episodes || "?"}`;
        if (pb && data.entry.total_episodes) pb.style.width = Math.min(100, data.entry.current_episode / data.entry.total_episodes * 100) + "%";
      }
      updateStatsStrip();
    }
  });
}

/* ---------- Card renderer (search / discover) ---------- */
function renderCards(container, items) {
  const labels = {watching:"Watching",completed:"Completed",plan_to_watch:"Plan to Watch",on_hold:"On Hold",dropped:"Dropped"};
  container.innerHTML = items.map(it => {
    const inList = MYLIST.has(it.mal_id);
    return `
    <div class="card" data-title="${esc((it.title || "").toLowerCase())}">
      <a class="card-link" href="/anime/${it.mal_id}" aria-label="${esc(it.title)}"></a>
      <div class="poster">
        <img loading="lazy" decoding="async" src="${esc(it.image_url || PLACEHOLDER)}" alt="">
        ${inList ? `
        <span class="chip st st-${esc(it.status || "plan_to_watch")}">
          <span class="status-dot ${esc(it.status || "")}"></span>${esc(labels[it.status] || "Plan to Watch")}
        </span>
        <button class="fav-btn${it.favorite ? " on" : ""}" data-fav='${esc(JSON.stringify({ mal_id: it.mal_id }))}'>
          <svg viewBox="0 0 24 24" width="14" height="14">
            <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"
                  fill="${it.favorite ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          </svg>
        </button>` : ""}
        <span class="quickadd" role="button" tabindex="0" data-json='${esc(JSON.stringify(it))}'>${inList ? "✓" : "+"}</span>
      </div>
      <div class="card-body">
        <div class="card-title">${esc(it.title)}</div>
        ${(it.score || it.episodes) ? `
        <div class="card-meta">
          ${it.score ? `<span class="cm-score">★ ${scoreFmt(it.score)}</span>` : ""}
          ${it.score && it.episodes ? `<span>•</span>` : ""}
          ${it.episodes ? `<span class="cm-ep">${it.episodes} ep</span>` : ""}
        </div>` : ""}
      </div>
    </div>`;
  }).join("");
  bindQuickAdds(container);
  bindFavorites(container);
}

/* ---------- Discover ---------- */
function initDiscover() {
  const secs = $$(".discover-sec");
  if (!secs.length) return;
  const load = async sec => {
    if (sec.dataset.done) return;
    sec.dataset.done = "1";
    const box = $("[data-cards]", sec);
    const status = $("[data-role=status]", sec);
    const data = await api(sec.dataset.src);
    if (data.error || !data.items || !data.items.length) {
      box.innerHTML = `<p class="muted" style="padding:14px">Couldn't load. <button class="link-btn" onclick="this.closest('.discover-sec').dataset.done='';window.__loadSec(this)">Retry</button></p>`;
      return;
    }
    data.items.forEach(i => { if (i.in_list) MYLIST.add(i.mal_id); });
    renderCards(box, data.items);
    if (data.sub && status) status.textContent = data.sub;
  };
  window.__loadSec = el => load(el.closest(".discover-sec"));
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(es => es.forEach(en => {
      if (en.isIntersecting) { load(en.target); io.unobserve(en.target); }
    }), { rootMargin: "300px" });
    secs.forEach(s => io.observe(s));
  } else secs.forEach(load);
}

/* ---------- Search ---------- */
function initSearch() {
  const input = $("#q");
  if (!input) return;
  const results = $("#results"), status = $("#search-status"), recentBox = $("#recent-searches");
  const KEY = "anilog.recentSearches";
  const renderRecent = () => {
    let list = [];
    try { list = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (_) {}
    recentBox.innerHTML = list.map(q => `<button class="rchip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
    $$(".rchip", recentBox).forEach(c => c.onclick = () => { input.value = c.dataset.q; run(c.dataset.q); });
  };
  const saveRecent = q => {
    let list = [];
    try { list = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (_) {}
    list = [q, ...list.filter(x => x !== q)].slice(0, 6);
    localStorage.setItem(KEY, JSON.stringify(list));
  };
  let seq = 0;
  async function run(q) {
    q = q.trim();
    if (q.length < 2) { results.innerHTML = ""; status.textContent = ""; return; }
    const my = ++seq;
    status.textContent = "Searching…";
    const data = await api("/api/search?q=" + encodeURIComponent(q));
    if (my !== seq) return;
    if (data.error) { status.textContent = ""; results.innerHTML = ""; toast(data.error, "error"); return; }
    saveRecent(q); renderRecent();
    if (!data.results || !data.results.length) { status.textContent = `No results for "${q}".`; results.innerHTML = ""; return; }
    status.textContent = `${data.results.length} results`;
    data.results.forEach(r => { if (r.in_list) MYLIST.add(r.mal_id); });
    renderCards(results, data.results);
  }
  input.addEventListener("input", debounce(() => run(input.value), 380));
  input.addEventListener("keydown", e => { if (e.key === "Enter") run(input.value); });
  renderRecent();
  if (input.value.trim().length >= 2) run(input.value);
}

/* ---------- List page ---------- */
function initListPage() {
  const grid = $("#list-cards");
  if (!grid) return;
  const g = $("#view-grid"), l = $("#view-list");
  const setView = v => {
    grid.dataset.view = v;
    g.classList.toggle("on", v === "grid");
    l.classList.toggle("on", v === "list");
    localStorage.setItem("anilog.view", v);
  };
  g.onclick = () => setView("grid");
  l.onclick = () => setView("list");

  const url = new URL(location.href);
  const go = () => { location.href = url.pathname + "?" + url.searchParams.toString(); };
  const sortSel = $("#sort-select");
  if (sortSel) sortSel.onchange = () => { url.searchParams.set("sort", sortSel.value); go(); };
  for (const [id, param] of Object.entries({ "f-genre": "genre", "f-year": "year", "f-type": "type", "f-score": "score", "f-prog": "prog" })) {
    const el = document.getElementById(id);
    if (el) el.onchange = () => {
      if (el.value) url.searchParams.set(param, el.value); else url.searchParams.delete(param);
      go();
    };
  }
  const q = $("#list-search"), counter = $("#visible-count");
  if (q) q.addEventListener("input", debounce(() => {
    const needle = q.value.trim().toLowerCase();
    let visible = 0;
    $$(".card", grid).forEach(c => {
      const show = !needle || (c.dataset.title || "").includes(needle);
      c.style.display = show ? "" : "none";
      if (show) visible++;
    });
    if (counter) counter.textContent = visible;
  }, 150));
  bindQuickAdds(grid);
  bindFavorites(grid);
}

/* ---------- Settings ---------- */
function initSettings() {
  if (document.body.dataset.page !== "settings") return;
  $$("[data-setting]").forEach(el => {
    el.addEventListener("change", async () => {
      const value = el.type === "checkbox" ? (el.checked ? "on" : "off") : el.value;
      applyThemePref(el.dataset.setting, value);
      const data = await api("/api/profile/settings", { method: "POST", body: JSON.stringify({ [el.dataset.setting]: value }) });
      if (data.error) return toast(data.error, "error");
      toast("Setting saved ✓", "success");
    });
  });
  const btnCache = $("#btn-clear-cache");
  if (btnCache) btnCache.onclick = async () => {
    const ok = await confirmBox("Clear cached API data?", "Your list is untouched.");
    if (!ok) return;
    await api("/api/cache/clear", { method: "POST" });
    toast("Cache cleared ✓", "success");
  };
}

/* ---------- Comments (with likes + sort) ---------- */
function initComments() {
  const section = document.getElementById("comments-section");
  if (!section) return;
  const h = document.getElementById("sheet-data-holder");
  if (!h) return;
  const malId = JSON.parse(h.dataset.json).mal_id;
  const list = document.getElementById("comments-list");
  const count = document.getElementById("comment-count");
  const form = document.getElementById("comment-form");
  let all = [];
  let sortMode = "new";

  function render() {
    const cs = sortMode === "top" ? [...all].sort((a, b) => (b.likes || 0) - (a.likes || 0)) : all;
    count.textContent = cs.length ? `${cs.length}` : "0";
    if (!cs.length) { list.innerHTML = `<p class="muted">No comments yet. Be the first!</p>`; return; }
    list.innerHTML = cs.map(c => {
      const initial = (c.display_name || c.username || "?")[0].toUpperCase();
      return `
        <article class="comment">
          <a href="/user/${esc(c.username)}" class="avatar">${esc(initial)}</a>
          <div>
            <div class="comment__head">
              <a href="/user/${esc(c.username)}" class="comment__name">${esc(c.display_name || c.username)}</a>
              <time class="comment__time">${formatTime(c.created_at)}</time>
            </div>
            <p class="comment__body">${esc(c.text)}</p>
            <div class="comment__actions">
              <button class="comment__action like${c.liked ? " liked" : ""}" data-id="${c.id}">♥ <span>${c.likes || 0}</span></button>
              ${c.can_delete ? `<button class="comment__action danger" data-del="${c.id}">Delete</button>` : ""}
            </div>
          </div>
        </article>`;
    }).join("");
    list.querySelectorAll(".comment__action.like").forEach(btn => btn.onclick = async () => {
      const res = await api(`/api/comments/${btn.dataset.id}/like`, { method: "POST" });
      if (res.ok) {
        const c = all.find(x => x.id == btn.dataset.id);
        if (c) { c.liked = res.liked; c.likes = res.likes; render(); }
      } else toast(res.error || "Failed", "error");
    });
    list.querySelectorAll("[data-del]").forEach(btn => btn.onclick = async () => {
      const ok = await confirmBox("Delete comment?", "This cannot be undone.", true);
      if (!ok) return;
      const res = await api(`/api/comments/${btn.dataset.del}`, { method: "DELETE" });
      if (res.ok) { toast("Comment deleted", "success"); load(); }
      else toast(res.error || "Failed", "error");
    });
  }

  async function load() {
    const data = await api(`/api/anime/${malId}/comments`);
    if (data.error) { list.innerHTML = `<p class="muted">Failed to load.</p>`; return; }
    all = data.comments || [];
    render();
  }

  $$("[data-csort]").forEach(btn => btn.onclick = () => {
    sortMode = btn.dataset.csort;
    $$("[data-csort]").forEach(b => b.classList.toggle("active", b === btn));
    render();
  });

  if (form) form.onsubmit = async e => {
    e.preventDefault();
    const input = document.getElementById("comment-input");
    const text = input.value.trim();
    if (!text) return toast("Comment cannot be empty", "error");
    const res = await api(`/api/anime/${malId}/comments`, { method: "POST", body: JSON.stringify({ text }) });
    if (res.ok) { toast("Comment posted ✓", "success"); input.value = ""; load(); }
    else toast(res.error || "Failed", "error");
  };

  load();
}

/* ---------- Keyboard shortcuts ---------- */
function initKeyboardShortcuts() {
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); location.href = "/search"; }
  });
}

/* ---------- User dropdown menu ---------- */
function initUserMenu() {
  const closeAll = () => {
    $$(".user-menu").forEach(m => { m.hidden = true; });
    $$(".profile-btn").forEach(b => b.classList.remove("open"));
  };

  $$(".user-menu-wrap").forEach(wrap => {
    const btn = wrap.querySelector(".profile-btn");
    const menu = wrap.querySelector(".user-menu");
    if (!btn || !menu) return;

    btn.addEventListener("click", e => {
      e.stopPropagation();
      const willOpen = menu.hidden;
      closeAll();
      menu.hidden = !willOpen;
      btn.classList.toggle("open", willOpen);
    });

    menu.addEventListener("click", e => e.stopPropagation());
  });

  document.addEventListener("click", closeAll);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeAll(); });
}

/* ---------- Live user identity sync (no refresh needed) ---------- */
function refreshUserUI() {
  const u = window.CURRENT_USER;
  if (!u) return;
  const name = u.display_name || u.username;
  const initial = (name[0] || "?").toUpperCase();
  $$(".avatar-sm").forEach(a => { a.textContent = initial; });
  $$(".user-menu__head b").forEach(b => b.textContent = name);
  $$(".user-menu__head small").forEach(s => s.textContent = "@" + u.username);
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set("current-username", "@" + u.username);

  /* Only update the profile card when it's YOUR OWN profile card */
  if (document.querySelector(".pcard[data-own='1']")) {
    set("pcard-name", name);
    set("pcard-handle", "@" + u.username);
    set("pcard-avatar", initial);
    const vb = document.getElementById("verified-badge");
    if (vb) vb.hidden = !u.email_verified;
    const ab = document.getElementById("admin-badge");
    if (ab) ab.hidden = !u.is_admin;
  }
  const pub = document.getElementById("public-page-link");
  if (pub) pub.href = "/user/" + encodeURIComponent(u.username);
}

/* ---------- Boot ---------- */
document.addEventListener("DOMContentLoaded", () => {
  bindQuickAdds();
  bindFavorites();
  bindProgressButtons();
  initDiscover();
  initSearch();
  initListPage();
  initSettings();
  initComments();
  initKeyboardShortcuts();
  initUserMenu();
  refreshUserUI();
  tickCountdowns();
  const content = document.querySelector(".content");
  if (content) content.classList.add("page-transition");
  if (document.body.dataset.page === "anime") initAnimePage();
});