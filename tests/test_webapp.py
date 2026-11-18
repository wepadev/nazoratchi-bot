import asyncio
import json
import time

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Config
from bot.db import Database
from bot.web.api import create_app
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
        assert ag["groups"][0]["active"]["submitted"] == 4
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
