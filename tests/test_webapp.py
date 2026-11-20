import asyncio
import json
import time

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Config
from bot.db import Database
from bot.web.api import create_app
from bot.timeutil import utcnow
from bot.web.auth import sign_init_data, validate_init_data
from tests.test_flow import FakeSession
from tests.webapp_seed import ADMIN, SUPER, TOKEN, init_data, seed


def test_init_data_validation():
    good = init_data(5)
    assert validate_init_data(good, TOKEN)["id"] == 5
    assert validate_init_data(good, "999:OTHER") is None
    assert validate_init_data(good.replace("first_name", "first_nam"), TOKEN) is None
    old = sign_init_data({"auth_date": str(int(time.time()) - 3 * 86400), "user": json.dumps({"id": 5})}, TOKEN)
    assert validate_init_data(old, TOKEN) is None
    assert validate_init_data("", TOKEN) is None


def test_api():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:")
        session = FakeSession()
        bot = Bot(TOKEN, session=session)
        ids = await seed(db, bot, cfg)
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()

        async def get(path, uid, status=200):
            r = await client.get(path, headers={"X-Telegram-Init-Data": init_data(uid)})
            assert r.status == status, (path, r.status, await r.text())
            return await r.json()

        # imzosiz va ro'yxatdan o'tmagan
        assert (await client.get("/api/me")).status == 401
        assert (await get("/api/me", 999, 403))["error"] == "not_registered"
        assert (await client.get("/")).status == 200

        assert (await get("/api/me", 301))["role"] == "ustoz"
        assert (await get("/api/me", ADMIN))["role"] == "admin"
        assert (await get("/api/me", SUPER))["role"] == "super"

        home = await get("/api/home", 301)
        g = home["groups"][0]
        assert g["coins"] == 23 and g["place"] == 4  # 20 to'g'ri + 3 qo'lda; faol testni topshirganlar oldinda
        assert home["active"][0]["id"] == ids["active"] and home["active"][0]["correct"] is None
        assert home["recent"][0]["correct"] == 20
        assert (await get("/api/home", 307))["recent"][0]["correct"] is None  # topshirmagan

        # faol test: kalit yashirin
        t = await get(f"/api/tests/{ids['active']}", 301)
        assert t["key"] is None and t["submission"] is None and t["n"] == 30
        # yakunlangan test: kalit va xatolar ochiq
        t = await get(f"/api/tests/{ids['closed']}", 303)
        assert t["key"] == "ABCDABCDABCDABCDABCD" and len(t["mistakes"]) == 4

        # javob yuborish
        url = f"/api/tests/{ids['active']}/submit"
        hdr = {"X-Telegram-Init-Data": init_data(301)}
        assert (await client.post(url, json={"answers": "ABC"}, headers=hdr)).status == 400
        r = await client.post(url, json={"answers": "CADBBCADDACBBACDCABDACBDABCDC-"}, headers=hdr)
        assert r.status == 200 and (await r.json())["correct"] == 29
        assert (await client.post(url, json={"answers": "C" * 30}, headers=hdr)).status == 409
        assert any("ilova orqali" in (getattr(m, "text", "") or "") for m in session.sent)

        # begona foydalanuvchi guruh testini ko'ra olmaydi
        await db.create_user(400, "998904000000", "Begona", None)
        await get(f"/api/tests/{ids['active']}", 400, 403)
        await get(f"/api/groups/{ids['group']}/rating", 400, 403)

        r = await get(f"/api/groups/{ids['group']}/rating?period=week", 301)
        assert r["me"] and sum(x["me"] for x in r["rows"]) == 1

        # nazoratchi
        await get("/api/admin/groups", 301, 403)
        ag = await get("/api/admin/groups", ADMIN)
        assert ag["groups"][0]["actives"][0]["submitted"] == 4
        grp = await get(f"/api/admin/groups/{ids['group']}", ADMIN)
        assert {t["status"] for t in grp["tests"]} == {"published", "closed"}
        st = await get(f"/api/admin/tests/{ids['closed']}", ADMIN)
        assert st["submitted"] == 6 and len(st["questions"]) == 20 and st["missing"] == ["Ergashev Sardor", "Nazarova Zarina"]
        await db.create_user(201, "998900000201", "Boshqa Nazoratchi", None, role="admin")
        await get(f"/api/admin/tests/{ids['closed']}", 201, 403)
        await get(f"/api/admin/tests/{ids['closed']}", SUPER)

        await client.close()
        await db.close()

    asyncio.run(scenario())


def test_admin_actions():
    async def scenario():
        import aiohttp
        db = Database(":memory:")
        await db.connect()
        cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:")
        session = FakeSession()
        bot = Bot(TOKEN, session=session)
        ids = await seed(db, bot, cfg)
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()
        H = lambda uid: {"X-Telegram-Init-Data": init_data(uid)}  # noqa: E731

        async def call(method, path, uid, status=200, **kw):
            r = await client.request(method, path, headers=H(uid), **kw)
            assert r.status == status, (method, path, r.status, await r.text())
            return await r.json()

        gid = ids["group"]
        # ustoz admin amallarini qila olmaydi; nazoratchi super amallarini qila olmaydi
        await call("POST", f"/api/admin/groups/{gid}/code", 301, 403)
        await call("POST", "/api/admin/groups", ADMIN, 403, json={"name": "X"})

        # bosh admin: guruh, nazoratchi qo'shish va tayinlash
        g2 = await call("POST", "/api/admin/groups", SUPER, json={"name": "Sertifikat guruhi"})
        await call("POST", "/api/admin/staff", SUPER, 404, json={"phone": "+998 99 999 99 99"})
        r = await call("POST", "/api/admin/staff", SUPER, json={"phone": "90 000 03 08"})
        assert r["id"] == 308 and (await db.get_user(308)).is_admin
        await call("POST", f"/api/admin/groups/{g2['id']}/admins/308", SUPER, json={"assigned": True})
        assert await db.is_group_admin(g2["id"], 308)
        admins = (await call("GET", f"/api/admin/groups/{g2['id']}/admins", SUPER))["admins"]
        assert any(a["id"] == 308 and a["assigned"] for a in admins)
        await call("PATCH", f"/api/admin/groups/{g2['id']}", SUPER, json={"name": "Yangi nom"})
        assert (await db.get_group(g2["id"])).name == "Yangi nom"
        assert len((await call("GET", "/api/admin/staff", SUPER))["staff"]) == 2
        await call("DELETE", f"/api/admin/staff/308", SUPER)
        assert not await db.is_group_admin(g2["id"], 308)
        await call("DELETE", f"/api/admin/groups/{g2['id']}", SUPER)

        # nazoratchi: test yaratish (fayl bilan), noto'g'ri kalit
        form = aiohttp.FormData()
        form.add_field("title", "3-hafta: Hosila")
        form.add_field("key", "ABCE")
        await call("POST", f"/api/admin/groups/{gid}/tests", ADMIN, 400, data=form)
        form = aiohttp.FormData()
        form.add_field("title", "3-hafta: Hosila")
        form.add_field("key", "abcdabcdab")
        form.add_field("file", b"%PDF-1.4 test", filename="test.pdf", content_type="application/pdf")
        tid = (await call("POST", f"/api/admin/groups/{gid}/tests", ADMIN, data=form))["id"]
        t = await db.get_test(tid)
        assert t.status == "draft" and t.answer_key == "ABCDABCDAB"
        assert any(type(m).__name__ == "SendDocument" for m in session.sent)  # fayl nazoratchiga yuborildi

        # qoralama kalitini o'zgartirish (savollar soni ham o'zgarishi mumkin)
        await call("POST", f"/api/admin/tests/{tid}/key", ADMIN, json={"key": "AAAAA"})
        assert (await db.get_test(tid)).answer_key == "AAAAA"

        # boshqa test faol bo'lsa ham nashr qilinadi (bir vaqtda bir nechta faol test)
        await call("POST", f"/api/admin/tests/{tid}/publish", ADMIN, 400, json={"deadline": "2000-01-01T10:00:00+05:00"})
        r = await call("POST", f"/api/admin/tests/{tid}/publish", ADMIN, json={"deadline": "2099-01-01T10:00:00+05:00"})
        assert r["result"] == "published"
        assert len(await db.active_tests(gid)) == 2
        await call("POST", f"/api/admin/tests/{tid}/publish", ADMIN, 409, json={})  # qayta nashr yo'q

        # muddatsiz test: draft -> hours 0
        form = aiohttp.FormData()
        form.add_field("title", "Muddatsiz")
        form.add_field("key", "AB")
        open_id = (await call("POST", f"/api/admin/groups/{gid}/tests", ADMIN, data=form))["id"]
        await call("POST", f"/api/admin/tests/{open_id}/publish", ADMIN, json={"hours": 0})
        assert (await db.get_test(open_id)).deadline_at is None
        r = await client.post(f"/api/tests/{open_id}/submit", json={"answers": "AA"}, headers={"X-Telegram-Init-Data": init_data(301)})
        assert (await r.json())["wrong"] == [2]
        t = await call("GET", f"/api/tests/{open_id}", 301)
        assert t["wrong"] == [2] and t["key"] is None  # xato raqami bor, kalit yo'q

        session.sent.clear()
        r = await call("POST", f"/api/admin/tests/{ids['active']}/remind", ADMIN)
        assert r["sent"] == 5  # 8 a'zodan 3 tasi topshirgan
        await call("POST", f"/api/admin/tests/{ids['active']}/close", ADMIN)
        assert (await db.get_test(ids["active"])).status == "closed"
        await call("DELETE", f"/api/admin/tests/{tid}", ADMIN, 409)  # faol testni o'chirib bo'lmaydi

        # yakunlangan test kalitini tuzatish -> natijalar qayta hisoblanadi
        await call("POST", f"/api/admin/tests/{ids['closed']}/key", ADMIN, 400, json={"key": "ABC"})
        key = list("ABCDABCDABCDABCDABCD")
        key[11] = "A"  # 12-savol: ko'pchilik A ni tanlagan
        r = await call("POST", f"/api/admin/tests/{ids['closed']}/key", ADMIN, json={"key": "".join(key)})
        assert r["changed"] >= 1

        # ustozlar, tanga, chiqarish, kod, excel
        m = await call("GET", f"/api/admin/groups/{gid}/members", ADMIN)
        assert len(m["members"]) == 8
        await call("POST", f"/api/admin/groups/{gid}/coins", ADMIN, 400, json={"user_id": 301, "amount": 3, "reason": ""})
        before = dict((u.id, c) for u, c in await db.rating(gid))[301]
        await call("POST", f"/api/admin/groups/{gid}/coins", ADMIN, json={"user_id": 301, "amount": -2, "reason": "Kechikdi"})
        assert dict((u.id, c) for u, c in await db.rating(gid))[301] == before - 2
        old = (await db.get_group(gid)).code
        assert (await call("POST", f"/api/admin/groups/{gid}/code", ADMIN))["code"] != old
        session.sent.clear()
        await call("POST", f"/api/admin/groups/{gid}/excel", ADMIN)
        assert any(type(m).__name__ == "SendDocument" and m.chat_id == ADMIN for m in session.sent)
        await call("DELETE", f"/api/admin/groups/{gid}/members/307", ADMIN)
        assert not await db.is_member(gid, 307)

        # e'tirozlar
        a1 = await db.create_appeal(ids["closed"], 303, 4, "4 — javob C", utcnow())
        a2 = await db.create_appeal(ids["closed"], 302, None, "Savol noaniq edi", utcnow())
        lst = (await call("GET", "/api/admin/appeals", ADMIN))["appeals"]
        assert {x["id"] for x in lst} == {a1, a2} and next(x for x in lst if x["id"] == a1)["given"] == "C"
        assert (await call("GET", "/api/admin/groups", ADMIN))["appeals_open"] == 2
        r = await call("POST", f"/api/admin/appeals/{a1}", ADMIN, json={"action": "accept"})
        assert "Qabul" in r["verdict"]
        await call("POST", f"/api/admin/appeals/{a1}", ADMIN, 409, json={"action": "reject"})
        r = await call("POST", f"/api/admin/appeals/{a2}", ADMIN, json={"action": "fixkey"})
        assert r["test_id"] == ids["closed"]

        await client.close()
        await db.close()

    asyncio.run(scenario())
