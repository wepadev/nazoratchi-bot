"""Mini App: nazoratchi va bosh admin amallari (yaratish, nashr, tanga, e'tirozlar...)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import escape

from aiogram.types import BufferedInputFile
from aiohttp import web

from .. import services
from ..db import normalize_phone
from ..excel import attendance_report, group_report
from ..timeutil import local, utcnow
from .api import K_BOT, K_CFG, K_DB, R_ADMIN, R_SUPER, R_USER, can_manage, err, iso

KEY_RE = re.compile(r"^[ABCD]{1,200}$")
MAX_FILE = 15 * 1024 * 1024


def admin_only(handler):
    async def wrapper(request: web.Request):
        if not request[R_ADMIN]:
            return err(403, "forbidden", "Faqat nazoratchilar uchun.")
        return await handler(request)
    return wrapper


def super_only(handler):
    async def wrapper(request: web.Request):
        if not request[R_SUPER]:
            return err(403, "forbidden", "Faqat bosh admin uchun.")
        return await handler(request)
    return wrapper


async def body(request: web.Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def clean_name(value, lo: int = 2, hi: int = 80) -> str | None:
    name = " ".join(str(value or "").split())
    return name if lo <= len(name) <= hi else None


async def managed_group(request: web.Request):
    db = request.app[K_DB]
    gid = int(request.match_info["group_id"])
    g = await db.get_group(gid)
    if not g or not await can_manage(db, request, gid):
        return None
    return g


async def managed_test(request: web.Request):
    db = request.app[K_DB]
    t = await db.get_test(int(request.match_info["test_id"]))
    if not t or not await can_manage(db, request, t.group_id):
        return None
    return t


NO_ACCESS = ("forbidden", "Topilmadi yoki ruxsat yo'q.")


# ======================= guruh =======================

@super_only
async def create_group(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    name = clean_name((await body(request)).get("name"), 2, 64)
    if not name:
        return err(400, "bad_name", "Nom 2–64 belgi bo'lishi kerak.")
    g = await db.create_group(name, request[R_USER].id)
    return web.json_response({"id": g.id, "code": g.code})


@super_only
async def update_group(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    name = clean_name((await body(request)).get("name"), 2, 64)
    if not name:
        return err(400, "bad_name", "Nom 2–64 belgi bo'lishi kerak.")
    await db.rename_group(g.id, name)
    return web.json_response({"ok": True})


@super_only
async def delete_group(request: web.Request) -> web.Response:
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    await request.app[K_DB].delete_group(g.id)
    return web.json_response({"ok": True})


@admin_only
async def new_code(request: web.Request) -> web.Response:
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    return web.json_response({"code": await request.app[K_DB].regenerate_code(g.id)})


@admin_only
async def members(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    rows = services.ranked(await db.rating(g.id))
    out = []
    for place, u, coins in rows:
        cnt, avg = await db.user_test_stats(u.id, g.id)
        out.append({"id": u.id, "name": u.full_name, "phone": u.phone, "username": u.username,
                    "coins": coins, "place": place, "tests": cnt, "avg": round(avg, 1) if avg is not None else None})
    return web.json_response({"group": {"id": g.id, "name": g.name}, "members": out})


@admin_only
async def kick(request: web.Request) -> web.Response:
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    await request.app[K_DB].remove_member(g.id, int(request.match_info["user_id"]))
    return web.json_response({"ok": True})


@admin_only
async def coins(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    data = await body(request)
    try:
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    reason = clean_name(data.get("reason"), 3, 200)
    target = await db.get_user(int(data.get("user_id") or 0))
    if not amount or abs(amount) > 9999 or not reason:
        return err(400, "bad_coins", "Miqdor (masalan 3 yoki -2) va sabab (kamida 3 belgi) kerak.")
    if not target or not await db.is_member(g.id, target.id):
        return err(404, "not_found", "Ustoz topilmadi.")
    await services.manual_coins(request.app[K_BOT], db, g, target, amount, reason, request[R_USER], utcnow())
    return web.json_response({"ok": True})


@admin_only
async def excel(request: web.Request) -> web.Response:
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    now = utcnow()
    data = await group_report(request.app[K_DB], g, now)
    safe = re.sub(r"[^\w\-]+", "_", g.name).strip("_") or "guruh"
    await request.app[K_BOT].send_document(
        request[R_USER].id, BufferedInputFile(data, filename=f"{safe}_{local(now):%Y-%m-%d}.xlsx"),
        caption=f"📥 <b>{escape(g.name)}</b>: reyting, natijalar, savollar tahlili, tangalar tarixi")
    return web.json_response({"ok": True})


# ---------------- nazoratchilarni tayinlash (bosh admin) ----------------

@super_only
async def group_admins(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    assigned = {a.id for a in await db.group_admins(g.id)}
    cfg = request.app[K_CFG]
    admins = [a for a in await db.list_admins() if a.id not in cfg.super_admin_ids]
    return web.json_response({"admins": [{"id": a.id, "name": a.full_name, "assigned": a.id in assigned}
                                         for a in admins]})


@super_only
async def toggle_admin(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    aid = int(request.match_info["admin_id"])
    target = await db.get_user(aid)
    if not g or not target or not target.is_admin:
        return err(404, "not_found", "Nazoratchi topilmadi.")
    if (await body(request)).get("assigned"):
        await db.assign_admin(g.id, aid)
        await services.safe_send(request.app[K_BOT], aid,
                                 f"📌 Siz <b>{escape(g.name)}</b> guruhiga nazoratchi etib tayinlandingiz.")
    else:
        await db.unassign_admin(g.id, aid)
    return web.json_response({"ok": True})


@super_only
async def staff(request: web.Request) -> web.Response:
    db, cfg = request.app[K_DB], request.app[K_CFG]
    rows = [r for r in await db.admin_activity() if r["id"] not in cfg.super_admin_ids]
    for r in rows:
        r["last_test"] = iso(r["last_test"])
        u = await db.get_user(r["id"])
        r["phone"] = u.phone if u else ""
    return web.json_response({"staff": rows})


@super_only
async def add_staff(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    raw = str((await body(request)).get("phone", "")).strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    target = await db.get_user_by_phone(raw) if len(digits) >= 9 else None
    if not target:
        return err(404, "not_found", f"{normalize_phone(raw) if digits else 'Bu raqam'} bilan ro'yxatdan o'tgan "
                                     "foydalanuvchi topilmadi. U avval botda /start bosishi kerak.")
    if not target.is_admin:
        await db.set_role(target.id, "admin")
        await services.safe_send(request.app[K_BOT], target.id,
                                 "🎉 Sizga nazoratchi huquqi berildi! Botda /start ni bosing.")
    return web.json_response({"id": target.id, "name": target.full_name})


@super_only
async def remove_staff(request: web.Request) -> web.Response:
    db, cfg = request.app[K_DB], request.app[K_CFG]
    uid = int(request.match_info["user_id"])
    if uid in cfg.super_admin_ids:
        return err(400, "super", "Bosh adminni olib bo'lmaydi.")
    target = await db.get_user(uid)
    if target and target.is_admin:
        await db.set_role(uid, "user")
        await services.safe_send(request.app[K_BOT], uid, "Sizning nazoratchi huquqingiz olib tashlandi.")
    return web.json_response({"ok": True})


# ======================= testlar =======================

async def _store_file(request: web.Request, field, title: str) -> tuple[str | None, str | None]:
    """Faylni nazoratchining o'ziga bot orqali yuborib, Telegram file_id ni oladi."""
    data = field.file.read()
    if not data:
        return None, None
    if len(data) > MAX_FILE:
        raise ValueError("Fayl 15 MB dan katta.")
    bot, uid = request.app[K_BOT], request[R_USER].id
    name = field.filename or "test.pdf"
    caption = f"📎 «{escape(title)}» test fayli saqlandi"
    if (field.content_type or "").startswith("image/") and len(data) < 10 * 1024 * 1024:
        msg = await bot.send_photo(uid, BufferedInputFile(data, filename=name), caption=caption)
        photos = getattr(msg, "photo", None)
        return (photos[-1].file_id, "photo") if photos else (None, None)
    msg = await bot.send_document(uid, BufferedInputFile(data, filename=name), caption=caption)
    doc = getattr(msg, "document", None)
    return (doc.file_id, "document") if doc else (None, None)


@admin_only
async def create_test(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    form = await request.post()
    title = clean_name(form.get("title"))
    key = str(form.get("key", "")).upper()
    if not title:
        return err(400, "bad_title", "Test nomi 2–80 belgi bo'lishi kerak.")
    if not KEY_RE.match(key):
        return err(400, "bad_key", "Kalitda har bir savolga A, B, C yoki D belgilanishi kerak.")
    file_id = file_type = None
    field = form.get("file")
    if field is not None and hasattr(field, "file"):
        try:
            file_id, file_type = await _store_file(request, field, title)
        except ValueError as e:
            return err(400, "bad_file", str(e))
    t = await db.create_test(g.id, title, key, file_id, file_type, request[R_USER].id)
    return web.json_response({"id": t.id})


@admin_only
async def publish_test(request: web.Request) -> web.Response:
    db, bot, cfg = request.app[K_DB], request.app[K_BOT], request.app[K_CFG]
    t = await managed_test(request)
    if not t or t.status != "draft":
        return err(409, "bad_state", "Faqat qoralama testni nashr qilish mumkin.")
    data = await body(request)
    now = utcnow()
    hours, deadline = data.get("hours"), None
    if data.get("deadline"):
        try:
            deadline = datetime.fromisoformat(str(data["deadline"]))
        except ValueError:
            deadline = None
        if not deadline or deadline.tzinfo is None or deadline < now + timedelta(minutes=30):
            return err(400, "bad_deadline", "Muddat kamida 30 daqiqadan keyin bo'lishi kerak.")
        hours = None
    else:
        try:
            hours = int(hours)
        except (TypeError, ValueError):
            hours = 0
        if not 1 <= hours <= 24 * 31:
            return err(400, "bad_hours", "Davomiylikni tanlang.")
    result = await services.publish_or_queue(bot, db, cfg, t, now, hours=hours, deadline=deadline)
    if result == "busy":
        return err(409, "busy", "Guruhda faol test bor. Aniq sana bilan emas, davomiylik bilan navbatga qo'ying.")
    return web.json_response({"result": result})


@admin_only
async def unqueue_test(request: web.Request) -> web.Response:
    t = await managed_test(request)
    if not t:
        return err(403, *NO_ACCESS)
    await request.app[K_DB].unqueue_test(t.id)
    return web.json_response({"ok": True})


@admin_only
async def close_test(request: web.Request) -> web.Response:
    t = await managed_test(request)
    if not t or t.status != "published":
        return err(409, "bad_state", "Test faol emas.")
    await services.close(request.app[K_BOT], request.app[K_DB], request.app[K_CFG], t, utcnow())
    return web.json_response({"ok": True})


@admin_only
async def delete_test(request: web.Request) -> web.Response:
    t = await managed_test(request)
    if not t or t.status not in ("draft", "queued"):
        return err(409, "bad_state", "Faqat qoralama yoki navbatdagi testni o'chirish mumkin.")
    await request.app[K_DB].delete_test(t.id)
    return web.json_response({"ok": True, "group_id": t.group_id})


@admin_only
async def remind_test(request: web.Request) -> web.Response:
    db, bot, cfg = request.app[K_DB], request.app[K_BOT], request.app[K_CFG]
    t = await managed_test(request)
    if not t or t.status != "published":
        return err(409, "bad_state", "Test faol emas.")
    from .. import keyboards as kb
    g = await db.get_group(t.group_id)
    text = services.announce_text(t, g, cfg, utcnow())
    sent = 0
    for u in await db.non_submitters(t, only_before_publish=False):
        sent += await services.send_test(bot, u.id, t, text, kb.answer_kb(t.id))
    return web.json_response({"sent": sent})


@admin_only
async def update_key(request: web.Request) -> web.Response:
    db, bot, cfg = request.app[K_DB], request.app[K_BOT], request.app[K_CFG]
    t = await managed_test(request)
    if not t:
        return err(403, *NO_ACCESS)
    key = str((await body(request)).get("key", "")).upper()
    if not KEY_RE.match(key):
        return err(400, "bad_key", "Kalitda har bir savolga A, B, C yoki D belgilanishi kerak.")
    if t.status in ("draft", "queued"):
        await db.update_test(t.id, answer_key=key)  # nashrdan oldin savollar sonini ham o'zgartirish mumkin
        return web.json_response({"changed": 0})
    if len(key) != t.n:
        return err(400, "bad_key", f"Nashr qilingan testda savollar soni o'zgarmaydi ({t.n} ta).")
    changed = await services.fix_key(bot, db, cfg, t, key, request[R_USER].id, utcnow())
    return web.json_response({"changed": changed})


# ======================= e'tirozlar =======================

@admin_only
async def appeals(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    out = []
    for a in await db.open_appeals(None if request[R_SUPER] else request[R_USER].id):
        t = await db.get_test(a.test_id)
        g = await db.get_group(t.group_id)
        u = await db.get_user(a.user_id)
        sub = await db.get_submission(t.id, u.id)
        item = {"id": a.id, "test_id": t.id, "test": t.title, "group": g.name, "n": t.n, "name": u.full_name,
                "phone": u.phone, "question": a.question, "text": a.text, "created_at": iso(a.created_at),
                "correct": sub.correct if sub else None, "given": None, "key": None}
        if sub and a.question and 1 <= a.question <= t.n:
            item["given"], item["key"] = sub.answers[a.question - 1], t.answer_key[a.question - 1]
        out.append(item)
    return web.json_response({"appeals": out})


@admin_only
async def resolve_appeal(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    a = await db.get_appeal(int(request.match_info["appeal_id"]))
    t = await db.get_test(a.test_id) if a else None
    if not a or not t or not await can_manage(db, request, t.group_id):
        return err(403, *NO_ACCESS)
    action = (await body(request)).get("action")
    if action not in ("accept", "reject", "fixkey"):
        return err(400, "bad_action", "Noto'g'ri amal.")
    verdict = await services.resolve_appeal(request.app[K_BOT], db, a, t, action, request[R_USER], utcnow())
    if verdict is None:
        return err(409, "resolved", "Bu e'tiroz allaqachon ko'rib chiqilgan.")
    return web.json_response({"verdict": verdict, "test_id": t.id})


def setup(app: web.Application) -> None:
    r = app.router
    r.add_post("/api/admin/groups", create_group)
    r.add_patch(r"/api/admin/groups/{group_id:\d+}", update_group)
    r.add_delete(r"/api/admin/groups/{group_id:\d+}", delete_group)
    r.add_post(r"/api/admin/groups/{group_id:\d+}/code", new_code)
    r.add_get(r"/api/admin/groups/{group_id:\d+}/members", members)
    r.add_delete(r"/api/admin/groups/{group_id:\d+}/members/{user_id:\d+}", kick)
    r.add_post(r"/api/admin/groups/{group_id:\d+}/coins", coins)
    r.add_post(r"/api/admin/groups/{group_id:\d+}/excel", excel)
    r.add_get(r"/api/admin/groups/{group_id:\d+}/admins", group_admins)
    r.add_post(r"/api/admin/groups/{group_id:\d+}/admins/{admin_id:\d+}", toggle_admin)
    r.add_post(r"/api/admin/groups/{group_id:\d+}/tests", create_test)
    r.add_get("/api/admin/staff", staff)
    r.add_post("/api/admin/staff", add_staff)
    r.add_delete(r"/api/admin/staff/{user_id:\d+}", remove_staff)
    r.add_post(r"/api/admin/tests/{test_id:\d+}/publish", publish_test)
    r.add_post(r"/api/admin/tests/{test_id:\d+}/unqueue", unqueue_test)
    r.add_post(r"/api/admin/tests/{test_id:\d+}/close", close_test)
    r.add_delete(r"/api/admin/tests/{test_id:\d+}", delete_test)
    r.add_post(r"/api/admin/tests/{test_id:\d+}/remind", remind_test)
    r.add_post(r"/api/admin/tests/{test_id:\d+}/key", update_key)
    r.add_get("/api/admin/appeals", appeals)
    r.add_post(r"/api/admin/appeals/{appeal_id:\d+}", resolve_appeal)
    setup_lessons(app)


# ======================= jonli darslar =======================

def lesson_json(lesson, roster, now) -> dict:
    present = sum(1 for _, p in roster if p)
    return {"id": lesson.id, "group_id": lesson.group_id, "title": lesson.title, "code": lesson.code,
            "created_at": iso(lesson.created_at), "closes_at": iso(lesson.closes_at),
            "open": lesson.is_open(now), "present": present, "total": len(roster)}


async def managed_lesson(request: web.Request):
    db = request.app[K_DB]
    lesson = await db.get_lesson(int(request.match_info["lesson_id"]))
    if not lesson or not await can_manage(db, request, lesson.group_id):
        return None
    return lesson


@admin_only
async def group_lessons(request: web.Request) -> web.Response:
    """Darslar ro'yxati + har bir ustozning qatnashmagan kunlari."""
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    now = utcnow()
    lessons, members, att = await db.attendance_matrix(g.id)
    out_lessons = []
    for lesson in reversed(lessons):
        roster = [(u, (lesson.id, u.id) in att) for u, j in members if not (j and j > lesson.closes_at)]
        out_lessons.append(lesson_json(lesson, roster, now))
    out_members = []
    for u, joined in members:
        held = [l for l in lessons if not l.is_open(now) and not (joined and joined > l.closes_at)]
        missed = [iso(l.created_at) for l in held if (l.id, u.id) not in att]
        out_members.append({"id": u.id, "name": u.full_name, "held": len(held),
                            "present": len(held) - len(missed), "missed": missed})
    out_members.sort(key=lambda m: (-len(m["missed"]), m["name"]))
    return web.json_response({"group": {"id": g.id, "name": g.name}, "lessons": out_lessons, "members": out_members})


@admin_only
async def create_lesson(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    g = await managed_group(request)
    if not g:
        return err(403, *NO_ACCESS)
    data = await body(request)
    now = utcnow()
    code = str(data.get("code") or "").strip() or await services.new_lesson_code(db, g.id, now)
    if not services.valid_lesson_code(code):
        return err(400, "bad_code", "Kod aynan 4 ta raqamdan iborat bo'lishi kerak.")
    if await db.open_code_in_group(g.id, code, now):
        return err(409, "code_busy", "Bu guruhda shu kod bilan ochiq dars bor. Boshqa kod tanlang.")
    try:
        minutes = int(data.get("minutes", 60))
    except (TypeError, ValueError):
        minutes = 60
    if minutes not in [m for m, _ in services.LESSON_DURATIONS]:
        return err(400, "bad_minutes", "Davomiylikni tanlang.")
    title = clean_name(data.get("title"), 2, 80) or "Jonli dars"
    lesson = await db.create_lesson(g.id, title, code, request[R_USER].id, now, services.lesson_closes_at(now, minutes))
    return web.json_response(lesson_json(lesson, [], now))


@admin_only
async def get_lesson(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    lesson = await managed_lesson(request)
    if not lesson:
        return err(403, *NO_ACCESS)
    now = utcnow()
    roster = await db.lesson_roster(lesson)
    g = await db.get_group(lesson.group_id)
    return web.json_response(lesson_json(lesson, roster, now) | {
        "group": g.name,
        "people": [{"id": u.id, "name": u.full_name, "phone": u.phone, "present": p} for u, p in roster]})


@admin_only
async def close_lesson(request: web.Request) -> web.Response:
    lesson = await managed_lesson(request)
    if not lesson:
        return err(403, *NO_ACCESS)
    await services.close_lesson(request.app[K_BOT], request.app[K_DB], request.app[K_CFG], lesson, utcnow())
    return web.json_response({"ok": True})


@admin_only
async def delete_lesson(request: web.Request) -> web.Response:
    lesson = await managed_lesson(request)
    if not lesson:
        return err(403, *NO_ACCESS)
    await request.app[K_DB].delete_lesson(lesson.id)
    return web.json_response({"ok": True, "group_id": lesson.group_id})


@admin_only
async def mark_lesson(request: web.Request) -> web.Response:
    """Nazoratchi qo'lda belgilaydi (masalan, ustoz kodni kirita olmagan bo'lsa)."""
    db = request.app[K_DB]
    lesson = await managed_lesson(request)
    if not lesson:
        return err(403, *NO_ACCESS)
    data = await body(request)
    uid = int(data.get("user_id") or 0)
    if not await db.is_member(lesson.group_id, uid):
        return err(404, "not_found", "Ustoz topilmadi.")
    now, admin = utcnow(), request[R_USER]
    if data.get("present"):
        await db.mark_attendance(lesson.id, uid, now, marked_by=admin.id)
    else:
        await db.unmark_attendance(lesson.id, uid)
    diff = await services.sync_lesson_coins(db, request.app[K_CFG], lesson, uid, now, admin_id=admin.id)
    if diff:
        what = "qatnashgan" if data.get("present") else "qatnashmagan"
        sign = "+" if diff > 0 else "−"
        await services.safe_send(request.app[K_BOT], uid,
                                 f"✏️ Nazoratchi sizni {services.lesson_label(lesson)} jonli darsida {what} deb "
                                 f"belgiladi: {sign}{abs(diff)} 🪙")
    return web.json_response({"ok": True, "coins": diff})


@admin_only
async def attendance_excel(request: web.Request) -> web.Response:
    db = request.app[K_DB]
    groups = await db.list_groups(None if request[R_SUPER] else request[R_USER].id)
    if not groups:
        return err(404, "no_groups", "Guruh yo'q.")
    now = utcnow()
    data = await attendance_report(db, groups, now)
    await request.app[K_BOT].send_document(
        request[R_USER].id, BufferedInputFile(data, filename=f"davomat_{local(now):%Y-%m-%d}.xlsx"),
        caption=f"🎥 Jonli darslar davomati: {len(groups)} ta guruh, barchasi bitta faylda")
    return web.json_response({"ok": True})


def setup_lessons(app: web.Application) -> None:
    r = app.router
    r.add_get(r"/api/admin/groups/{group_id:\d+}/lessons", group_lessons)
    r.add_post(r"/api/admin/groups/{group_id:\d+}/lessons", create_lesson)
    r.add_get(r"/api/admin/lessons/{lesson_id:\d+}", get_lesson)
    r.add_post(r"/api/admin/lessons/{lesson_id:\d+}/close", close_lesson)
    r.add_post(r"/api/admin/lessons/{lesson_id:\d+}/mark", mark_lesson)
    r.add_delete(r"/api/admin/lessons/{lesson_id:\d+}", delete_lesson)
    r.add_post("/api/admin/attendance/excel", attendance_excel)
