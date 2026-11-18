/* Mini App: ustoz va nazoratchi uchun. Ramkasiz (vanilla JS), hash-marshrutlash. */
(() => {
  "use strict";
  const tg = window.Telegram && window.Telegram.WebApp;
  const $app = document.getElementById("app");
  const OPTS = ["A", "B", "C", "D"];
  let ME = null;
  let HOME = null;          // ustoz bosh sahifa ma'lumoti (guruhlar ro'yxati uchun ham)
  let timers = [];

  // ---------- yordamchilar ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* xotira yo'q */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* */ } },
  };
  const haptic = (t) => { try { tg && tg.HapticFeedback && (t === "ok" || t === "err" ? tg.HapticFeedback.notificationOccurred(t === "ok" ? "success" : "error") : tg.HapticFeedback.selectionChanged()); } catch { /* */ } };

  function toast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg; el.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove("show"), 2400);
  }

  function confirmBox(msg) {
    return new Promise((res) => {
      if (tg && tg.showConfirm && tg.initData) tg.showConfirm(msg, (ok) => res(!!ok));
      else res(window.confirm(msg));
    });
  }

  async function api(path, opts = {}) {
    const r = await fetch(path, {
      ...opts,
      headers: {
        ...(opts.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        "X-Telegram-Init-Data": (tg && tg.initData) || "",
      },
    });
    let data = {};
    try { data = await r.json(); } catch { /* bo'sh javob */ }
    if (!r.ok) { const e = new Error(data.message || "Xatolik yuz berdi"); e.code = data.error; e.status = r.status; throw e; }
    return data;
  }

  const TZ = "Asia/Tashkent";
  function fmtDate(iso) {
    if (!iso) return "—";
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
    return `${p.day}.${p.month} ${p.hour}:${p.minute}`;
  }
  function left(iso) {
    let m = Math.max(0, Math.floor((new Date(iso) - Date.now()) / 60000));
    const d = Math.floor(m / 1440); m -= d * 1440; const h = Math.floor(m / 60); m -= h * 60;
    if (d) return h ? `${d} kun ${h} soat` : `${d} kun`;
    if (h) return m ? `${h} soat ${m} daq` : `${h} soat`;
    return `${m} daqiqa`;
  }
  const hoursLeft = (iso) => (new Date(iso) - Date.now()) / 3600000;
  const coinsHtml = (c) => `<span class="coins ${c < 0 ? "neg" : ""}"><span class="coin"></span>${c}</span>`;
  const deadlineChip = (iso) => {
    const h = hoursLeft(iso);
    const cls = h <= 3 ? "bad" : h <= 24 ? "accent" : "brand";
    return `<span class="chip ${cls}">⏱ ${left(iso)}</span>`;
  };

  function setTheme() {
    const dark = tg && tg.colorScheme ? tg.colorScheme === "dark"
      : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--page").trim();
    try { tg && tg.setHeaderColor && tg.setHeaderColor(bg); tg && tg.setBackgroundColor && tg.setBackgroundColor(bg); } catch { /* eski versiya */ }
  }

  function go(hash) { location.hash = hash; }
  function clearTimers() { timers.forEach(clearInterval); timers = []; }
  function render(html) { $app.innerHTML = html; window.scrollTo(0, 0); }
  function loading() { render(`<div class="loader"><span></span></div>`); }
  function stateView(icon, title, text, btn) {
    render(`<div class="state"><div class="ic">${icon}</div><h2>${esc(title)}</h2><p>${esc(text)}</p>${btn || ""}</div>`);
  }
  function showError(e) {
    if (e.status === 401) return stateView("📱", "Telegram orqali oching", "Bu ilova faqat bot ichida ishlaydi.");
    if (e.code === "not_registered") return stateView("👋", "Avval ro'yxatdan o'ting",
      "Botga qaytib /start ni bosing va telefon raqamingizni yuboring.",
      `<button class="btn" onclick="Telegram.WebApp.close()">Botga qaytish</button>`);
    stateView("⚠️", "Xatolik", e.message || "Qaytadan urinib ko'ring.",
      `<button class="btn ghost" onclick="location.reload()">Qayta yuklash</button>`);
  }

  // ---------- marshrutlash ----------
  const routes = [
    [/^$/, () => (ME.role === "ustoz" ? ustozHome() : adminHome())],
    [/^test\/(\d+)$/, (id) => testPage(+id)],
    [/^rating\/(\d+)$/, (id) => ratingPage(+id, "all")],
    [/^g\/(\d+)$/, (id) => adminGroup(+id)],
    [/^t\/(\d+)$/, (id) => adminTest(+id)],
    [/^new\/(\d+)$/, (id) => newTest(+id)],
    [/^key\/(\d+)$/, (id) => editKey(+id)],
    [/^m\/(\d+)$/, (id) => membersPage(+id)],
    [/^ga\/(\d+)$/, (id) => groupAdmins(+id)],
    [/^newgroup$/, () => newGroup()],
    [/^staff$/, () => staffPage()],
    [/^appeals$/, () => appealsPage()],
  ];

  async function router() {
    clearTimers();
    const path = location.hash.replace(/^#\/?/, "");
    if (tg && tg.BackButton) { path ? tg.BackButton.show() : tg.BackButton.hide(); }
    for (const [re, fn] of routes) {
      const m = path.match(re);
      if (m) {
        loading();
        try { await fn(...m.slice(1)); } catch (e) { showError(e); }
        return;
      }
    }
    go("/");
  }

  // ================= USTOZ =================
  async function ustozHome() {
    HOME = await api("/api/home");
    const first = (ME.name || "").split(" ").slice(-1)[0] || ME.name;
    const sel = store.get("group") ?? (HOME.groups[0] && HOME.groups[0].id);
    const g = HOME.groups.find((x) => x.id === sel) || HOME.groups[0];

    let hero = `<div class="hero"><div class="hi">Assalomu alaykum,</div><div class="name">${esc(first)} 👋</div>`;
    if (g) {
      hero += `<div class="hero-stats">
        <div class="hs"><div class="v"><span class="coin"></span>${g.coins}</div><div class="k">tanga</div></div>
        <div class="hs"><div class="v">${g.place ?? "—"}<small style="font-size:14px;opacity:.7;font-weight:600">/${g.total}</small></div><div class="k">o'rin</div></div>
        <div class="hs"><div class="v">${g.week_coins > 0 ? "+" : ""}${g.week_coins}</div><div class="k">shu hafta</div></div>
      </div>`;
      if (HOME.groups.length > 1) {
        hero += `<div class="groups-scroll">${HOME.groups.map((x) =>
          `<button data-g="${x.id}" class="${x.id === g.id ? "on" : ""}">${esc(x.name)}</button>`).join("")}</div>`;
      }
    } else {
      hero += `<div class="hero-stats"><div class="hs"><div class="k">Hali guruhga qo'shilmagansiz. Botda «➕ Guruhga qo'shilish» ni bosing.</div></div></div>`;
    }
    hero += `</div>`;

    const active = HOME.active.length ? HOME.active.map((t) => `
      <div class="card tcard">
        <div class="top"><div><div class="title">${esc(t.title)}</div>
          <div class="meta">${esc(t.group)} · ${t.n} ta savol · ${fmtDate(t.deadline_at)} gacha</div></div>
          ${t.correct === null ? deadlineChip(t.deadline_at) : `<span class="chip ok">✓ ${t.correct}/${t.n}</span>`}
        </div>
        <div class="actions">${t.correct === null
          ? `<button class="btn block" data-go="/test/${t.id}">Javob belgilash</button>`
          : `<button class="btn ghost block" data-go="/test/${t.id}">Javoblarimni ko'rish</button>`}</div>
      </div>`).join("") : `<div class="card empty">Hozir faol test yo'q.<br>Yangi test chiqqanda bot xabar beradi 🔔</div>`;

    const recent = HOME.recent.length ? `<div class="list">${HOME.recent.map((t) => `
      <button class="row" data-go="/test/${t.id}">
        <div class="grow"><div class="t">${esc(t.title)}</div><div class="s">${esc(t.group)} · ${fmtDate(t.closed_at)}</div></div>
        ${t.correct === null ? `<span class="chip bad">−${HOME.rules.penalty}</span>`
          : `<span class="chip ${t.correct === t.n ? "ok" : "muted"}">${t.correct}/${t.n}</span>`}
        <span class="chev">›</span></button>`).join("")}</div>` : `<div class="card empty">Natijalar shu yerda chiqadi.</div>`;

    render(`${hero}
      <div class="section"><div class="label">Faol testlar</div>${active}</div>
      ${g ? `<div class="section"><button class="btn ghost block" data-go="/rating/${g.id}">🏆 Reytingni ko'rish</button></div>` : ""}
      <div class="section"><div class="label">Natijalarim</div>${recent}</div>
      <p class="note">Har bir to'g'ri javob: +${HOME.rules.per_correct} tanga · Topshirmaslik: −${HOME.rules.penalty} tanga</p>`);

    $app.querySelectorAll("[data-g]").forEach((b) => b.onclick = () => { store.set("group", +b.dataset.g); haptic(); ustozHome(); });
  }

  // ---------- test sahifasi ----------
  async function testPage(id) {
    const t = await api(`/api/tests/${id}`);
    if (!t.submission && t.status === "published" && ME.role !== "ustoz") return go(`/t/${id}`);
    if (t.status === "published" && !t.submission && new Date(t.deadline_at) > Date.now()) return answerSheet(t);
    return resultView(t);
  }

  function answerSheet(t) {
    const key = `draft:${t.id}`;
    const ans = (store.get(key) || "").padEnd(t.n, "-").slice(0, t.n).split("");
    const rows = Array.from({ length: t.n }, (_, i) => `
      <div class="q" data-q="${i}"><div class="num">${i + 1}</div><div class="opts">
        ${OPTS.map((o) => `<button class="b ${ans[i] === o ? "on" : ""}" data-o="${o}" aria-label="${i + 1}-savol ${o}">${o}</button>`).join("")}
      </div></div>`).join("");
    render(`
      <div class="card tcard"><div class="top"><div><div class="title">${esc(t.title)}</div>
        <div class="meta">${esc(t.group)} · ${t.n} ta savol</div></div><span id="dl">${deadlineChip(t.deadline_at)}</span></div>
        <div class="note" style="text-align:left">Har savol uchun bitta javobni belgilang. Qayta bossangiz, belgi olib tashlanadi. Yuborgandan keyin o'zgartirib bo'lmaydi.</div>
      </div>
      <div class="section"><div class="sheet">${rows}</div></div>
      <div class="bar-bottom"><div class="inner"><div class="cnt">Belgilandi<br><b id="cnt">0</b> / ${t.n}</div>
        <button class="btn" id="send" style="min-width:150px">Yuborish</button></div></div>`);

    const cnt = document.getElementById("cnt");
    const upd = () => { cnt.textContent = ans.filter((a) => a !== "-").length; };
    upd();
    $app.querySelectorAll(".q").forEach((row) => {
      const i = +row.dataset.q;
      row.querySelectorAll(".b").forEach((b) => b.onclick = () => {
        ans[i] = ans[i] === b.dataset.o ? "-" : b.dataset.o;
        row.querySelectorAll(".b").forEach((x) => x.classList.toggle("on", x.dataset.o === ans[i]));
        store.set(key, ans.join("")); upd(); haptic();
      });
    });
    timers.push(setInterval(() => {
      const el = document.getElementById("dl"); if (el) el.innerHTML = deadlineChip(t.deadline_at);
      if (new Date(t.deadline_at) <= Date.now()) { clearTimers(); toast("Muddat tugadi"); router(); }
    }, 30000));

    document.getElementById("send").onclick = async () => {
      const blanks = ans.map((a, i) => (a === "-" ? i + 1 : null)).filter(Boolean);
      const msg = blanks.length
        ? `${blanks.length} ta savol javobsiz qoldi (${blanks.slice(0, 10).join(", ")}${blanks.length > 10 ? "…" : ""}). Baribir yuborasizmi? Keyin o'zgartirib bo'lmaydi.`
        : "Javoblarni yuborasizmi? Keyin o'zgartirib bo'lmaydi.";
      if (!(await confirmBox(msg))) return;
      const btn = document.getElementById("send"); btn.disabled = true; btn.textContent = "Yuborilmoqda…";
      try {
        const r = await api(`/api/tests/${t.id}/submit`, { method: "POST", body: JSON.stringify({ answers: ans.join("") }) });
        store.del(key); haptic("ok");
        render(`<div class="card result-hero">
          <div class="h-sub">${esc(t.title)}</div>
          <div class="score-big" style="margin-top:10px">${r.correct}<small>/${r.n}</small></div>
          <div class="coins-earned"><span class="chip accent"><span class="coin"></span>+${r.coins} tanga</span></div>
          <p class="note">Qaysi savollarda xato qilganingiz va to'g'ri javoblar muddat tugagach ko'rsatiladi.</p>
        </div>
        <div class="section"><button class="btn block" data-go="/">Bosh sahifa</button></div>`);
      } catch (e) {
        haptic("err"); btn.disabled = false; btn.textContent = "Yuborish"; toast(e.message);
        if (e.code === "already" || e.code === "not_active") setTimeout(router, 1200);
      }
    };
  }

  function resultView(t) {
    const sub = t.submission;
    const closed = t.status === "closed";
    let head = `<div class="card result-hero"><div class="h-sub">${esc(t.title)} · ${esc(t.group)}</div>`;
    if (sub) {
      head += `<div class="score-big" style="margin-top:10px">${sub.correct}<small>/${t.n}</small></div>
        <div class="progress" style="margin:16px auto 0;max-width:260px"><i style="width:${(100 * sub.correct / t.n).toFixed(1)}%"></i></div>`;
      head += closed ? `<p class="note">${t.mistakes.length ? `${t.mistakes.length} ta xato` : "Barcha javoblar to'g'ri! 🎉"}</p>`
        : `<p class="note">Muddat: ${fmtDate(t.deadline_at)}. To'g'ri javoblar shundan keyin ochiladi.</p>`;
    } else {
      head += `<div style="margin-top:14px"><span class="chip bad">Topshirilmagan</span></div>`;
    }
    head += `</div>`;

    let body = "";
    if (closed || sub) {
      const onlyWrong = store.get("onlyWrong") && closed && sub;
      const rows = Array.from({ length: t.n }, (_, i) => {
        const mine = sub ? sub.answers[i] : "-";
        const right = closed ? t.key[i] : null;
        if (onlyWrong && mine === right) return "";
        const miss = closed && mine !== right;
        return `<div class="q ${miss ? "miss" : ""}"><div class="num">${i + 1}</div><div class="opts">${OPTS.map((o) => {
          let c = "";
          if (closed && o === right) c = mine === o ? "right on" : "right";
          else if (o === mine) c = closed ? "wrong" : "on";
          return `<span class="b ${c}">${o}</span>`;
        }).join("")}</div><div class="mark">${closed ? (miss ? "✕" : "✓") : ""}</div></div>`;
      }).join("");
      const legend = closed ? `<div class="legend"><span><i style="background:var(--success)"></i>to'g'ri belgilagansiz</span>
        <span><i style="border-color:var(--success);background:var(--success-soft)"></i>to'g'ri javob</span>
        <span><i style="background:var(--danger)"></i>xato javobingiz</span></div>` : "";
      const toggle = closed && sub && t.mistakes.length ? `<div class="seg" style="margin-bottom:12px">
        <button data-w="0" class="${onlyWrong ? "" : "on"}">Hammasi</button><button data-w="1" class="${onlyWrong ? "on" : ""}">Faqat xatolar</button></div>` : "";
      body = `<div class="section"><div class="label">${closed ? "Javoblar" : "Sizning javoblaringiz"}</div>${toggle}${legend}<div class="sheet">${rows}</div></div>`;
    }
    render(head + body + `<div class="section"><button class="btn ghost block" data-go="/">Bosh sahifa</button></div>`);
    $app.querySelectorAll("[data-w]").forEach((b) => b.onclick = () => { store.set("onlyWrong", b.dataset.w === "1"); resultView(t); });
  }

  // ---------- reyting ----------
  async function ratingPage(gid, period) {
    const r = await api(`/api/groups/${gid}/rating?period=${period}`);
    const tabs = [["all", "Umumiy"], ["week", "Shu hafta"], ["lastweek", "O'tgan hafta"]];
    const rows = r.rows.length ? `<div class="list">${r.rows.map((x) => `
      <div class="row ${x.me ? "me" : ""}"><div class="place ${x.place <= 3 ? "p" + x.place : ""}">${x.place}</div>
        <div class="grow"><div class="t">${esc(x.name)}${x.me ? " (siz)" : ""}</div></div>${coinsHtml(x.coins)}</div>`).join("")}</div>`
      : `<div class="card empty">Hali ma'lumot yo'q.</div>`;
    let me = "";
    if (r.me) {
      const idx = r.rows.findIndex((x) => x.me);
      if (idx >= 8) {
        const top10 = r.rows[Math.min(9, r.rows.length - 1)];
        const need = r.me.place > 10 ? top10.coins - r.me.coins + 1 : 0;
        me = `<div class="me-bar"><div class="list"><div class="row me"><div class="place">${r.me.place}</div>
          <div class="grow"><div class="t">Siz</div>${need > 0 ? `<div class="s">TOP-10 ga ${need} tanga qoldi 💪</div>` : ""}</div>
          ${coinsHtml(r.me.coins)}</div></div></div>`;
      }
    }
    render(`<div class="h-title">🏆 ${esc(r.group.name)}</div><div class="h-sub">Reyting · teng tangalilar bir o'rinda</div>
      <div class="section" style="margin-top:14px"><div class="seg">${tabs.map(([k, l]) =>
        `<button data-p="${k}" class="${k === period ? "on" : ""}">${l}</button>`).join("")}</div></div>
      <div class="section" style="margin-top:14px">${rows}</div>${me}`);
    $app.querySelectorAll("[data-p]").forEach((b) => b.onclick = () => { haptic(); ratingPage(gid, b.dataset.p).catch(showError); });
  }

  // ================= NAZORATCHI =================
  const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data || {}) });
  const del = (path) => api(path, { method: "DELETE" });
  const STATUS = { draft: ["muted", "Qoralama"], queued: ["accent", "Navbatda"], published: ["brand", "Faol"], closed: ["ok", "Yakunlangan"] };
  const DURATIONS = [[12, "12 soat"], [24, "1 kun"], [48, "2 kun"], [72, "3 kun"], [168, "1 hafta"]];
  const abtn = (icon, label, attrs, extra = "") => `<button class="abtn ${extra}" ${attrs}><span class="ai">${icon}</span>${label}</button>`;

  // kalitni matndan o'qish: "abcd", "1a 2b", kirill harflari ham
  function parseKeyText(text) {
    const map = { "а": "a", "б": "b", "в": "b", "с": "c", "ц": "c", "д": "d" };
    const s = String(text || "").toLowerCase().replace(/[абвсцд]/g, (c) => map[c]);
    if (/\d/.test(s)) {
      const out = {}; let max = 0; const re = /(\d+)\s*[-.):=]?\s*([a-d])/g; let m;
      while ((m = re.exec(s))) { out[+m[1]] = m[2].toUpperCase(); max = Math.max(max, +m[1]); }
      return Array.from({ length: max }, (_, i) => out[i + 1] || "-");
    }
    return s.replace(/[^a-d]/g, "").toUpperCase().split("");
  }

  // kalit muharriri: har savol uchun A/B/C/D
  function keyRows(key) {
    return key.map((k, i) => `<div class="q" data-q="${i}"><div class="num">${i + 1}</div><div class="opts">
      ${OPTS.map((o) => `<button class="b ${k === o ? "on" : ""}" data-o="${o}">${o}</button>`).join("")}</div></div>`).join("");
  }
  function bindKey(root, key, onChange) {
    root.querySelectorAll(".q").forEach((row) => {
      const i = +row.dataset.q;
      row.querySelectorAll(".b").forEach((b) => b.onclick = () => {
        key[i] = b.dataset.o;
        row.querySelectorAll(".b").forEach((x) => x.classList.toggle("on", x.dataset.o === key[i]));
        haptic(); onChange && onChange();
      });
    });
  }
  const keyPreview = (key) => `<div class="keyprev">${key.split("").map((k, i) => `<span>${i + 1}-<b>${k}</b></span>`).join("")}</div>`;

  async function adminHome() {
    const { groups, appeals_open } = await api("/api/admin/groups");
    const sup = ME.role === "super";
    const list = groups.length ? groups.map((g) => {
      const a = g.active;
      const pct = a && g.members ? Math.round(100 * a.submitted / g.members) : 0;
      return `<button class="card tcard" style="display:block;width:100%;text-align:left" data-go="/g/${g.id}">
        <div class="top"><div><div class="title">${esc(g.name)}</div>
          <div class="meta">${g.members} ta ustoz · kod <span class="code">${esc(g.code)}</span></div></div><span class="chev">›</span></div>
        ${a ? `<div style="margin-top:14px"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px;margin-bottom:6px">
            <b>${esc(a.title)}</b><span class="h-sub" style="white-space:nowrap">${a.submitted}/${g.members} topshirdi</span></div>
            <div class="progress"><i style="width:${pct}%"></i></div>
            <div class="meta" style="margin-top:6px">Muddat: ${fmtDate(a.deadline_at)} · ${left(a.deadline_at)} qoldi</div></div>`
          : `<div class="meta" style="margin-top:10px">Faol test yo'q</div>`}
      </button>`;
    }).join("") : `<div class="card empty">${sup ? "Hali guruh yo'q — «Yangi guruh» ni bosing." : "Sizga hali guruh tayinlanmagan."}</div>`;
    render(`<div class="hero"><div class="hi">${sup ? "Bosh admin" : "Nazoratchi"}</div><div class="name">${esc(ME.name)}</div>
        <div class="hero-stats"><div class="hs"><div class="v">${groups.length}</div><div class="k">guruh</div></div>
        <div class="hs"><div class="v">${groups.reduce((s, g) => s + g.members, 0)}</div><div class="k">ustoz</div></div>
        <div class="hs"><div class="v">${groups.filter((g) => g.active).length}</div><div class="k">faol test</div></div></div></div>
      <div class="section"><div class="agrid">
        ${abtn("📨", "E'tirozlar" + (appeals_open ? `<span class="badge">${appeals_open}</span>` : ""), `data-go="/appeals"`)}
        ${sup ? abtn("➕", "Yangi guruh", `data-go="/newgroup"`) : ""}
        ${sup ? abtn("👮", "Nazoratchilar", `data-go="/staff"`) : ""}
      </div></div>
      <div class="section"><div class="label">Guruhlar</div>${list}</div>`);
  }

  async function newGroup() {
    render(`<div class="h-title">Yangi guruh</div><div class="h-sub">Kod avtomatik yaratiladi</div>
      <div class="section"><label class="field"><span>Guruh nomi</span><input class="input" id="gname" maxlength="64" placeholder="Masalan: Attestatsiya 3-guruh"></label>
      <button class="btn block" id="save">Yaratish</button></div>`);
    document.getElementById("save").onclick = async () => {
      try {
        const r = await post("/api/admin/groups", { name: document.getElementById("gname").value });
        haptic("ok"); toast("Guruh yaratildi. Endi nazoratchi tayinlang."); go(`/ga/${r.id}`);
      } catch (e) { haptic("err"); toast(e.message); }
    };
  }

  async function adminGroup(id) {
    const d = await api(`/api/admin/groups/${id}`);
    const g = d.group;
    const sup = ME.role === "super";
    const tests = d.tests.length ? `<div class="list">${d.tests.map((t) => {
      const [cls, label] = STATUS[t.status];
      const live = t.status === "published" || t.status === "closed";
      const meta = live ? `${t.submitted}/${g.members} topshirdi${t.avg_pct !== null ? ` · o'rtacha ${t.avg_pct}%` : ""}` : `${t.n} ta savol`;
      return `<button class="row" data-go="/t/${t.id}"><div class="grow"><div class="t">${esc(t.title)}</div><div class="s">${meta}</div></div>
        <span class="chip ${cls}">${label}</span><span class="chev">›</span></button>`;
    }).join("")}</div>` : `<div class="card empty">Hali test yo'q. «Yangi test» ni bosing.</div>`;
    const risk = d.at_risk.length ? `<div class="section"><div class="warn">⚠️ Ketma-ket 2 ta testni topshirmaganlar: ${d.at_risk.map(esc).join(", ")}</div></div>` : "";
    render(`<div class="h-title" id="gtitle">${esc(g.name)}</div>
      <div class="h-sub">Kod: <span class="code" id="gcode">${esc(g.code)}</span> · ${g.members} ta ustoz</div>
      <div class="h-sub" style="margin-top:2px">Nazoratchilar: ${d.admins.length ? d.admins.map(esc).join(", ") : "tayinlanmagan"}</div>
      ${risk}
      <div class="section"><div class="agrid">
        ${abtn("➕", "Yangi test", `data-go="/new/${g.id}"`)}
        ${abtn("👥", "Ustozlar", `data-go="/m/${g.id}"`)}
        ${abtn("🏆", "Reyting", `data-go="/rating/${g.id}"`)}
        ${abtn("📥", "Excel", `id="excel"`)}
        ${abtn("🔄", "Yangi kod", `id="code"`)}
        ${sup ? abtn("👮", "Nazoratchilar", `data-go="/ga/${g.id}"`) : ""}
        ${sup ? abtn("✏️", "Nomini o'zgartirish", `id="rename"`) : ""}
        ${sup ? abtn("🗑", "O'chirish", `id="gdel"`, "danger") : ""}
      </div><div id="renameBox"></div></div>
      <div class="section"><div class="label">Testlar</div>${tests}</div>`);

    document.getElementById("excel").onclick = async () => {
      try { await post(`/api/admin/groups/${g.id}/excel`); haptic("ok"); toast("📥 Excel fayl botga yuborildi"); }
      catch (e) { toast(e.message); }
    };
    document.getElementById("code").onclick = async () => {
      if (!(await confirmBox("Yangi kod yaratilsinmi? Eski kod ishlamay qoladi."))) return;
      try { const r = await post(`/api/admin/groups/${g.id}/code`); document.getElementById("gcode").textContent = r.code; haptic("ok"); toast("Yangi kod: " + r.code); }
      catch (e) { toast(e.message); }
    };
    if (sup) {
      document.getElementById("rename").onclick = () => {
        const box = document.getElementById("renameBox");
        box.innerHTML = `<div class="card" style="margin-top:10px"><label class="field"><span>Yangi nom</span>
          <input class="input" id="newname" maxlength="64" value="${esc(g.name)}"></label><button class="btn block" id="saveName">Saqlash</button></div>`;
        document.getElementById("saveName").onclick = async () => {
          try { await api(`/api/admin/groups/${g.id}`, { method: "PATCH", body: JSON.stringify({ name: document.getElementById("newname").value }) });
            haptic("ok"); toast("Saqlandi"); adminGroup(g.id); } catch (e) { toast(e.message); }
        };
      };
      document.getElementById("gdel").onclick = async () => {
        if (!(await confirmBox(`«${g.name}» guruhini o'chirasizmi? Testlar, natijalar va tangalar ham butunlay o'chadi.`))) return;
        if (!(await confirmBox("Aniqmi? Buni qaytarib bo'lmaydi. Avval Excel'ni yuklab olishni maslahat beramiz."))) return;
        try { await del(`/api/admin/groups/${g.id}`); toast("Guruh o'chirildi"); go("/"); } catch (e) { toast(e.message); }
      };
    }
  }

  async function groupAdmins(id) {
    const { admins } = await api(`/api/admin/groups/${id}/admins`);
    const rows = admins.length ? `<div class="list">${admins.map((a) => `
      <button class="row" data-a="${a.id}"><div class="grow"><div class="t">${esc(a.name)}</div></div>
        <span class="switch ${a.assigned ? "on" : ""}"></span></button>`).join("")}</div>`
      : `<div class="card empty">Hali nazoratchi yo'q.<br><br><button class="btn ghost" data-go="/staff">Nazoratchi qo'shish</button></div>`;
    render(`<div class="h-title">Nazoratchi tayinlash</div><div class="h-sub">Bir nechtasini tanlash mumkin</div>
      <div class="section">${rows}</div><div class="section"><button class="btn ghost block" data-go="/g/${id}">Guruhga qaytish</button></div>`);
    $app.querySelectorAll("[data-a]").forEach((b) => b.onclick = async () => {
      const sw = b.querySelector(".switch"); const on = !sw.classList.contains("on");
      try { await post(`/api/admin/groups/${id}/admins/${b.dataset.a}`, { assigned: on }); sw.classList.toggle("on", on); haptic(); }
      catch (e) { toast(e.message); }
    });
  }

  async function staffPage() {
    const { staff } = await api("/api/admin/staff");
    const rows = staff.length ? `<div class="list">${staff.map((s) => `
      <div class="row"><div class="grow"><div class="t">${esc(s.full_name)}</div>
        <div class="s">${esc(s.phone)} · ${s.groups} guruh · ${s.tests_created} test · e'tiroz: ${s.appeals_resolved} ko'rildi${s.appeals_open ? `, <b style="color:var(--danger)">${s.appeals_open} ochiq</b>` : ""}</div></div>
        <button class="chip bad" data-rm="${s.id}" data-n="${esc(s.full_name)}">Olish</button></div>`).join("")}</div>`
      : `<div class="card empty">Hali nazoratchi yo'q.</div>`;
    render(`<div class="h-title">👮 Nazoratchilar</div><div class="h-sub">Guruhga tayinlash — guruh sahifasida</div>
      <div class="section"><div class="card"><label class="field"><span>Yangi nazoratchining telefon raqami</span>
        <input class="input" id="phone" inputmode="tel" placeholder="+998 90 123 45 67"></label>
        <button class="btn block" id="add">Nazoratchi qilish</button>
        <p class="note" style="text-align:left">U avval botda /start bosib ro'yxatdan o'tgan bo'lishi kerak.</p></div></div>
      <div class="section"><div class="label">Ro'yxat</div>${rows}</div>`);
    document.getElementById("add").onclick = async () => {
      try { const r = await post("/api/admin/staff", { phone: document.getElementById("phone").value });
        haptic("ok"); toast(`${r.name} nazoratchi qilindi`); staffPage(); } catch (e) { haptic("err"); toast(e.message); }
    };
    $app.querySelectorAll("[data-rm]").forEach((b) => b.onclick = async () => {
      if (!(await confirmBox(`${b.dataset.n} nazoratchilikdan olinsinmi?`))) return;
      try { await del(`/api/admin/staff/${b.dataset.rm}`); toast("Olib tashlandi"); staffPage(); } catch (e) { toast(e.message); }
    });
  }

  // ---------- ustozlar: tanga, chiqarish ----------
  async function membersPage(gid) {
    const d = await api(`/api/admin/groups/${gid}/members`);
    let open = null;
    const draw = () => {
      const rows = d.members.length ? `<div class="list">${d.members.map((m) => `
        <button class="row" data-m="${m.id}"><div class="place ${m.place <= 3 ? "p" + m.place : ""}">${m.place}</div>
          <div class="grow"><div class="t">${esc(m.name)}</div><div class="s">${esc(m.phone)} · ${m.tests} test${m.avg !== null ? ` · ${m.avg}%` : ""}</div></div>
          ${coinsHtml(m.coins)}</button>
        ${open === m.id ? `<div class="expand">
          <div class="field" style="margin-top:12px"><span>Tanga</span><div class="chips">
            ${[1, 3, 5, -2, -5].map((v) => `<button class="pick" data-v="${v}">${v > 0 ? "+" + v : "−" + (-v)}</button>`).join("")}</div></div>
          <label class="field"><span>Yoki miqdor</span><input class="input" id="amt" inputmode="numeric" placeholder="masalan 2 yoki -3"></label>
          <label class="field"><span>Sabab</span><input class="input" id="why" maxlength="200" placeholder="Darsda faol qatnashgani uchun"></label>
          <div class="btn-row"><button class="btn" id="giveC">Saqlash</button><button class="btn line" id="kick">Guruhdan chiqarish</button></div>
        </div>` : ""}`).join("")}</div>` : `<div class="card empty">Guruhda hali ustoz yo'q.</div>`;
      render(`<div class="h-title">👥 ${esc(d.group.name)}</div><div class="h-sub">${d.members.length} ta ustoz · tanga berish uchun ismni bosing</div>
        <div class="section" style="margin-top:14px">${rows}</div>`);
      $app.querySelectorAll("[data-m]").forEach((b) => b.onclick = () => { open = open === +b.dataset.m ? null : +b.dataset.m; draw(); });
      if (open === null) return;
      const amt = document.getElementById("amt");
      $app.querySelectorAll("[data-v]").forEach((b) => b.onclick = () => {
        amt.value = b.dataset.v; $app.querySelectorAll("[data-v]").forEach((x) => x.classList.toggle("on", x === b)); haptic();
      });
      document.getElementById("giveC").onclick = async () => {
        try {
          await post(`/api/admin/groups/${gid}/coins`, { user_id: open, amount: parseInt(amt.value, 10), reason: document.getElementById("why").value });
          haptic("ok"); toast("Saqlandi, ustozga xabar yuborildi"); membersPage(gid);
        } catch (e) { haptic("err"); toast(e.message); }
      };
      document.getElementById("kick").onclick = async () => {
        const m = d.members.find((x) => x.id === open);
        if (!(await confirmBox(`${m.name} guruhdan chiqarilsinmi?`))) return;
        try { await del(`/api/admin/groups/${gid}/members/${open}`); toast("Chiqarildi"); membersPage(gid); } catch (e) { toast(e.message); }
      };
    };
    draw();
  }

  // ---------- yangi test ----------
  async function newTest(gid) {
    let key = Array(30).fill("-");
    const draft = store.get(`newtest:${gid}`);
    if (draft && draft.key) key = draft.key.split("");
    let title = (draft && draft.title) || "";
    const draw = () => {
      render(`<div class="h-title">Yangi test</div><div class="h-sub">Kalitni belgilang, keyin nashr qilasiz</div>
        <div class="section"><div class="card">
          <label class="field"><span>Test nomi</span><input class="input" id="title" maxlength="80" placeholder="Masalan: 3-hafta: Hosila" value="${esc(title)}"></label>
          <div class="field"><span>Fayl (PDF yoki rasm, ixtiyoriy)</span>
            <label class="filepick"><input id="file" type="file" accept=".pdf,image/*,.doc,.docx" hidden>
              <span class="btn ghost">📎 Fayl tanlash</span><span class="fname" id="fname">Tanlanmagan</span></label></div>
          <label class="field" style="margin-bottom:0"><span>Savollar soni</span><div class="stepper">
            <button id="minus">−</button><input class="input" id="count" inputmode="numeric" value="${key.length}"><button id="plus">+</button></div></label>
        </div></div>
        <div class="section"><div class="card">
          <label class="field"><span>Kalitni matn bilan to'ldirish (ixtiyoriy)</span>
            <textarea class="input" id="ktext" placeholder="abcdabcd... yoki 1a 2b 3c ..."></textarea></label>
          <button class="btn ghost block" id="fill">Varaqaga to'ldirish</button></div></div>
        <div class="section"><div class="label">Javoblar kaliti</div><div class="sheet" id="keybox">${keyRows(key)}</div></div>
        <div class="bar-bottom"><div class="inner"><div class="cnt">Belgilandi<br><b id="cnt">0</b> / <span id="tot">${key.length}</span></div>
          <button class="btn" id="save" style="min-width:150px">Saqlash</button></div></div>`);
      const cnt = document.getElementById("cnt");
      const saveDraft = () => store.set(`newtest:${gid}`, { title, key: key.join("") });
      const upd = () => { cnt.textContent = key.filter((k) => k !== "-").length; saveDraft(); };
      upd();
      bindKey(document.getElementById("keybox"), key, upd);
      document.getElementById("title").oninput = (e) => { title = e.target.value; saveDraft(); };
      document.getElementById("file").onchange = (e) => {
        const f = e.target.files[0];
        document.getElementById("fname").textContent = f ? `${f.name} (${(f.size / 1048576).toFixed(1)} MB)` : "Tanlanmagan";
        if (f && f.size > 15 * 1048576) { toast("Fayl 15 MB dan katta"); e.target.value = ""; document.getElementById("fname").textContent = "Tanlanmagan"; }
      };
      const setCount = (n) => {
        n = Math.max(1, Math.min(200, n || 1));
        key = key.slice(0, n).concat(Array(Math.max(0, n - key.length)).fill("-"));
        saveDraft(); draw();
      };
      document.getElementById("minus").onclick = () => setCount(key.length - 1);
      document.getElementById("plus").onclick = () => setCount(key.length + 1);
      document.getElementById("count").onchange = (e) => setCount(parseInt(e.target.value, 10));
      document.getElementById("fill").onclick = () => {
        const parsed = parseKeyText(document.getElementById("ktext").value);
        if (!parsed.length) return toast("Kalit topilmadi. Masalan: abcdabcd");
        key = parsed; saveDraft(); draw(); toast(`${parsed.length} ta javob to'ldirildi`);
      };
      document.getElementById("save").onclick = async () => {
        title = title.trim();
        const missing = key.map((k, i) => (k === "-" ? i + 1 : null)).filter(Boolean);
        if (title.length < 2) return toast("Test nomini yozing");
        if (missing.length) return toast(`Belgilanmagan: ${missing.slice(0, 8).join(", ")}${missing.length > 8 ? "…" : ""}`);
        const fd = new FormData();
        fd.append("title", title); fd.append("key", key.join(""));
        const f = document.getElementById("file").files[0];
        if (f) fd.append("file", f);
        const btn = document.getElementById("save"); btn.disabled = true; btn.textContent = f ? "Yuklanmoqda…" : "Saqlanmoqda…";
        try {
          const r = await api(`/api/admin/groups/${gid}/tests`, { method: "POST", body: fd });
          store.del(`newtest:${gid}`); haptic("ok"); toast("Test saqlandi. Endi nashr qiling."); go(`/t/${r.id}`);
        } catch (e) { haptic("err"); btn.disabled = false; btn.textContent = "Saqlash"; toast(e.message); }
      };
    };
    draw();
  }

  // ---------- kalitni o'zgartirish / tuzatish ----------
  async function editKey(tid) {
    const t = await api(`/api/admin/tests/${tid}`);
    const key = t.key.split("");
    const live = t.status === "published" || t.status === "closed";
    render(`<div class="h-title">🔑 ${esc(t.title)}</div>
      <div class="h-sub">${live ? "O'zgartirilgan savollar bo'yicha barcha natijalar qayta hisoblanadi va tangalar to'g'rilanadi." : "Nashrdan oldin kalitni bemalol o'zgartirish mumkin."}</div>
      <div class="section"><div class="sheet" id="keybox">${keyRows(key)}</div></div>
      <div class="bar-bottom"><div class="inner"><div class="cnt">O'zgardi<br><b id="cnt">0</b> ta</div>
        <button class="btn" id="save" style="min-width:150px">Saqlash</button></div></div>`);
    const cnt = document.getElementById("cnt");
    bindKey(document.getElementById("keybox"), key, () => { cnt.textContent = key.filter((k, i) => k !== t.key[i]).length; });
    document.getElementById("save").onclick = async () => {
      const changed = key.map((k, i) => (k !== t.key[i] ? `№${i + 1}: ${t.key[i]} → ${k}` : null)).filter(Boolean);
      if (!changed.length) return toast("Kalit o'zgarmadi");
      if (!(await confirmBox(`Kalit o'zgaradi:\n${changed.slice(0, 10).join("\n")}${live ? "\n\nNatijalar qayta hisoblanadi." : ""}`))) return;
      try { const r = await post(`/api/admin/tests/${tid}/key`, { key: key.join("") }); haptic("ok");
        toast(live ? `Kalit yangilandi. ${r.changed} ta ustoz natijasi o'zgardi.` : "Kalit yangilandi"); go(`/t/${tid}`);
      } catch (e) { haptic("err"); toast(e.message); }
    };
  }

  // ---------- test sahifasi (nazoratchi) ----------
  async function adminTest(id) {
    const t = await api(`/api/admin/tests/${id}`);
    const live = t.status === "published" || t.status === "closed";
    let sort = store.get("qsort") || "num";
    let selected = null;
    let hours = 24;

    const publishBlock = () => `<div class="section"><div class="card">
      <div class="title" style="font-weight:700;margin-bottom:10px">🚀 Nashr qilish</div>
      ${t.active_other ? `<div class="warn" style="margin-bottom:12px">«${esc(t.active_other)}» hozir faol. Bu test <b>navbatga</b> qo'yiladi va u yakunlanishi bilan avtomatik nashr qilinadi.</div>` : ""}
      <div class="field"><span>Davomiyligi</span><div class="chips">${DURATIONS.map(([h, l]) =>
        `<button class="pick ${h === hours ? "on" : ""}" data-h="${h}">${l}</button>`).join("")}</div></div>
      ${t.active_other ? "" : `<label class="field"><span>Yoki aniq muddat (Toshkent vaqti)</span><input class="input" id="dl" type="datetime-local"></label>`}
      <button class="btn block" id="pub">${t.active_other ? "⏳ Navbatga qo'yish" : "🚀 Nashr qilish"}</button>
      <p class="note">Nashr qilinganda guruhdagi barcha ustozlarga xabar boradi.</p></div></div>`;

    const draw = () => {
      const [cls, label] = STATUS[t.status];
      const head = `<div class="h-title">${esc(t.title)}</div>
        <div class="h-sub"><span class="chip ${cls}">${label}</span> · ${t.n} ta savol${t.has_file ? " · 📎 fayl bor" : ""}</div>
        <div class="h-sub" style="margin-top:6px">${t.status === "published" ? `Muddat: ${fmtDate(t.deadline_at)} (${left(t.deadline_at)} qoldi)`
          : t.status === "closed" ? `Yakunlangan: ${fmtDate(t.closed_at)}` : t.status === "queued" ? `Navbatda · davomiyligi ${t.queue_hours} soat` : "Hali nashr qilinmagan"}</div>`;

      let actions = "";
      if (t.status === "draft") actions = publishBlock() + `<div class="section"><div class="agrid">${abtn("🔑", "Kalitni o'zgartirish", `data-go="/key/${t.id}"`)}${abtn("🗑", "O'chirish", `id="tdel"`, "danger")}</div></div>`;
      if (t.status === "queued") actions = `<div class="section"><div class="agrid">${abtn("↩️", "Navbatdan olish", `id="unq"`)}${abtn("🔑", "Kalitni o'zgartirish", `data-go="/key/${t.id}"`)}${abtn("🗑", "O'chirish", `id="tdel"`, "danger")}</div></div>`;
      if (t.status === "published") actions = `<div class="section"><div class="agrid">${abtn("📣", "Eslatma yuborish", `id="remind"`)}${abtn("🔑", "Kalitni tuzatish", `data-go="/key/${t.id}"`)}${abtn("⏹", "Hozir yakunlash", `id="closeT"`, "danger")}</div></div>`;
      if (t.status === "closed") actions = `<div class="section"><div class="agrid">${abtn("🔑", "Kalitni tuzatish", `data-go="/key/${t.id}"`)}</div></div>`;

      let stats = "";
      if (live) {
        const avgPct = t.avg !== null ? Math.round(100 * t.avg / t.n) : null;
        const qs = [...t.questions].sort((a, b) => (sort === "err" ? b.wrong_pct - a.wrong_pct || a.num - b.num : a.num - b.num));
        const bars = t.submitted ? qs.map((q) => `
          <button class="qb ${selected === q.num ? "sel" : ""}" data-q="${q.num}" aria-label="${q.num}-savol: ${q.wrong_pct}% xato">
            <span class="n">№${q.num}</span><span class="track"><i style="width:${q.wrong_pct}%"></i></span><span class="pct">${q.wrong_pct}%</span></button>
          ${selected === q.num ? `<div class="qdetail">To'g'ri javob: <b>${q.key}</b> · xato qilganlar: ${q.wrong} ta${q.common ? ` · ko'pchilik <b>${q.common}</b> ni tanlagan` : ""}</div>` : ""}`).join("")
          : `<div class="empty">Hali hech kim topshirmagan.</div>`;
        const results = t.results.length ? `<div class="section"><div class="label">Natijalar</div><div class="list">${t.results.map((r, i) => `
          <div class="row"><div class="place ${i < 3 ? "p" + (i + 1) : ""}">${i + 1}</div>
            <div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${fmtDate(r.submitted_at)}</div></div>
            <span class="chip ${r.correct === t.n ? "ok" : "muted"}">${r.correct}/${t.n}</span></div>`).join("")}</div></div>` : "";
        const missing = t.missing.length ? `<div class="section"><div class="label">Topshirmaganlar · ${t.missing.length}</div>
          <div class="list">${t.missing.map((n) => `<div class="row"><div class="grow"><div class="t">${esc(n)}</div></div></div>`).join("")}</div></div>` : "";
        stats = `<div class="section"><div class="tiles">
            <div class="tile"><div class="v">${t.submitted}/${t.members}</div><div class="k">topshirdi</div></div>
            <div class="tile"><div class="v">${t.avg !== null ? t.avg : "—"}</div><div class="k">o'rtacha / ${t.n}</div></div>
            <div class="tile"><div class="v">${avgPct !== null ? avgPct + "%" : "—"}</div><div class="k">o'zlashtirish</div></div></div></div>
          <div class="section"><div class="label">Savollar bo'yicha xato foizi</div>
            <div class="seg" style="margin-bottom:10px"><button data-s="num" class="${sort === "num" ? "on" : ""}">Tartib bo'yicha</button>
              <button data-s="err" class="${sort === "err" ? "on" : ""}">Eng ko'p xato</button></div>
            <div class="qbars">${bars}</div></div>${results}${missing}`;
      } else {
        stats = `<div class="section"><div class="label">Kalit</div><div class="card">${keyPreview(t.key)}</div></div>`;
      }
      render(head + actions + stats + `<div class="section"><button class="btn ghost block" data-go="/g/${t.group_id}">Guruhga qaytish</button></div>`);
      bind();
    };

    const reload = async () => { Object.assign(t, await api(`/api/admin/tests/${id}`)); draw(); };
    const bind = () => {
      $app.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => { sort = b.dataset.s; store.set("qsort", sort); draw(); });
      $app.querySelectorAll("[data-q]").forEach((b) => b.onclick = () => { selected = selected === +b.dataset.q ? null : +b.dataset.q; haptic(); draw(); });
      $app.querySelectorAll("[data-h]").forEach((b) => b.onclick = () => {
        hours = +b.dataset.h; const dl = document.getElementById("dl"); if (dl) dl.value = "";
        $app.querySelectorAll("[data-h]").forEach((x) => x.classList.toggle("on", x === b)); haptic();
      });
      const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
      on("pub", async () => {
        const dl = document.getElementById("dl");
        const payload = dl && dl.value ? { deadline: `${dl.value}:00+05:00` } : { hours };
        const when = payload.deadline ? `${dl.value.replace("T", " ")} gacha` : DURATIONS.find(([h]) => h === hours)[1];
        if (!(await confirmBox(t.active_other ? `Navbatga qo'yilsinmi? (${when})` : `Nashr qilinsinmi? Muddat: ${when}. Hamma ustozlarga xabar boradi.`))) return;
        try { const r = await post(`/api/admin/tests/${id}/publish`, payload); haptic("ok");
          toast(r.result === "queued" ? "Navbatga qo'yildi ⏳" : "Nashr qilindi 🚀"); reload(); } catch (e) { haptic("err"); toast(e.message); }
      });
      on("unq", async () => { try { await post(`/api/admin/tests/${id}/unqueue`); toast("Navbatdan olindi"); reload(); } catch (e) { toast(e.message); } });
      on("tdel", async () => {
        if (!(await confirmBox(`«${t.title}» o'chirilsinmi?`))) return;
        try { await del(`/api/admin/tests/${id}`); toast("O'chirildi"); go(`/g/${t.group_id}`); } catch (e) { toast(e.message); }
      });
      on("remind", async () => {
        if (!(await confirmBox("Topshirmagan ustozlarga test qayta yuborilsinmi?"))) return;
        try { const r = await post(`/api/admin/tests/${id}/remind`); haptic("ok"); toast(`📣 ${r.sent} ta ustozga yuborildi`); } catch (e) { toast(e.message); }
      });
      on("closeT", async () => {
        if (!(await confirmBox("Test hozir yakunlansinmi? Topshirmaganlarga jarima beriladi va hammaga to'g'ri javoblar yuboriladi."))) return;
        try { await post(`/api/admin/tests/${id}/close`); haptic("ok"); toast("Test yakunlandi"); reload(); } catch (e) { toast(e.message); }
      });
    };
    draw();
  }

  // ---------- e'tirozlar ----------
  async function appealsPage() {
    const { appeals } = await api("/api/admin/appeals");
    const cards = appeals.length ? appeals.map((a) => `<div class="card appeal" data-id="${a.id}">
      <div class="top" style="display:flex;justify-content:space-between;gap:10px"><div><div class="title" style="font-weight:700">${esc(a.name)}</div>
        <div class="meta h-sub">${esc(a.test)} · ${esc(a.group)} · ${fmtDate(a.created_at)}</div></div>
        ${a.correct !== null ? `<span class="chip muted">${a.correct}/${a.n}</span>` : ""}</div>
      ${a.given ? `<div class="q-info">№${a.question}: ustoz — <b>${esc(a.given)}</b>, kalit — <b style="color:var(--success)">${esc(a.key)}</b></div>` : ""}
      <div class="txt">«${esc(a.text)}»</div>
      <div class="btn-row" style="margin-top:14px"><button class="btn" data-act="accept">✅ +1</button><button class="btn line" data-act="reject">Rad etish</button></div>
      <button class="btn ghost block" style="margin-top:10px" data-act="fixkey">🔑 Kalit xato — tuzatish</button>
    </div>`).join("") : `<div class="card empty">Ochiq e'tiroz yo'q 👍</div>`;
    render(`<div class="h-title">📨 E'tirozlar</div><div class="h-sub">Ustozlarning test kaliti bo'yicha e'tirozlari</div>
      <div class="section">${cards}</div>`);
    $app.querySelectorAll(".appeal").forEach((card) => card.querySelectorAll("[data-act]").forEach((b) => b.onclick = async () => {
      const act = b.dataset.act;
      try {
        const r = await post(`/api/admin/appeals/${card.dataset.id}`, { action: act }); haptic("ok"); toast(r.verdict);
        if (act === "fixkey") return go(`/key/${r.test_id}`);
        appealsPage();
      } catch (e) { toast(e.message); appealsPage(); }
    }));
  }

  // ---------- ishga tushirish ----------
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-go]");
    if (el) { e.preventDefault(); haptic(); go(el.dataset.go); }
  });

  async function boot() {
    if (tg) {
      try { tg.ready(); tg.expand(); } catch { /* */ }
      tg.onEvent && tg.onEvent("themeChanged", setTheme);
      tg.BackButton && tg.BackButton.onClick(() => (history.length > 1 ? history.back() : go("/")));
    }
    setTheme();
    try { ME = await api("/api/me"); } catch (e) { return showError(e); }
    window.addEventListener("hashchange", router);
    const start = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param;
    if (start && /^test_\d+$/.test(start) && !location.hash) location.hash = `/test/${start.slice(5)}`;
    router();
  }
  boot();
})();
