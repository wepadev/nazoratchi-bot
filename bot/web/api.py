"""Mini App uchun HTTP API (aiohttp). Har bir so'rov Telegram initData imzosi bilan tekshiriladi."""
from __future__ import annotations

import logging
import re
from html import escape
from pathlib import Path

from aiogram import Bot
from aiohttp import web

from .. import services
from ..answers import mistakes
from ..config import Config
from ..db import Database, Test, User
from ..timeutil import utcnow
from .auth import validate_init_data

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
ANSWER_RE = re.compile(r"^[ABCD-]+$")

K_DB = web.AppKey("db", Database)
K_BOT = web.AppKey("bot", Bot)
K_CFG = web.AppKey("cfg", Config)
_RK = getattr(web, "RequestKey", None)  # aiohttp yangi versiyalarida
R_USER = _RK("user", User) if _RK else "user"
R_SUPER = _RK("is_super", bool) if _RK else "is_super"
R_ADMIN = _RK("is_admin", bool) if _RK else "is_admin"


def iso(dt):
    return dt.isoformat() if dt else None


def err(status: int, code: str, message: str) -> web.Response:
    return web.json_response({"error": code, "message": message}, status=status)


# ---------------- autentifikatsiya ----------------

@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    cfg = request.app[K_CFG]
    tg_user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), cfg.bot_token)
    if not tg_user:
        return err(401, "unauthorized", "Ilovani Telegram ichidan oching.")
    db = request.app[K_DB]
    user = await db.get_user(int(tg_user["id"]))
    if not user:
        return err(403, "not_registered", "Avval botda ro'yxatdan o'ting: /start")
    request[R_USER] = user
    request[R_SUPER] = user.id in cfg.super_admin_ids
    request[R_ADMIN] = request[R_SUPER] or user.is_admin
    return await handler(request)


async def can_manage(db: Database, request: web.Request, group_id: int) -> bool:
    if request[R_SUPER]:
        return True
    return request[R_ADMIN] and await db.is_group_admin(group_id, request[R_USER].id)


def test_brief(t: Test) -> dict:
    return {"id": t.id, "title": t.title, "n": t.n, "status": t.status,
            "published_at": iso(t.published_at), "deadline_at": iso(t.deadline_at), "closed_at": iso(t.closed_at)}


# ---------------- umumiy ----------------

async def me(request: web.Request) -> web.Response:
    u: User = request[R_USER]
    role = "super" if request[R_SUPER] else "admin" if request[R_ADMIN] else "ustoz"
    return web.json_response({"id": u.id, "name": u.full_name, "phone": u.phone, "role": role})


# ---------------- ustoz ----------------

async def home(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    u: User = request[R_USER]
    now = utcnow()
    since, _ = services.period_range("week", now)
    groups = []
    for g in await db.user_groups(u.id):
        rows = services.ranked(await db.rating(g.id))
        place, coins = next(((p, c) for p, x, c in rows if x.id == u.id), (None, 0))
        week = dict((x.id, c) for x, c in await db.rating(g.id, since))
        cnt, avg = await db.user_test_stats(u.id, g.id)
        groups.append({"id": g.id, "name": g.name, "coins": coins, "place": place, "total": len(rows),
                       "week_coins": week.get(u.id, 0), "tests_done": cnt,
                       "avg": round(avg, 1) if avg is not None else None})
    active = []
    for t in await db.user_open_tests(u.id):
        sub = await db.get_submission(t.id, u.id)
        g = await db.get_group(t.group_id)
        active.append(test_brief(t) | {"group": g.name, "correct": sub.correct if sub else None})
    recent = []
    for g in await db.user_groups(u.id):
        for t in reversed([t for t in await db.closed_tests(g.id) if t.status == "closed"][-10:]):
            sub = await db.get_submission(t.id, u.id)
            joined = await db.member_joined_at(g.id, u.id)
            if not sub and joined and t.published_at and t.published_at < joined:
                continue  # qo'shilishidan oldingi test
            recent.append(test_brief(t) | {"group": g.name, "correct": sub.correct if sub else None})
    recent.sort(key=lambda x: x["closed_at"] or "", reverse=True)
    cfg = request.app[K_CFG]
    recordings = [{"id": l.id, "title": l.title, "date": iso(l.created_at), "url": l.video_url}
                  for l in await db.user_recordings(u.id, limit=30)]
    open_lessons = [{"id": l.id, "title": l.title, "closes_at": iso(l.closes_at), "attended": att}
                    for l, att in await db.open_lessons_for_user(u.id, utcnow())]  # kod yuborilmaydi
    return web.json_response({"groups": groups, "active": active, "recent": recent[:15], "recordings": recordings,
                              "lessons": open_lessons,
                              "rules": {"per_correct": cfg.coins_per_correct, "penalty": cfg.penalty_not_submitted,
                                        "per_lesson": cfg.coins_per_lesson, "missed_lesson": cfg.penalty_missed_lesson}})


async def get_test(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    u: User = request[R_USER]
    t = await db.get_test(int(request.match_info["test_id"]))
    if not t or t.status not in ("published", "closed"):
        return err(404, "not_found", "Test topilmadi.")
    member = await db.is_member(t.group_id, u.id)
    if not member and not await can_manage(db, request, t.group_id):
        return err(403, "forbidden", "Siz bu guruh a'zosi emassiz.")
    g = await db.get_group(t.group_id)
    sub = await db.get_submission(t.id, u.id)
    data = test_brief(t) | {"group": g.name, "now": iso(utcnow()), "submission": None, "key": None}
    if sub:
        data["submission"] = {"answers": sub.answers, "correct": sub.correct, "submitted_at": iso(sub.submitted_at)}
    if sub and t.status == "published" and not t.deadline_at:
        # muddatsiz test: qaysi savollar xato — darhol (to'g'ri javobsiz)
        data["wrong"] = [num for num, _, _ in mistakes(sub.answers, t.answer_key)]
    if t.status == "closed":  # kalit faqat yakunlangandan keyin ochiladi
        data["key"] = t.answer_key
        if sub:
            data["mistakes"] = [{"num": n, "given": a, "right": k} for n, a, k in mistakes(sub.answers, t.answer_key)]
    return web.json_response(data)


async def submit_test(request: web.Request) -> web.Response:
    db, cfg, bot = request.app[K_DB], request.app[K_CFG], request.app[K_BOT]
    u: User = request[R_USER]
    t = await db.get_test(int(request.match_info["test_id"]))
    now = utcnow()
    expired = t is not None and t.deadline_at is not None and t.deadline_at <= now
    if not t or t.status != "published" or expired or not await db.is_member(t.group_id, u.id):
        return err(409, "not_active", "Bu test faol emas yoki muddati tugagan.")
    if await db.get_submission(t.id, u.id):
        return err(409, "already", "Siz bu testni allaqachon topshirgansiz.")
    try:
        body = await request.json()
        answers = str(body.get("answers", "")).upper()
    except Exception:
        return err(400, "bad_request", "Noto'g'ri so'rov.")
    if len(answers) != t.n or not ANSWER_RE.match(answers):
        return err(400, "bad_answers", f"Javoblar soni {t.n} ta bo'lishi kerak.")
    correct = await services.submit(db, cfg, t, u, answers, now)
    if correct is None:
        return err(409, "not_active", "Javob qabul qilinmadi: muddat tugagan yoki oldin topshirilgan.")
    coins = correct * cfg.coins_per_correct
    wrong = [num for num, _, _ in mistakes(answers, t.answer_key)] if not t.deadline_at else None
    await services.safe_send(bot, u.id,
                             f"✅ «{escape(t.title)}» javoblaringiz ilova orqali qabul qilindi.\n"
                             f"Natija: <b>{correct}/{t.n}</b> (+{coins} 🪙)")
    return web.json_response({"correct": correct, "n": t.n, "coins": coins, "wrong": wrong})


async def rating(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    u: User = request[R_USER]
    gid = int(request.match_info["group_id"])
    period = request.query.get("period", "all")
    if period not in services.PERIOD_TITLES:
        period = "all"
    g = await db.get_group(gid)
    if not g or not (await db.is_member(gid, u.id) or await can_manage(db, request, gid)):
        return err(403, "forbidden", "Ruxsat yo'q.")
    since, until = services.period_range(period, utcnow())
    rows = services.ranked(await db.rating(gid, since, until))
    out = [{"place": p, "name": x.full_name, "coins": c, "me": x.id == u.id} for p, x, c in rows]
    mine = next((r for r in out if r["me"]), None)
    return web.json_response({"group": {"id": g.id, "name": g.name}, "period": period, "rows": out, "me": mine})


async def attend(request: web.Request) -> web.Response:
    """Ustoz jonli dars kodini kiritadi."""
    code = str((await body_json(request)).get("code", "")).strip()
    if not services.valid_lesson_code(code):
        return err(400, "bad_code", "Kod aynan 4 ta raqamdan iborat bo'lishi kerak.")
    cfg = request.app[K_CFG]
    status, lessons = await services.attend(request.app[K_DB], request[R_USER], code, utcnow(), cfg)
    text = re.sub(r"<[^>]+>", "", services.attend_reply(status, lessons, cfg))
    if status in ("wrong", "blocked"):
        return err(429 if status == "blocked" else 404, status, text)
    return web.json_response({"status": status, "message": text})


async def body_json(request: web.Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ---------------- nazoratchi ----------------

def admin_only(handler):
    async def wrapper(request: web.Request):
        if not request[R_ADMIN]:
            return err(403, "forbidden", "Faqat nazoratchilar uchun.")
        return await handler(request)
    return wrapper


@admin_only
async def admin_groups(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    groups = await db.list_groups(None if request[R_SUPER] else request[R_USER].id)
    out = []
    for g in groups:
        actives = [test_brief(a) | {"submitted": len(await db.list_submissions(a.id))}
                   for a in await db.active_tests(g.id)]
        out.append({"id": g.id, "name": g.name, "code": g.code, "members": g.member_count, "actives": actives})
    open_appeals = len(await db.open_appeals(None if request[R_SUPER] else request[R_USER].id))
    return web.json_response({"groups": out, "appeals_open": open_appeals})


@admin_only
async def admin_group(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    gid = int(request.match_info["group_id"])
    g = await db.get_group(gid)
    if not g or not await can_manage(db, request, gid):
        return err(403, "forbidden", "Ruxsat yo'q.")
    tests = []
    for t in await db.list_tests(gid, limit=50):
        subs = await db.list_submissions(t.id)
        avg = round(100 * sum(s.correct for s in subs) / (len(subs) * t.n), 1) if subs else None
        tests.append(test_brief(t) | {"submitted": len(subs), "avg_pct": avg})
    admins = [a.full_name for a in await db.group_admins(gid)]
    risky = [u.full_name for u in await services.at_risk(db, gid)]
    return web.json_response({"group": {"id": g.id, "name": g.name, "code": g.code, "members": g.member_count},
                              "admins": admins, "tests": tests, "at_risk": risky})


@admin_only
async def admin_test(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    t = await db.get_test(int(request.match_info["test_id"]))
    if not t or not await can_manage(db, request, t.group_id):
        return err(403, "forbidden", "Ruxsat yo'q.")
    subs = await db.list_submissions(t.id)
    members = {m.id: m for m in await db.list_members(t.group_id)}
    questions = [{"num": num, "key": t.answer_key[num - 1], "wrong": wrong,
                  "wrong_pct": round(100 * wrong / len(subs), 1) if subs else 0, "common": common}
                 for num, wrong, common in services.question_stats(t, [s.answers for s in subs])]
    results = sorted(
        ({"name": members[s.user_id].full_name if s.user_id in members else "—", "correct": s.correct,
          "submitted_at": iso(s.submitted_at)} for s in subs),
        key=lambda r: -r["correct"])
    missing = [u.full_name for u in await db.non_submitters(t, only_before_publish=False)] \
        if t.status in ("published", "closed") else []
    avg = round(sum(s.correct for s in subs) / len(subs), 1) if subs else None
    active = await db.active_test(t.group_id)
    return web.json_response(test_brief(t) | {
        "queue_hours": t.queue_hours, "has_file": bool(t.file_id),
        "active_other": None,
        "group_id": t.group_id, "key": t.answer_key, "members": len(members), "submitted": len(subs),
        "avg": avg, "questions": questions, "results": results, "missing": missing})


# ---------------- ilova ----------------

async def index(request: web.Request) -> web.Response:
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


def create_app(db: Database, bot: Bot, cfg: Config) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=16 * 1024 * 1024)  # fayl yuklash uchun
    app[K_DB], app[K_BOT], app[K_CFG] = db, bot, cfg
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_static("/static/", STATIC)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/home", home)
    app.router.add_post("/api/attend", attend)
    app.router.add_get(r"/api/tests/{test_id:\d+}", get_test)
    app.router.add_post(r"/api/tests/{test_id:\d+}/submit", submit_test)
    app.router.add_get(r"/api/groups/{group_id:\d+}/rating", rating)
    app.router.add_get("/api/admin/groups", admin_groups)
    app.router.add_get(r"/api/admin/groups/{group_id:\d+}", admin_group)
    app.router.add_get(r"/api/admin/tests/{test_id:\d+}", admin_test)
    from . import admin_api
    admin_api.setup(app)
    return app


async def start_server(db: Database, bot: Bot, cfg: Config) -> web.AppRunner:
    runner = web.AppRunner(create_app(db, bot, cfg), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", cfg.web_port).start()
    log.info("Mini App serveri %s-portda ishga tushdi", cfg.web_port)
    return runner
