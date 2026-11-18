import asyncio
from datetime import timedelta

from bot.db import CODE_ALPHABET, CODE_LENGTH, Database, normalize_phone
from bot.timeutil import utcnow


def test_normalize_phone():
    assert normalize_phone("+998 90 123-45-67") == "+998901234567"
    assert normalize_phone("901234567") == "+998901234567"


def test_groups_tests_coins():
    async def scenario():
        now = utcnow()
        db = Database(":memory:")
        await db.connect()
        await db.create_user(1, "998900000001", "Nazoratchi", None, role="admin")
        await db.create_user(2, "998900000002", "Ustoz A", None)
        await db.create_user(3, "998900000003", "Ustoz B", None)
        g = await db.create_group("9-guruh", 1)
        assert len(g.code) == CODE_LENGTH and set(g.code) <= set(CODE_ALPHABET)
        await db.assign_admin(g.id, 1)
        assert [x.id for x in await db.list_groups(1)] == [g.id]
        assert await db.list_groups(2) == []
        assert await db.add_member(g.id, 2, now) and not await db.add_member(g.id, 2, now)
        await db.add_member(g.id, 3, now)

        t1 = await db.create_test(g.id, "T1", "ABCD", None, None, 1)
        t2 = await db.create_test(g.id, "T2", "AAAA", None, None, 1)
        assert await db.publish_test(t1.id, now, now + timedelta(hours=1))
        assert not await db.publish_test(t2.id, now, now + timedelta(hours=1))  # bir vaqtda bitta faol
        await db.queue_test(t2.id, 24, now)
        assert (await db.next_queued(g.id)).id == t2.id

        assert await db.submit(t1.id, 2, "ABCC", 3, now)
        assert not await db.submit(t1.id, 2, "ABCD", 4, now)  # qayta topshirib bo'lmaydi
        assert not await db.submit(t1.id, 3, "ABCD", 4, now + timedelta(hours=2))  # muddat o'tgan
        assert [u.id for u in await db.non_submitters(await db.get_test(t1.id), True)] == [3]

        await db.add_coins(2, g.id, 3, "T1", now)
        await db.add_coins(3, g.id, -5, "T1 topshirilmadi", now)
        assert [(u.id, c) for u, c in await db.rating(g.id)] == [(2, 3), (3, -5)]
        assert [(u.id, c) for u, c in await db.rating(g.id, since=now + timedelta(seconds=1))] == [(2, 0), (3, 0)]

        assert await db.close_test(t1.id, now) and not await db.close_test(t1.id, now)
        await db.delete_group(g.id)
        assert await db.get_test(t1.id) is None
        await db.close()

    asyncio.run(scenario())
