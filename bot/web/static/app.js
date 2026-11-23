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
    if (!iso) return `<span class="chip brand">♾ muddatsiz</span>`;
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
  function openUrl(url) {
    if (!/^https?:\/\//.test(url)) return;
    try { if (tg && tg.openLink && tg.initData) return tg.openLink(url); } catch { /* */ }
    window.open(url, "_blank", "noopener");
  }
  function clearTimers() { timers.forEach((t) => { clearInterval(t); clearTimeout(t); }); timers = []; }
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
    [/^lessons\/(\d+)$/, (id) => lessonsPage(+id)],
    [/^lesson\/(\d+)$/, (id) => lessonPage(+id)],
    [/^tasks\/(\d+)$/, (id) => tasksPage(+id)],
    [/^task\/(\d+)$/, (id) => taskPage(+id)],
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
          <div class="meta">${esc(t.group)} · ${t.n} ta savol${t.deadline_at ? ` · ${fmtDate(t.deadline_at)} gacha` : ""}</div></div>
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

    // kod maydoni faqat hozir ochiq va ustoz hali qatnashmagan dars bo'lsa ko'rinadi
    const pendingLessons = (HOME.lessons || []).filter((l) => !l.attended && new Date(l.closes_at) > Date.now());
    render(`${hero}
      ${pendingLessons.length ? `<div class="section"><div class="card"><div class="title" style="font-weight:700">🎥 Jonli dars kodi</div>
        <div class="h-sub" style="margin:4px 0 12px">«${esc(pendingLessons[0].title)}» — dars oxirida aytilgan 4 xonali kodni kiriting · ${fmtDate(pendingLessons[0].closes_at).split(" ")[1]} gacha</div>
        <div class="stepper"><input class="input" id="acode" inputmode="numeric" maxlength="4" placeholder="• • • •" style="letter-spacing:6px;font-size:20px">
        <button class="btn" id="asend" style="width:auto;padding:0 18px;font-size:16px">Yuborish</button></div></div></div>` : ""}
      ${(HOME.tasks || []).length ? `<div class="section"><div class="label">📋 Bugungi vazifalar</div><div class="list">${HOME.tasks.map((k) => `
        <div class="row"><div class="grow"><div class="t" style="white-space:normal">${esc(k.text)}</div></div>
          ${k.done ? `<span class="chip ok">✅ Bajarildi</span>` : `<button class="btn" data-task="${k.id}" style="height:40px;padding:0 14px;font-size:14px">Bajardim</button>`}</div>`).join("")}</div></div>` : ""}
      <div class="section"><div class="label">Faol testlar</div>${active}</div>
      ${g ? `<div class="section"><button class="btn ghost block" data-go="/rating/${g.id}">🏆 Reytingni ko'rish</button></div>` : ""}
      <div class="section"><div class="label">Natijalarim</div>${recent}</div>
      ${HOME.recordings && HOME.recordings.length ? `<div class="section"><div class="label">📺 Dars yozuvlari</div><div class="list">${HOME.recordings.map((v) => `
        <button class="row" data-video="${esc(v.url)}"><div class="ai-play">▶</div><div class="grow"><div class="t">${esc(v.title)}</div>
          <div class="s">${fmtDate(v.date).split(" ")[0]} · jonli dars yozuvi</div></div><span class="chev">›</span></button>`).join("")}</div></div>` : ""}
      <p class="note">To'g'ri javob: +${HOME.rules.per_correct} · Testni topshirmaslik: −${HOME.rules.penalty}<br>
        Jonli darsda qatnashish: +${HOME.rules.per_lesson}${HOME.rules.missed_lesson ? ` · Darsni qoldirish: −${HOME.rules.missed_lesson}` : ""} (tanga)</p>`);

    $app.querySelectorAll("[data-g]").forEach((b) => b.onclick = () => { store.set("group", +b.dataset.g); haptic(); ustozHome(); });
    $app.querySelectorAll("[data-video]").forEach((b) => b.onclick = () => openUrl(b.dataset.video));
    $app.querySelectorAll("[data-task]").forEach((b) => b.onclick = async () => {
      b.disabled = true;
      try { await post(`/api/tasks/${b.dataset.task}/done`); haptic("ok"); toast("✅ Barakalla! Belgilab qo'ydim."); ustozHome().catch(showError); }
      catch (e) { b.disabled = false; toast(e.message); }
    });
    if (pendingLessons.length) {  // muddat tugashi bilan maydon yo'qolsin
      const ms = Math.min(...pendingLessons.map((l) => new Date(l.closes_at) - Date.now())) + 1000;
      timers.push(setTimeout(() => { if (!location.hash.replace(/^#\/?/, "")) ustozHome().catch(showError); }, Math.min(ms, 2 ** 31 - 1)));
    }
    const asend = document.getElementById("asend");
    if (asend) {
      const ainput = document.getElementById("acode");
      asend.onclick = () => sendAttendance(ainput, asend);
      ainput.onkeydown = (e) => { if (e.key === "Enter") sendAttendance(ainput, asend); };
    }
  }

  // ---------- test sahifasi ----------
  async function testPage(id) {
    const t = await api(`/api/tests/${id}`);
    if (!t.submission && t.status === "published" && ME.role !== "ustoz") return go(`/t/${id}`);
    const live = !t.deadline_at || new Date(t.deadline_at) > Date.now();
    if (t.status === "published" && !t.submission && live) return answerSheet(t);
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
    if (t.deadline_at) timers.push(setInterval(() => {
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
          ${r.wrong ? `<p class="note">${r.wrong.length ? `Xato qilgan savollaringiz: <b>${r.wrong.join(", ")}</b>` : "Barcha javoblar to'g'ri! 🎉"}<br>To'g'ri javoblar test yakunlanganda ochiladi.</p>`
            : `<p class="note">Qaysi savollarda xato qilganingiz va to'g'ri javoblar muddat tugagach ko'rsatiladi.</p>`}
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
        : t.wrong ? `<p class="note">${t.wrong.length ? `Xato savollar: <b>${t.wrong.join(", ")}</b>` : "Barcha javoblar to'g'ri! 🎉"}<br>To'g'ri javoblar test yakunlanganda ochiladi.</p>`
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
        const known = closed || !!t.wrong;  // muddatsiz test: xato savollar ma'lum, kalit yo'q
        const miss = closed ? mine !== right : !!t.wrong && t.wrong.includes(i + 1);
        return `<div class="q ${miss ? "miss" : ""}"><div class="num">${i + 1}</div><div class="opts">${OPTS.map((o) => {
          let c = "";
          if (closed && o === right) c = mine === o ? "right on" : "right";
          else if (o === mine) c = closed || t.wrong ? (miss ? "wrong" : "right on") : "on";
          return `<span class="b ${c}">${o}</span>`;
        }).join("")}</div><div class="mark">${known ? (miss ? "✕" : "✓") : ""}</div></div>`;
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
  const STATUS = { draft: ["muted", "Qoralama"], scheduled: ["accent", "Rejalashtirilgan"], queued: ["accent", "Navbatda"], published: ["brand", "Faol"], closed: ["ok", "Yakunlangan"] };
  const DURATIONS = [[0, "♾ Muddatsiz"], [24, "1 kun"], [48, "2 kun"], [72, "3 kun"], [168, "1 hafta"]];
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
      const actives = g.actives || [];
      const bars = actives.map((a) => {
        const pct = g.members ? Math.round(100 * a.submitted / g.members) : 0;
        return `<div style="margin-top:14px"><div style="display:flex;justify-content:space-between;gap:8px;font-size:14px;margin-bottom:6px">
            <b>${esc(a.title)}</b><span class="h-sub" style="white-space:nowrap">${a.submitted}/${g.members} topshirdi</span></div>
            <div class="progress"><i style="width:${pct}%"></i></div>
            <div class="meta" style="margin-top:6px">${a.deadline_at ? `Muddat: ${fmtDate(a.deadline_at)} · ${left(a.deadline_at)} qoldi` : "♾ Muddatsiz"}</div></div>`;
      }).join("");
      return `<button class="card tcard" style="display:block;width:100%;text-align:left" data-go="/g/${g.id}">
        <div class="top"><div><div class="title">${esc(g.name)}</div>
          <div class="meta">${g.members} ta ustoz · kod <span class="code">${esc(g.code)}</span></div></div><span class="chev">›</span></div>
        ${bars || `<div class="meta" style="margin-top:10px">Faol test yo'q</div>`}
      </button>`;
    }).join("") : `<div class="card empty">${sup ? "Hali guruh yo'q — «Yangi guruh» ni bosing." : "Sizga hali guruh tayinlanmagan."}</div>`;
    render(`<div class="hero"><div class="hi">${sup ? "Bosh admin" : "Nazoratchi"}</div><div class="name">${esc(ME.name)}</div>
        <div class="hero-stats"><div class="hs"><div class="v">${groups.length}</div><div class="k">guruh</div></div>
        <div class="hs"><div class="v">${groups.reduce((s, g) => s + g.members, 0)}</div><div class="k">ustoz</div></div>
        <div class="hs"><div class="v">${groups.reduce((s, g) => s + (g.actives || []).length, 0)}</div><div class="k">faol test</div></div></div></div>
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
        ${abtn("🎥", "Jonli darslar", `data-go="/lessons/${g.id}"`)}
        ${abtn("📋", "Kunlik vazifalar", `data-go="/tasks/${g.id}"`)}
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
    let file = null;  // tanlangan fayl sahifa qayta chizilganda ham saqlanadi
    const fileLabel = () => (file ? `${file.name} (${(file.size / 1048576).toFixed(1)} MB)` : "Tanlanmagan");
    const draw = () => {
      render(`<div class="h-title">Yangi test</div><div class="h-sub">Kalitni belgilang, keyin nashr qilasiz</div>
        <div class="section"><div class="card">
          <label class="field"><span>Test nomi</span><input class="input" id="title" maxlength="80" placeholder="Masalan: 3-hafta: Hosila" value="${esc(title)}"></label>
          <div class="field"><span>Fayl (PDF yoki rasm, ixtiyoriy)</span>
            <label class="filepick"><input id="file" type="file" accept=".pdf,image/*,.doc,.docx" hidden>
              <span class="btn ghost">📎 Fayl tanlash</span><span class="fname" id="fname">${esc(fileLabel())}</span></label></div>
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
        const f = e.target.files[0] || null;
        if (f && f.size > 15 * 1048576) { toast("Fayl 15 MB dan katta"); e.target.value = ""; return; }
        file = f;
        document.getElementById("fname").textContent = fileLabel();
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
        const f = file;
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

  function scheduleText(t) {
    const dur = t.deadline_at ? `muddat ${fmtDate(t.deadline_at)} gacha` : t.queue_hours ? `nashrdan keyin ${t.queue_hours} soat` : "♾ muddatsiz";
    return `⏰ <b>${fmtDate(t.publish_at)}</b> da avtomatik nashr qilinadi · ${dur}`;
  }

  // ---------- test sahifasi (nazoratchi) ----------
  async function adminTest(id) {
    const t = await api(`/api/admin/tests/${id}`);
    const live = t.status === "published" || t.status === "closed";
    let sort = store.get("qsort") || "num";
    let selected = null;
    let hours = 0;

    let mode = "now";  // now | later
    const publishBlock = () => `<div class="section"><div class="card">
      <div class="title" style="font-weight:700;margin-bottom:10px">🚀 Nashr qilish</div>
      <div class="seg" style="margin-bottom:14px"><button data-mode="now" class="${mode === "now" ? "on" : ""}">Hozir</button>
        <button data-mode="later" class="${mode === "later" ? "on" : ""}">⏰ Rejalashtirish</button></div>
      ${mode === "later" ? `<label class="field"><span>Nashr vaqti (Toshkent vaqti)</span><input class="input" id="pat" type="datetime-local"></label>` : ""}
      <div class="field"><span>Muddat</span><div class="chips">${DURATIONS.map(([h, l]) =>
        `<button class="pick ${h === hours ? "on" : ""}" data-h="${h}">${l}</button>`).join("")}</div></div>
      <label class="field"><span>Yoki aniq muddat (Toshkent vaqti)</span><input class="input" id="dl" type="datetime-local"></label>
      <button class="btn block" id="pub">${mode === "later" ? "⏰ Rejalashtirish" : "🚀 Nashr qilish"}</button>
      <p class="note">Nashr qilinganda guruhdagi barcha ustozlarga xabar boradi. ♾ Muddatsiz test siz yakunlamaguningizcha faol turadi: ustoz xato savollar raqamini darhol ko'radi, to'g'ri javoblar va −5 jarima yakunlanganda.</p></div></div>`;

    const draw = () => {
      const [cls, label] = STATUS[t.status];
      const head = `<div class="h-title">${esc(t.title)}</div>
        <div class="h-sub"><span class="chip ${cls}">${label}</span> · ${t.n} ta savol${t.has_file ? " · 📎 fayl bor" : ""}</div>
        <div class="h-sub" style="margin-top:6px">${t.status === "published" ? (t.deadline_at ? `Muddat: ${fmtDate(t.deadline_at)} (${left(t.deadline_at)} qoldi)` : "♾ Muddatsiz · «Hozir yakunlash» bilan yopasiz")
          : t.status === "closed" ? `Yakunlangan: ${fmtDate(t.closed_at)}` : t.status === "queued" ? `Navbatda · davomiyligi ${t.queue_hours} soat`
          : t.status === "scheduled" ? `⏰ ${fmtDate(t.publish_at)} da nashr qilinadi` : "Hali nashr qilinmagan"}</div>`;

      let actions = "";
      if (t.status === "draft") actions = publishBlock() + `<div class="section"><div class="agrid">${abtn("🔑", "Kalitni o'zgartirish", `data-go="/key/${t.id}"`)}${abtn("🗑", "O'chirish", `id="tdel"`, "danger")}</div></div>`;
      if (t.status === "scheduled") actions = `<div class="section"><div class="warn">${scheduleText(t)}</div></div>
        <div class="section"><div class="agrid">${abtn("🚀", "Hozir nashr qilish", `id="pubnow"`)}${abtn("↩️", "Rejani bekor qilish", `id="unq"`)}${abtn("🔑", "Kalitni o'zgartirish", `data-go="/key/${t.id}"`)}${abtn("🗑", "O'chirish", `id="tdel"`, "danger")}</div></div>`;
      if (t.status === "queued") actions = `<div class="section"><div class="agrid">${abtn("↩️", "Navbatdan olish", `id="unq"`)}${abtn("🔑", "Kalitni o'zgartirish", `data-go="/key/${t.id}"`)}${abtn("🗑", "O'chirish", `id="tdel"`, "danger")}</div></div>`;
      if (t.status === "published") actions = `<div class="section"><div class="agrid">${abtn("📣", "Eslatma yuborish", `id="remind"`)}${abtn("🔑", "Kalitni tuzatish", `data-go="/key/${t.id}"`)}${abtn("⏹", "Hozir yakunlash", `id="closeT"`, "danger")}</div></div>`;
      if (t.status === "closed") actions = `<div class="section"><div class="agrid">${abtn("🔑", "Kalitni tuzatish", `data-go="/key/${t.id}"`)}</div></div>`;
      actions += `<div class="section"><label class="abtn" style="cursor:pointer"><span class="ai">📎</span>
        ${t.has_file ? "Test faylini almashtirish" : "Test faylini qo'shish"}<input type="file" id="tfile" accept=".pdf,image/*,.doc,.docx" hidden></label>
        ${t.status === "published" ? `<p class="note" style="text-align:left">Fayl guruhdagi barcha ustozlarga darhol yuboriladi.</p>` : ""}</div>`;

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
      const tf = document.getElementById("tfile");
      if (tf) tf.onchange = async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        if (f.size > 15 * 1048576) { e.target.value = ""; return toast("Fayl 15 MB dan katta"); }
        const fd = new FormData(); fd.append("file", f);
        toast("Yuklanmoqda…");
        try {
          const r = await api(`/api/admin/tests/${id}/file`, { method: "POST", body: fd });
          haptic("ok"); toast(r.sent ? `📎 Fayl saqlandi va ${r.sent} ta ustozga yuborildi` : "📎 Fayl saqlandi"); reload();
        } catch (err) { haptic("err"); toast(err.message); }
      };
      $app.querySelectorAll("[data-mode]").forEach((b) => b.onclick = () => { mode = b.dataset.mode; haptic(); draw(); });
      on("pub", async () => {
        const dl = document.getElementById("dl"), pat = document.getElementById("pat");
        const payload = dl && dl.value ? { deadline: `${dl.value}:00+05:00` } : { hours };
        const when = payload.deadline ? `${dl.value.replace("T", " ")} gacha` : DURATIONS.find(([h]) => h === hours)[1];
        if (mode === "later") {
          if (!pat || !pat.value) return toast("Nashr vaqtini tanlang");
          payload.publish_at = `${pat.value}:00+05:00`;
          if (!(await confirmBox(`${pat.value.replace("T", " ")} da avtomatik nashr qilinsinmi? Muddat: ${when}.`))) return;
        } else if (!(await confirmBox(`Nashr qilinsinmi? Muddat: ${when}. Hamma ustozlarga xabar boradi.`))) return;
        try { const r = await post(`/api/admin/tests/${id}/publish`, payload); haptic("ok");
          toast(r.result === "scheduled" ? "Rejalashtirildi ⏰" : r.result === "queued" ? "Navbatga qo'yildi ⏳" : "Nashr qilindi 🚀"); reload(); } catch (e) { haptic("err"); toast(e.message); }
      });
      on("pubnow", async () => {
        if (!(await confirmBox("Test hozir nashr qilinsinmi? Hamma ustozlarga xabar boradi."))) return;
        try { await post(`/api/admin/tests/${id}/publish_now`); haptic("ok"); toast("Nashr qilindi 🚀"); reload(); } catch (e) { toast(e.message); }
      });
      on("unq", async () => { try { await post(`/api/admin/tests/${id}/unqueue`); toast("Bekor qilindi — test qoralamaga qaytdi"); reload(); } catch (e) { toast(e.message); } });
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

  // ================= JONLI DARSLAR =================
  const LESSON_DURATIONS = [[30, "30 daqiqa"], [60, "1 soat"], [120, "2 soat"], [0, "Kun oxirigacha"]];
  const dayLabel = (iso) => fmtDate(iso).split(" ")[0];
  const timeLabel = (iso) => fmtDate(iso).split(" ")[1];

  async function sendAttendance(input, btn) {
    const code = input.value.replace(/\D/g, "");
    if (code.length !== 4) { haptic("err"); return toast("Kod 4 ta raqamdan iborat bo'lishi kerak"); }
    btn.disabled = true;
    try { const r = await post("/api/attend", { code }); haptic("ok"); toast(r.message); input.value = ""; ustozHome().catch(showError); }
    catch (e) { haptic("err"); toast(e.message); }
    finally { btn.disabled = false; }
  }

  async function lessonsPage(gid) {
    const d = await api(`/api/admin/groups/${gid}/lessons`);
    let minutes = 60;
    const open = d.lessons.filter((l) => l.open);
    const openCards = open.map((l) => `<div class="card" style="text-align:center">
        <div class="h-sub">${esc(l.title)} · ${dayLabel(l.created_at)}</div>
        <div class="lcode">${esc(l.code)}</div>
        <div class="h-sub">Dars oxirida shu kodni ayting · ${timeLabel(l.closes_at)} gacha ishlaydi</div>
        <div style="margin:14px 0 4px"><span class="chip brand">Qatnashdi ${l.present}/${l.total}</span></div>
        <div class="btn-row" style="margin-top:12px"><button class="btn ghost" data-go="/lesson/${l.id}">Ro'yxat</button>
          <button class="btn line" data-close="${l.id}">Kodni yopish</button></div></div>`).join("");
    const past = d.lessons.filter((l) => !l.open);
    const list = past.length ? `<div class="list">${past.map((l) => {
      const pct = l.total ? Math.round(100 * l.present / l.total) : 0;
      return `<button class="row" data-go="/lesson/${l.id}"><div class="grow"><div class="t">${dayLabel(l.created_at)} · ${esc(l.title)}</div>
        <div class="s">kod ${esc(l.code)} · ${l.total - l.present} kishi qatnashmadi${l.video_url ? " · 📺 yozuv bor" : ""}</div></div>
        <span class="chip ${pct >= 90 ? "ok" : pct >= 70 ? "muted" : "bad"}">${l.present}/${l.total}</span><span class="chev">›</span></button>`;
    }).join("")}</div>` : `<div class="card empty">Hali yakunlangan dars yo'q.</div>`;
    const missing = d.members.filter((m) => m.missed.length);
    const full = d.members.length - missing.length;
    const absent = missing.length ? `<div class="list">${missing.map((m) => `
      <div class="row" style="align-items:flex-start"><div class="grow"><div class="t">${esc(m.name)}</div>
        <div class="chips" style="margin-top:8px">${m.missed.map((x) => `<span class="chip bad">${dayLabel(x)}</span>`).join("")}</div></div>
        <span class="chip muted">${m.present}/${m.held}</span></div>`).join("")}</div>`
      : `<div class="card empty">${d.lessons.length ? "Hamma ustozlar barcha darslarda qatnashgan 👏" : "Ma'lumot yo'q."}</div>`;

    render(`<div class="h-title">🎥 Jonli darslar</div><div class="h-sub">${esc(d.group.name)}</div>
      ${openCards ? `<div class="section">${openCards}</div>` : ""}
      <div class="section"><div class="card">
        <div class="title" style="font-weight:700;margin-bottom:12px">➕ Yangi jonli dars</div>
        <label class="field"><span>Mavzu (ixtiyoriy)</span><input class="input" id="ltitle" maxlength="80" placeholder="Masalan: Logarifmik tenglamalar"></label>
        <label class="field"><span>YouTube yozuvi (ixtiyoriy, keyin ham qo'shsa bo'ladi)</span><input class="input" id="lvideo" inputmode="url" placeholder="https://youtu.be/..."></label>
        <div class="field"><span>4 xonali kod</span><div class="stepper">
          <input class="input" id="lcode" inputmode="numeric" maxlength="4" placeholder="4821" style="letter-spacing:4px">
          <button id="rnd" title="Avtomatik">🎲</button></div></div>
        <div class="field"><span>Kod qancha ishlasin</span><div class="chips">${LESSON_DURATIONS.map(([m, l]) =>
          `<button class="pick ${m === minutes ? "on" : ""}" data-min="${m}">${l}</button>`).join("")}</div></div>
        <button class="btn block" id="lopen">Darsni ochish</button>
        <p class="note" style="text-align:left">Dars oxirida kodni ayting. Ustozlar uni botga yoki ilovaga yozadi. Kod yopilganda qatnashmaganlar ro'yxati sizga keladi.</p>
      </div></div>
      <div class="section"><div class="label"><span>Qatnashmaganlar</span><span>${full ? `${full} kishi hammasida bor` : ""}</span></div>${absent}</div>
      <div class="section"><div class="label">Darslar</div>${list}</div>
      <div class="section"><button class="btn ghost block" id="axls">📥 Davomat Excel (barcha guruhlar)</button></div>`);

    $app.querySelectorAll("[data-min]").forEach((b) => b.onclick = () => {
      minutes = +b.dataset.min; $app.querySelectorAll("[data-min]").forEach((x) => x.classList.toggle("on", x === b)); haptic();
    });
    document.getElementById("rnd").onclick = () => {
      document.getElementById("lcode").value = String(Math.floor(Math.random() * 10000)).padStart(4, "0"); haptic();
    };
    document.getElementById("lopen").onclick = async () => {
      const code = document.getElementById("lcode").value.replace(/\D/g, "");
      if (code && code.length !== 4) return toast("Kod 4 ta raqamdan iborat bo'lishi kerak");
      try {
        const r = await post(`/api/admin/groups/${gid}/lessons`, { code, minutes, title: document.getElementById("ltitle").value, video_url: document.getElementById("lvideo").value });
        haptic("ok"); toast(`Dars ochildi. Kod: ${r.code}`); lessonsPage(gid);
      } catch (e) { haptic("err"); toast(e.message); }
    };
    $app.querySelectorAll("[data-close]").forEach((b) => b.onclick = async () => {
      if (!(await confirmBox("Kod yopilsinmi? Shundan keyin ustozlar uni kirita olmaydi."))) return;
      try { await post(`/api/admin/lessons/${b.dataset.close}/close`); toast("Kod yopildi"); lessonsPage(gid); } catch (e) { toast(e.message); }
    });
    document.getElementById("axls").onclick = async () => {
      try { await post("/api/admin/attendance/excel"); haptic("ok"); toast("📥 Excel fayl botga yuborildi"); } catch (e) { toast(e.message); }
    };
  }

  async function lessonPage(id) {
    const l = await api(`/api/admin/lessons/${id}`);
    let tab = store.get("ltab") || "absent";
    const draw = () => {
      const absent = l.people.filter((p) => !p.present), present = l.people.filter((p) => p.present);
      const shown = tab === "absent" ? absent : present;
      const pct = l.total ? Math.round(100 * l.present / l.total) : 0;
      render(`<div class="h-title">${esc(l.title)}</div>
        <div class="h-sub">${esc(l.group)} · ${dayLabel(l.created_at)} · kod <span class="code">${esc(l.code)}</span></div>
        <div class="h-sub" style="margin-top:4px">${l.open ? `🟢 kod ${timeLabel(l.closes_at)} gacha ishlaydi` : "Kod yopilgan"}</div>
        <div class="section" style="margin-top:14px"><div class="tiles">
          <div class="tile"><div class="v">${l.present}</div><div class="k">qatnashdi</div></div>
          <div class="tile"><div class="v">${l.total - l.present}</div><div class="k">qatnashmadi</div></div>
          <div class="tile"><div class="v">${pct}%</div><div class="k">davomat</div></div></div></div>
        <div class="section"><div class="seg"><button data-t="absent" class="${tab === "absent" ? "on" : ""}">Qatnashmadi · ${absent.length}</button>
          <button data-t="present" class="${tab === "present" ? "on" : ""}">Qatnashdi · ${present.length}</button></div></div>
        <div class="section" style="margin-top:12px">${shown.length ? `<div class="list">${shown.map((p) => `
          <button class="row" data-u="${p.id}"><div class="grow"><div class="t">${esc(p.name)}</div><div class="s">${esc(p.phone)}</div></div>
            <span class="switch ${p.present ? "on" : ""}"></span></button>`).join("")}</div>
          <p class="note">Kodni kirita olmaganlarni qo'lda belgilash uchun tugmani bosing.</p>`
          : `<div class="card empty">${tab === "absent" ? "Hamma qatnashgan 👏" : "Hali hech kim kod kiritmagan."}</div>`}</div>
        <div class="section"><div class="card"><div class="title" style="font-weight:700;margin-bottom:10px">📺 Dars yozuvi (YouTube)</div>
          <input class="input" id="vurl" inputmode="url" placeholder="https://youtu.be/..." value="${esc(l.video_url || "")}">
          <div class="btn-row" style="margin-top:10px"><button class="btn" id="vsave">Saqlash</button>
            ${l.video_url ? `<button class="btn ghost" id="vopen">▶ Ochish</button>` : ""}</div>
          <p class="note" style="text-align:left">Yangi havola saqlanganda guruhdagi ustozlarga yuboriladi va «📺 Dars yozuvlari» bo'limida turadi. O'chirish uchun maydonni bo'shatib saqlang.</p></div></div>
        <div class="section"><div class="btn-row">${l.open ? `<button class="btn line" id="lclose">Kodni yopish</button>` : ""}
          <button class="btn ghost" data-go="/lessons/${l.group_id}">Darslar</button></div>
          <button class="btn line block" id="ldel" style="margin-top:10px">O'chirish</button></div>`);
      $app.querySelectorAll("[data-t]").forEach((b) => b.onclick = () => { tab = b.dataset.t; store.set("ltab", tab); draw(); });
      $app.querySelectorAll("[data-u]").forEach((b) => b.onclick = async () => {
        const p = l.people.find((x) => x.id === +b.dataset.u);
        try { await post(`/api/admin/lessons/${id}/mark`, { user_id: p.id, present: !p.present });
          p.present = !p.present; l.present += p.present ? 1 : -1; haptic(); draw(); } catch (e) { toast(e.message); }
      });
      const c = document.getElementById("lclose");
      if (c) c.onclick = async () => {
        if (!(await confirmBox("Kod yopilsinmi?"))) return;
        try { await post(`/api/admin/lessons/${id}/close`); toast("Kod yopildi"); Object.assign(l, await api(`/api/admin/lessons/${id}`)); draw(); } catch (e) { toast(e.message); }
      };
      document.getElementById("vsave").onclick = async () => {
        try {
          const r = await post(`/api/admin/lessons/${id}/video`, { url: document.getElementById("vurl").value });
          l.video_url = r.video_url; haptic("ok");
          toast(r.video_url ? (r.sent ? `Saqlandi, ${r.sent} ta ustozga yuborildi` : "Saqlandi") : "Yozuv olib tashlandi"); draw();
        } catch (e) { haptic("err"); toast(e.message); }
      };
      const vo = document.getElementById("vopen"); if (vo) vo.onclick = () => openUrl(l.video_url);
      document.getElementById("ldel").onclick = async () => {
        if (!(await confirmBox("Bu dars va uning davomati o'chirilsinmi?"))) return;
        try { await del(`/api/admin/lessons/${id}`); toast("O'chirildi"); go(`/lessons/${l.group_id}`); } catch (e) { toast(e.message); }
      };
    };
    draw();
  }

  // ================= KUNLIK VAZIFALAR =================
  const dayLbl = (d) => `${d.slice(8, 10)}.${d.slice(5, 7)}`;

  async function tasksPage(gid) {
    const d = await api(`/api/admin/groups/${gid}/tasks`);
    let day = 0;
    const list = d.tasks.length ? `<div class="list">${d.tasks.map((t) => {
      const st = t.active ? `<span class="chip brand">bugun</span>` : t.upcoming ? `<span class="chip accent">rejada</span>` : "";
      const pct = t.total ? Math.round(100 * t.done / t.total) : 0;
      return `<button class="row" data-go="/task/${t.id}"><div class="grow"><div class="t">${esc(t.text)}</div>
        <div class="s">${dayLbl(t.day)} · bajardi ${t.done}/${t.total}</div></div>${st}
        <span class="chip ${pct >= 90 ? "ok" : pct >= 50 ? "muted" : "bad"}">${pct}%</span><span class="chev">›</span></button>`;
    }).join("")}</div>` : `<div class="card empty">Hali vazifa yo'q.</div>`;
    render(`<div class="h-title">📋 Kunlik vazifalar</div><div class="h-sub">${esc(d.group.name)}</div>
      <div class="section"><div class="card">
        <div class="title" style="font-weight:700;margin-bottom:12px">➕ Yangi vazifa</div>
        <label class="field"><span>Vazifa matni</span><textarea class="input" id="ttext" maxlength="500"
          placeholder="Masalan: Darslikning 45-betidagi 1–20 misollarni yeching"></textarea></label>
        <div class="field"><span>Qaysi kun uchun</span><div class="chips">
          <button class="pick on" data-day="0">📅 Bugun</button><button class="pick" data-day="1">📅 Ertaga</button></div></div>
        <button class="btn block" id="tadd">Qo'shish</button>
        <p class="note" style="text-align:left">Ustozlar «✅ Bajardim» bosguncha bot har soatda so'raydi (tunda emas). Kun oxirida bajarmaganlar ro'yxati sizga keladi.</p>
      </div></div>
      <div class="section"><div class="label">Vazifalar</div>${list}</div>`);
    $app.querySelectorAll("[data-day]").forEach((b) => b.onclick = () => {
      day = +b.dataset.day; $app.querySelectorAll("[data-day]").forEach((x) => x.classList.toggle("on", x === b)); haptic();
    });
    document.getElementById("tadd").onclick = async () => {
      const text = document.getElementById("ttext").value.trim();
      if (text.length < 3) return toast("Vazifa matnini yozing");
      try {
        const r = await post(`/api/admin/groups/${gid}/tasks`, { text, day });
        haptic("ok"); toast(day === 0 ? `Qo'shildi, ${r.sent} ta ustozga yuborildi` : "Qo'shildi — ertaga ertalabdan so'raladi");
        tasksPage(gid);
      } catch (e) { haptic("err"); toast(e.message); }
    };
  }

  async function taskPage(id) {
    const t = await api(`/api/admin/tasks/${id}`);
    let tab = "missing";
    const draw = () => {
      const missing = t.people.filter((p) => !p.done), done = t.people.filter((p) => p.done);
      const shown = tab === "missing" ? missing : done;
      render(`<div class="h-title">📋 ${esc(t.text)}</div>
        <div class="h-sub">${dayLbl(t.day)} · ${t.active ? "bugun — bajarmaganlardan har soatda so'ralyapti" : t.upcoming ? "rejada" : "kun tugagan"}</div>
        <div class="section" style="margin-top:14px"><div class="tiles">
          <div class="tile"><div class="v">${done.length}</div><div class="k">bajardi</div></div>
          <div class="tile"><div class="v">${missing.length}</div><div class="k">bajarmadi</div></div>
          <div class="tile"><div class="v">${t.total ? Math.round(100 * done.length / t.total) : 0}%</div><div class="k">bajarilish</div></div></div></div>
        <div class="section"><div class="seg"><button data-t="missing" class="${tab === "missing" ? "on" : ""}">Bajarmadi · ${missing.length}</button>
          <button data-t="done" class="${tab === "done" ? "on" : ""}">Bajardi · ${done.length}</button></div></div>
        <div class="section" style="margin-top:12px">${shown.length ? `<div class="list">${shown.map((p) => `
          <div class="row"><div class="grow"><div class="t">${esc(p.name)}</div><div class="s">${esc(p.phone)}</div></div>
          ${p.done ? `<span class="chip ok">✓</span>` : `<span class="chip bad">—</span>`}</div>`).join("")}</div>`
          : `<div class="card empty">${tab === "missing" ? "Hamma bajargan 👏" : "Hali hech kim bajarmagan."}</div>`}</div>
        <div class="section"><div class="btn-row"><button class="btn ghost" data-go="/tasks/${t.group_id}">Vazifalar</button>
          <button class="btn line" id="tdel2">O'chirish</button></div></div>`);
      $app.querySelectorAll("[data-t]").forEach((b) => b.onclick = () => { tab = b.dataset.t; draw(); });
      document.getElementById("tdel2").onclick = async () => {
        if (!(await confirmBox("Vazifa o'chirilsinmi? Eslatmalar to'xtaydi."))) return;
        try { await del(`/api/admin/tasks/${id}`); toast("O'chirildi"); go(`/tasks/${t.group_id}`); } catch (e) { toast(e.message); }
      };
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
