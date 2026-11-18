"""Mini App testlari va skrinshotlar uchun namunaviy ma'lumotlar."""
import json
import time
from datetime import timedelta

from aiogram import Bot

from bot import services
from bot.config import Config
from bot.db import Database
from bot.timeutil import utcnow
from bot.web.auth import sign_init_data

TOKEN = "123456:TEST"
SUPER, ADMIN = 100, 200
USTOZ = {301: "Aliyev Ali", 302: "Valiyeva Malika", 303: "Karimov Jasur", 304: "Soliyeva Dilnoza",
         305: "Rahimov Bekzod", 306: "Tursunova Gulnora", 307: "Ergashev Sardor", 308: "Nazarova Zarina"}


def init_data(uid: int, name: str = "User") -> str:
    return sign_init_data({"auth_date": str(int(time.time())),
                           "user": json.dumps({"id": uid, "first_name": name}, separators=(",", ":"))}, TOKEN)


async def seed(db: Database, bot: Bot, cfg: Config) -> dict:
    now = utcnow()
    await db.create_user(SUPER, "998900000100", "Bosh Admin", None, role="admin")
    await db.create_user(ADMIN, "998900000200", "Karimova Nodira", None, role="admin")
    for uid, name in USTOZ.items():
        await db.create_user(uid, f"99890000{uid:04d}", name, None)
    g = await db.create_group("Attestatsiya 1-guruh", SUPER)
    await db.assign_admin(g.id, ADMIN)
    for uid in USTOZ:
        await db.add_member(g.id, uid, now - timedelta(days=10))

    # 1) yakunlangan test
    t1 = await db.create_test(g.id, "1-hafta: Logarifmlar", "ABCDABCDABCDABCDABCD", None, None, ADMIN)
    await db.publish_test(t1.id, now - timedelta(days=3), now + timedelta(days=1))
    t1 = await db.get_test(t1.id)
    answers = {301: "ABCDABCDABCDABCDABCD", 302: "ABCDABCDABCAABCDABCA", 303: "ABCCABCDABBAABCDDBCD",
               304: "ABCDABDDABCAABCDABCD", 305: "BBCDABCDCBCAABCDABCB", 306: "ABCDABCD-BCAABCDA---"}
    for uid, a in answers.items():
        await services.submit(db, cfg, t1, await db.get_user(uid), a, now - timedelta(days=2))
    await services.close(bot, db, cfg, t1, now - timedelta(hours=2))

    # 2) faol test
    t2 = await db.create_test(g.id, "2-hafta: Trigonometriya", "CADBBCADDACBBACDCABD" + "ACBDABCDCA", None, None, ADMIN)
    await db.publish_test(t2.id, now - timedelta(hours=5), now + timedelta(hours=19))
    t2 = await db.get_test(t2.id)
    for uid, a in {302: "CADBBCADDACBBACDCABDACBDABCDCA", 303: "CADBACADDACBBACDCABDACBDABCDAA",
                   305: "CADBBCADDBCBBACDCABDACBDABCDCB"}.items():
        await services.submit(db, cfg, t2, await db.get_user(uid), a, now - timedelta(hours=1))
    await db.add_coins(301, g.id, 3, "Faol qatnashgani uchun", now, created_by=ADMIN)
    return {"group": g.id, "closed": t1.id, "active": t2.id}
