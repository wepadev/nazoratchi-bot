import asyncio

from bot.db import CODE_ALPHABET, CODE_LENGTH, Database, normalize_phone


def run(coro):
    return asyncio.run(coro)


def test_normalize_phone():
    assert normalize_phone("+998 90 123-45-67") == "+998901234567"
    assert normalize_phone("901234567") == "+998901234567"
    assert normalize_phone("998901234567") == "+998901234567"


def test_full_flow():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        admin = await db.create_user(1, "998900000001", "Admin Bir", "adm", role="admin")
        u = await db.create_user(2, "+998900000002", "Talaba Ikki", None)
        assert admin.is_admin and not u.is_admin
        assert (await db.get_user_by_phone("90 000 00 02")).id == 2

        g = await db.create_group("Matematika 9-A", admin.id)
        assert len(g.code) == CODE_LENGTH and set(g.code) <= set(CODE_ALPHABET)

        found = await db.get_group_by_code(" " + g.code.lower() + " ")
        assert found and found.id == g.id

        assert await db.add_member(g.id, u.id) is True
        assert await db.add_member(g.id, u.id) is False
        assert (await db.get_group(g.id)).member_count == 1
        assert [x.id for x in await db.user_groups(u.id)] == [g.id]

        old = g.code
        new = await db.regenerate_code(g.id)
        assert new != old and await db.get_group_by_code(old) is None

        assert len(await db.list_groups(admin.id)) == 1
        assert len(await db.list_groups(999)) == 0
        assert len(await db.list_groups()) == 1

        await db.delete_group(g.id)
        assert await db.user_groups(u.id) == []

        await db.set_role(2, "admin")
        assert [a.id for a in await db.list_admins()] == [1, 2]
        await db.close()

    run(scenario())
