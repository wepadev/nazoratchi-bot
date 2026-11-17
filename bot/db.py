"""SQLite ma'lumotlar bazasi bilan ishlash."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

import aiosqlite

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # chalkash belgilarsiz (0/O, 1/I)
CODE_LENGTH = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,          -- Telegram user id
    phone       TEXT    NOT NULL,
    full_name   TEXT    NOT NULL,
    username    TEXT,
    role        TEXT    NOT NULL DEFAULT 'user',   -- 'user' | 'admin'
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    code        TEXT    NOT NULL UNIQUE,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (group_id, user_id)
);
"""


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 9:  # 901234567 -> 998901234567
        digits = "998" + digits
    return "+" + digits


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


@dataclass
class User:
    id: int
    phone: str
    full_name: str
    username: str | None
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass
class Group:
    id: int
    name: str
    code: str
    owner_id: int
    member_count: int = 0


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() chaqirilmagan"
        return self._conn

    # ---------- users ----------
    async def get_user(self, user_id: int) -> User | None:
        cur = await self.conn.execute(
            "SELECT id, phone, full_name, username, role FROM users WHERE id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return User(**dict(row)) if row else None

    async def get_user_by_phone(self, phone: str) -> User | None:
        cur = await self.conn.execute(
            "SELECT id, phone, full_name, username, role FROM users WHERE phone = ?",
            (normalize_phone(phone),),
        )
        row = await cur.fetchone()
        return User(**dict(row)) if row else None

    async def create_user(
        self, user_id: int, phone: str, full_name: str, username: str | None, role: str = "user"
    ) -> User:
        phone = normalize_phone(phone)
        await self.conn.execute(
            """INSERT INTO users (id, phone, full_name, username, role) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET phone=excluded.phone, full_name=excluded.full_name,
                                             username=excluded.username""",
            (user_id, phone, full_name, username, role),
        )
        await self.conn.commit()
        user = await self.get_user(user_id)
        assert user
        return user

    async def set_role(self, user_id: int, role: str) -> None:
        await self.conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        await self.conn.commit()

    async def list_admins(self) -> list[User]:
        cur = await self.conn.execute(
            "SELECT id, phone, full_name, username, role FROM users WHERE role = 'admin' ORDER BY full_name"
        )
        return [User(**dict(r)) for r in await cur.fetchall()]

    # ---------- groups ----------
    async def _unique_code(self) -> str:
        while True:
            code = generate_code()
            cur = await self.conn.execute("SELECT 1 FROM groups WHERE code = ?", (code,))
            if not await cur.fetchone():
                return code

    async def create_group(self, name: str, owner_id: int) -> Group:
        code = await self._unique_code()
        cur = await self.conn.execute(
            "INSERT INTO groups (name, code, owner_id) VALUES (?, ?, ?)", (name, code, owner_id)
        )
        await self.conn.commit()
        return Group(id=cur.lastrowid, name=name, code=code, owner_id=owner_id)

    _GROUP_SELECT = """
        SELECT g.id, g.name, g.code, g.owner_id,
               (SELECT COUNT(*) FROM group_members m WHERE m.group_id = g.id) AS member_count
        FROM groups g
    """

    async def get_group(self, group_id: int) -> Group | None:
        cur = await self.conn.execute(self._GROUP_SELECT + " WHERE g.id = ?", (group_id,))
        row = await cur.fetchone()
        return Group(**dict(row)) if row else None

    async def get_group_by_code(self, code: str) -> Group | None:
        cur = await self.conn.execute(
            self._GROUP_SELECT + " WHERE g.code = ?", (code.strip().upper(),)
        )
        row = await cur.fetchone()
        return Group(**dict(row)) if row else None

    async def list_groups(self, owner_id: int | None = None) -> list[Group]:
        """owner_id berilmasa — barcha guruhlar (bosh admin uchun)."""
        if owner_id is None:
            cur = await self.conn.execute(self._GROUP_SELECT + " ORDER BY g.id DESC")
        else:
            cur = await self.conn.execute(
                self._GROUP_SELECT + " WHERE g.owner_id = ? ORDER BY g.id DESC", (owner_id,)
            )
        return [Group(**dict(r)) for r in await cur.fetchall()]

    async def regenerate_code(self, group_id: int) -> str:
        code = await self._unique_code()
        await self.conn.execute("UPDATE groups SET code = ? WHERE id = ?", (code, group_id))
        await self.conn.commit()
        return code

    async def rename_group(self, group_id: int, name: str) -> None:
        await self.conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
        await self.conn.commit()

    async def delete_group(self, group_id: int) -> None:
        await self.conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        await self.conn.commit()

    # ---------- members ----------
    async def add_member(self, group_id: int, user_id: int) -> bool:
        """True — yangi qo'shildi, False — oldin ham a'zo edi."""
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, user_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def remove_member(self, group_id: int, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)
        )
        await self.conn.commit()

    async def list_members(self, group_id: int) -> list[User]:
        cur = await self.conn.execute(
            """SELECT u.id, u.phone, u.full_name, u.username, u.role
               FROM group_members m JOIN users u ON u.id = m.user_id
               WHERE m.group_id = ? ORDER BY m.joined_at""",
            (group_id,),
        )
        return [User(**dict(r)) for r in await cur.fetchall()]

    async def user_groups(self, user_id: int) -> list[Group]:
        cur = await self.conn.execute(
            self._GROUP_SELECT
            + " JOIN group_members gm ON gm.group_id = g.id WHERE gm.user_id = ? ORDER BY gm.joined_at",
            (user_id,),
        )
        return [Group(**dict(r)) for r in await cur.fetchall()]
