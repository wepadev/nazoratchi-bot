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
      headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": (tg && tg.initData) || "" },
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
  async function adminHome() {
    const { groups } = await api("/api/admin/groups");
    const role = ME.role === "super" ? "Bosh admin" : "Nazoratchi";
    const list = groups.length ? groups.map((g) => {
      const a = g.active;
      const pct = a && g.members ? Math.round(100 * a.submitted / g.members) : 0;
      return `<button class="card tcard" style="display:block;width:100%;text-align:left" data-go="/g/${g.id}">
        <div class="top"><div><div class="title">${esc(g.name)}</div>
          <div class="meta">${g.members} ta ustoz · kod <span class="code">${esc(g.code)}</span></div></div><span class="chev">›</span></div>
        ${a ? `<div style="margin-top:14px"><div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:6px">
            <span><b>${esc(a.title)}</b></span><span class="h-sub">${a.submitted}/${g.members} topshirdi</span></div>
            <div class="progress"><i style="width:${pct}%"></i></div>
            <div class="meta" style="margin-top:6px">Muddat: ${fmtDate(a.deadline_at)} · ${left(a.deadline_at)} qoldi</div></div>`
          : `<div class="meta" style="margin-top:10px">Faol test yo'q</div>`}
      </button>`;
    }).join("") : `<div class="card empty">${ME.role === "super" ? "Hali guruh yo'q. Botda «🆕 Guruh yaratish» ni bosing." : "Sizga hali guruh tayinlanmagan."}</div>`;
    render(`<div class="hero"><div class="hi">${role}</div><div class="name">${esc(ME.name)}</div>
        <div class="hero-stats"><div class="hs"><div class="v">${groups.length}</div><div class="k">guruh</div></div>
        <div class="hs"><div class="v">${groups.reduce((s, g) => s + g.members, 0)}</div><div class="k">ustoz</div></div>
        <div class="hs"><div class="v">${groups.filter((g) => g.active).length}</div><div class="k">faol test</div></div></div></div>
      <div class="section"><div class="label">Guruhlar</div>${list}</div>
      <p class="note">Test yaratish va nashr qilish — botda: 🗂 Guruhlar → 📝 Testlar</p>`);
  }

  const STATUS = { draft: ["muted", "Qoralama"], queued: ["accent", "Navbatda"], published: ["brand", "Faol"], closed: ["ok", "Yakunlangan"] };

  async function adminGroup(id) {
    const d = await api(`/api/admin/groups/${id}`);
    const g = d.group;
    const tests = d.tests.length ? `<div class="list">${d.tests.map((t) => {
      const [cls, label] = STATUS[t.status];
      const clickable = t.status === "published" || t.status === "closed";
      const meta = clickable ? `${t.submitted}/${g.members} topshirdi${t.avg_pct !== null ? ` · o'rtacha ${t.avg_pct}%` : ""}` : `${t.n} ta savol`;
      return `<${clickable ? "button" : "div"} class="row" ${clickable ? `data-go="/t/${t.id}"` : ""}>
        <div class="grow"><div class="t">${esc(t.title)}</div><div class="s">${meta}</div></div>
        <span class="chip ${cls}">${label}</span>${clickable ? `<span class="chev">›</span>` : ""}</${clickable ? "button" : "div"}>`;
    }).join("")}</div>` : `<div class="card empty">Hali test yo'q.</div>`;
    const risk = d.at_risk.length ? `<div class="section"><div class="warn">⚠️ Ketma-ket 2 ta testni topshirmaganlar: ${d.at_risk.map(esc).join(", ")}</div></div>` : "";
    render(`<div class="h-title">${esc(g.name)}</div>
      <div class="h-sub">Kod: <span class="code">${esc(g.code)}</span> · ${g.members} ta ustoz</div>
      <div class="h-sub" style="margin-top:2px">Nazoratchilar: ${d.admins.length ? d.admins.map(esc).join(", ") : "tayinlanmagan"}</div>
      ${risk}
      <div class="section"><button class="btn ghost block" data-go="/rating/${g.id}">🏆 Reyting</button></div>
      <div class="section"><div class="label">Testlar</div>${tests}</div>`);
  }

  async function adminTest(id) {
    const t = await api(`/api/admin/tests/${id}`);
    const avgPct = t.avg !== null ? Math.round(100 * t.avg / t.n) : null;
    let sort = store.get("qsort") || "num";
    let selected = null;

    const draw = () => {
      const qs = [...t.questions].sort((a, b) => (sort === "err" ? b.wrong_pct - a.wrong_pct || a.num - b.num : a.num - b.num));
      const bars = t.submitted ? qs.map((q) => `
        <button class="qb ${selected === q.num ? "sel" : ""}" data-q="${q.num}" aria-label="${q.num}-savol: ${q.wrong_pct}% xato">
          <span class="n">№${q.num}</span><span class="track"><i style="width:${q.wrong_pct}%"></i></span><span class="pct">${q.wrong_pct}%</span></button>
        ${selected === q.num ? `<div class="qdetail">To'g'ri javob: <b>${q.key}</b> · xato qilganlar: ${q.wrong} ta${q.common ? ` · ko'pchilik <b>${q.common}</b> ni tanlagan` : ""}</div>` : ""}`).join("")
        : `<div class="empty">Hali hech kim topshirmagan.</div>`;
      const results = t.results.length ? `<div class="list">${t.results.map((r, i) => `
        <div class="row"><div class="place ${i < 3 ? "p" + (i + 1) : ""}">${i + 1}</div>
          <div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${fmtDate(r.submitted_at)}</div></div>
          <span class="chip ${r.correct === t.n ? "ok" : "muted"}">${r.correct}/${t.n}</span></div>`).join("")}</div>` : "";
      const missing = t.missing.length ? `<div class="section"><div class="label">Topshirmaganlar · ${t.missing.length}</div>
        <div class="list">${t.missing.map((n) => `<div class="row"><div class="grow"><div class="t">${esc(n)}</div></div></div>`).join("")}</div></div>` : "";
      render(`<div class="h-title">${esc(t.title)}</div>
        <div class="h-sub">${t.status === "published" ? `Faol · muddat ${fmtDate(t.deadline_at)} (${left(t.deadline_at)} qoldi)` : `Yakunlangan · ${fmtDate(t.closed_at)}`}</div>
        <div class="section" style="margin-top:14px"><div class="tiles">
          <div class="tile"><div class="v">${t.submitted}/${t.members}</div><div class="k">topshirdi</div></div>
          <div class="tile"><div class="v">${t.avg !== null ? t.avg : "—"}</div><div class="k">o'rtacha / ${t.n}</div></div>
          <div class="tile"><div class="v">${avgPct !== null ? avgPct + "%" : "—"}</div><div class="k">o'zlashtirish</div></div>
        </div></div>
        <div class="section"><div class="label"><span>Savollar bo'yicha xato foizi</span></div>
          <div class="seg" style="margin-bottom:10px"><button data-s="num" class="${sort === "num" ? "on" : ""}">Tartib bo'yicha</button>
            <button data-s="err" class="${sort === "err" ? "on" : ""}">Eng ko'p xato</button></div>
          <div class="qbars">${bars}</div></div>
        ${results ? `<div class="section"><div class="label">Natijalar</div>${results}</div>` : ""}
        ${missing}`);
      $app.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => { sort = b.dataset.s; store.set("qsort", sort); draw(); });
      $app.querySelectorAll("[data-q]").forEach((b) => b.onclick = () => { selected = selected === +b.dataset.q ? null : +b.dataset.q; haptic(); draw(); });
    };
    draw();
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
