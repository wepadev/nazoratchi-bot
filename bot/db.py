"""SQLite ma'lumotlar bazasi bilan ishlash. Vaqtlar UTC, 'YYYY-MM-DD HH:MM:SS' ko'rinishida."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime

import aiosqlite

from .timeutil import from_db, to_db

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # chalkash belgilarsiz (0/O, 1/I)
CODE_LENGTH = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,                -- Telegram user id
    phone       TEXT    NOT NULL,
    full_name   TEXT    NOT NULL,
    username    TEXT,
    role        TEXT    NOT NULL DEFAULT 'user',    -- 'user' (ustoz) | 'admin' (nazoratchi)
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    code        TEXT    NOT NULL UNIQUE,
    created_by  INTEGER NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- guruhga tayinlangan nazoratchilar
CREATE TABLE IF NOT EXISTS group_admins (
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    admin_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (group_id, admin_id)
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS tests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id        INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    answer_key      TEXT    NOT NULL,                 -- 'ABCD...'
    file_id         TEXT,
    file_type       TEXT,                             -- 'document' | 'photo'
    status          TEXT    NOT NULL DEFAULT 'draft', -- draft | queued | published | closed
    queue_hours     INTEGER,                          -- navbatdagi test uchun davomiylik
    queued_at       TEXT,
    created_by      INTEGER NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    published_at    TEXT,
    deadline_at     TEXT,
    reminded_at     TEXT,
    final_reminded  INTEGER NOT NULL DEFAULT 0,
    closed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_tests_group ON tests(group_id, status);

CREATE TABLE IF NOT EXISTS submissions (
    test_id      INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answers      TEXT    NOT NULL,
    correct      INTEGER NOT NULL,
    submitted_at TEXT    NOT NULL,
    PRIMARY KEY (test_id, user_id)
);

-- tanga harakatlari: har bir tanga sababi bilan
CREATE TABLE IF NOT EXISTS coins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    test_id     INTEGER REFERENCES tests(id) ON DELETE SET NULL,
    lesson_id   INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    amount      INTEGER NOT NULL,
    reason      TEXT    NOT NULL,
    created_by  INTEGER,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coins_group ON coins(group_id, created_at);

CREATE TABLE IF NOT EXISTS appeals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id      INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question     INTEGER,
    text         TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'open',   -- open | accepted | rejected
    resolved_by  INTEGER,
    created_at   TEXT    NOT NULL,
    resolved_at  TEXT
);

-- jonli darslar: nazoratchi kod qo'yadi, ustozlar dars oxirida kiritadi
CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    code        TEXT    NOT NULL,                 -- 4 xonali
    created_by  INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,
    closes_at   TEXT    NOT NULL,                 -- kod shu vaqtgacha ishlaydi
    closed_at   TEXT                              -- yakuniy hisobot yuborilgan vaqt
);
CREATE INDEX IF NOT EXISTS idx_lessons_group ON lessons(group_id, created_at);

CREATE TABLE IF NOT EXISTS attendance (
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    marked_at   TEXT    NOT NULL,
    marked_by   INTEGER,                          -- qo'lda belgilagan nazoratchi (aks holda NULL)
    PRIMARY KEY (lesson_id, user_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
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
    member_count: int = 0


@dataclass
class Test:
    id: int
    group_id: int
    title: str
    answer_key: str
    file_id: str | None
    file_type: str | None
    status: str
    queue_hours: int | None
    created_by: int
    published_at: datetime | None
    deadline_at: datetime | None
    reminded_at: datetime | None
    final_reminded: bool
    closed_at: datetime | None

    @property
    def n(self) -> int:
        return len(self.answer_key)


@dataclass
class Submission:
    test_id: int
    user_id: int
    answers: str
    correct: int
    submitted_at: datetime


@dataclass
class Appeal:
    id: int
    test_id: int
    user_id: int
    question: int | None
    text: str
    status: str
    created_at: datetime


@dataclass
class Lesson:
    id: int
    group_id: int
    title: str
    code: str
    created_by: int
    created_at: datetime
    closes_at: datetime
    closed_at: datetime | None

    def is_open(self, now: datetime) -> bool:
        return self.closed_at is None and self.closes_at > now


_USER_COLS = "u.id, u.phone, u.full_name, u.username, u.role"
_LESSON_COLS = "l.id, l.group_id, l.title, l.code, l.created_by, l.created_at, l.closes_at, l.closed_at"


def _lesson(row) -> Lesson:
    d = dict(row)
    for k in ("created_at", "closes_at", "closed_at"):
        d[k] = from_db(d[k])
    return Lesson(**d)
_TEST_COLS = ("id, group_id, title, answer_key, file_id, file_type, status, queue_hours, created_by, "
              "published_at, deadline_at, reminded_at, final_reminded, closed_at")


def _user(row) -> User:
    return User(id=row["id"], phone=row["phone"], full_name=row["full_name"],
                username=row["username"], role=row["role"])


def _test(row) -> Test:
    d = dict(row)
    for k in ("published_at", "deadline_at", "reminded_at", "closed_at"):
        d[k] = from_db(d[k])
    d["final_reminded"] = bool(d["final_reminded"])
    return Test(**{k: d[k] for k in Test.__dataclass_fields__})


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
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Eski bazalarga yangi ustunlarni qo'shadi (ma'lumot o'chmaydi)."""
        cur = await self._conn.execute("PRAGMA table_info(coins)")
        cols = {r["name"] for r in await cur.fetchall()}
        if "lesson_id" not in cols:
            await self._conn.execute(
                "ALTER TABLE coins ADD COLUMN lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() chaqirilmagan"
        return self._conn

    async def _all(self, sql: str, params=()) -> list:
        cur = await self.conn.execute(sql, params)
        return list(await cur.fetchall())

    async def _one(self, sql: str, params=()):
        cur = await self.conn.execute(sql, params)
        return await cur.fetchone()

    async def _exec(self, sql: str, params=()) -> aiosqlite.Cursor:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur

    # ================= users =================
    async def get_user(self, user_id: int) -> User | None:
        row = await self._one(f"SELECT {_USER_COLS} FROM users u WHERE u.id = ?", (user_id,))
        return _user(row) if row else None

    async def get_user_by_phone(self, phone: str) -> User | None:
        row = await self._one(f"SELECT {_USER_COLS} FROM users u WHERE u.phone = ?",
                              (normalize_phone(phone),))
        return _user(row) if row else None

    async def create_user(self, user_id: int, phone: str, full_name: str, username: str | None,
                          role: str = "user") -> User:
        await self._exec(
            """INSERT INTO users (id, phone, full_name, username, role) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET phone=excluded.phone, full_name=excluded.full_name,
                                             username=excluded.username""",
            (user_id, normalize_phone(phone), full_name, username, role),
        )
        user = await self.get_user(user_id)
        assert user
        return user

    async def set_role(self, user_id: int, role: str) -> None:
        await self._exec("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if role != "admin":
            await self._exec("DELETE FROM group_admins WHERE admin_id = ?", (user_id,))

    async def list_admins(self) -> list[User]:
        rows = await self._all(f"SELECT {_USER_COLS} FROM users u WHERE u.role = 'admin' ORDER BY u.full_name")
        return [_user(r) for r in rows]

    # ================= groups =================
    _GROUP_SELECT = """
        SELECT g.id, g.name, g.code,
               (SELECT COUNT(*) FROM group_members m WHERE m.group_id = g.id) AS member_count
        FROM groups g
    """

    async def _unique_code(self) -> str:
        while True:
            code = generate_code()
            if not await self._one("SELECT 1 FROM groups WHERE code = ?", (code,)):
                return code

    async def create_group(self, name: str, created_by: int) -> Group:
        code = await self._unique_code()
        cur = await self._exec("INSERT INTO groups (name, code, created_by) VALUES (?, ?, ?)",
                               (name, code, created_by))
        return Group(id=cur.lastrowid, name=name, code=code)

    async def get_group(self, group_id: int) -> Group | None:
        row = await self._one(self._GROUP_SELECT + " WHERE g.id = ?", (group_id,))
        return Group(**dict(row)) if row else None

    async def get_group_by_code(self, code: str) -> Group | None:
        row = await self._one(self._GROUP_SELECT + " WHERE g.code = ?", (code.strip().upper(),))
        return Group(**dict(row)) if row else None

    async def list_groups(self, admin_id: int | None = None) -> list[Group]:
        """admin_id berilmasa — barcha guruhlar (bosh admin uchun), aks holda nazoratchiga tayinlanganlari."""
        if admin_id is None:
            rows = await self._all(self._GROUP_SELECT + " ORDER BY g.id DESC")
        else:
            rows = await self._all(
                self._GROUP_SELECT
                + " JOIN group_admins ga ON ga.group_id = g.id WHERE ga.admin_id = ? ORDER BY g.id DESC",
                (admin_id,),
            )
        return [Group(**dict(r)) for r in rows]

    async def regenerate_code(self, group_id: int) -> str:
        code = await self._unique_code()
        await self._exec("UPDATE groups SET code = ? WHERE id = ?", (code, group_id))
        return code

    async def rename_group(self, group_id: int, name: str) -> None:
        await self._exec("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))

    async def delete_group(self, group_id: int) -> None:
        await self._exec("DELETE FROM groups WHERE id = ?", (group_id,))

    # ---- nazoratchilar ----
    async def assign_admin(self, group_id: int, admin_id: int) -> None:
        await self._exec("INSERT OR IGNORE INTO group_admins (group_id, admin_id) VALUES (?, ?)",
                         (group_id, admin_id))

    async def unassign_admin(self, group_id: int, admin_id: int) -> None:
        await self._exec("DELETE FROM group_admins WHERE group_id = ? AND admin_id = ?", (group_id, admin_id))

    async def group_admins(self, group_id: int) -> list[User]:
        rows = await self._all(
            f"SELECT {_USER_COLS} FROM group_admins ga JOIN users u ON u.id = ga.admin_id "
            "WHERE ga.group_id = ? ORDER BY u.full_name", (group_id,))
        return [_user(r) for r in rows]

    async def is_group_admin(self, group_id: int, admin_id: int) -> bool:
        return bool(await self._one("SELECT 1 FROM group_admins WHERE group_id = ? AND admin_id = ?",
                                    (group_id, admin_id)))

    # ---- a'zolar (ustozlar) ----
    async def add_member(self, group_id: int, user_id: int, now: datetime) -> bool:
        cur = await self._exec(
            "INSERT OR IGNORE INTO group_members (group_id, user_id, joined_at) VALUES (?, ?, ?)",
            (group_id, user_id, to_db(now)))
        return cur.rowcount > 0

    async def remove_member(self, group_id: int, user_id: int) -> None:
        await self._exec("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))

    async def is_member(self, group_id: int, user_id: int) -> bool:
        return bool(await self._one("SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
                                    (group_id, user_id)))

    async def list_members(self, group_id: int) -> list[User]:
        rows = await self._all(
            f"SELECT {_USER_COLS} FROM group_members m JOIN users u ON u.id = m.user_id "
            "WHERE m.group_id = ? ORDER BY u.full_name", (group_id,))
        return [_user(r) for r in rows]

    async def user_groups(self, user_id: int) -> list[Group]:
        rows = await self._all(
            self._GROUP_SELECT
            + " JOIN group_members gm ON gm.group_id = g.id WHERE gm.user_id = ? ORDER BY gm.joined_at",
            (user_id,))
        return [Group(**dict(r)) for r in rows]

    # ================= tests =================
    async def create_test(self, group_id: int, title: str, answer_key: str, file_id: str | None,
                          file_type: str | None, created_by: int) -> Test:
        cur = await self._exec(
            "INSERT INTO tests (group_id, title, answer_key, file_id, file_type, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)", (group_id, title, answer_key, file_id, file_type, created_by))
        test = await self.get_test(cur.lastrowid)
        assert test
        return test

    async def get_test(self, test_id: int) -> Test | None:
        row = await self._one(f"SELECT {_TEST_COLS} FROM tests WHERE id = ?", (test_id,))
        return _test(row) if row else None

    async def list_tests(self, group_id: int, limit: int = 30) -> list[Test]:
        rows = await self._all(
            f"""SELECT {_TEST_COLS} FROM tests WHERE group_id = ?
                ORDER BY CASE status WHEN 'published' THEN 0 WHEN 'queued' THEN 1 WHEN 'draft' THEN 2 ELSE 3 END,
                         COALESCE(queued_at, published_at, created_at) DESC, id DESC LIMIT ?""",
            (group_id, limit))
        return [_test(r) for r in rows]

    async def closed_tests(self, group_id: int) -> list[Test]:
        rows = await self._all(
            f"SELECT {_TEST_COLS} FROM tests WHERE group_id = ? AND status IN ('published','closed') "
            "ORDER BY published_at", (group_id,))
        return [_test(r) for r in rows]

    async def active_test(self, group_id: int) -> Test | None:
        row = await self._one(f"SELECT {_TEST_COLS} FROM tests WHERE group_id = ? AND status = 'published'",
                              (group_id,))
        return _test(row) if row else None

    async def next_queued(self, group_id: int) -> Test | None:
        row = await self._one(
            f"SELECT {_TEST_COLS} FROM tests WHERE group_id = ? AND status = 'queued' "
            "ORDER BY queued_at, id LIMIT 1", (group_id,))
        return _test(row) if row else None

    async def queue_test(self, test_id: int, hours: int, now: datetime) -> None:
        await self._exec("UPDATE tests SET status='queued', queue_hours=?, queued_at=? WHERE id=?",
                         (hours, to_db(now), test_id))

    async def unqueue_test(self, test_id: int) -> None:
        await self._exec("UPDATE tests SET status='draft', queue_hours=NULL, queued_at=NULL "
                         "WHERE id=? AND status='queued'", (test_id,))

    async def publish_test(self, test_id: int, now: datetime, deadline: datetime) -> bool:
        cur = await self._exec(
            """UPDATE tests SET status='published', published_at=?, deadline_at=?, reminded_at=?
               WHERE id=? AND status IN ('draft','queued')
                 AND NOT EXISTS (SELECT 1 FROM tests t2 WHERE t2.group_id = tests.group_id
                                 AND t2.status='published')""",
            (to_db(now), to_db(deadline), to_db(now), test_id))
        return cur.rowcount > 0

    async def close_test(self, test_id: int, now: datetime) -> bool:
        cur = await self._exec("UPDATE tests SET status='closed', closed_at=? WHERE id=? AND status='published'",
                               (to_db(now), test_id))
        return cur.rowcount > 0

    async def due_tests(self, now: datetime) -> list[Test]:
        rows = await self._all(f"SELECT {_TEST_COLS} FROM tests WHERE status='published' AND deadline_at <= ?",
                               (to_db(now),))
        return [_test(r) for r in rows]

    async def published_tests(self) -> list[Test]:
        rows = await self._all(f"SELECT {_TEST_COLS} FROM tests WHERE status='published'")
        return [_test(r) for r in rows]

    async def set_reminded(self, test_id: int, now: datetime, final: bool = False) -> None:
        if final:
            await self._exec("UPDATE tests SET reminded_at=?, final_reminded=1 WHERE id=?", (to_db(now), test_id))
        else:
            await self._exec("UPDATE tests SET reminded_at=? WHERE id=?", (to_db(now), test_id))

    async def update_test(self, test_id: int, **fields) -> None:
        allowed = {"title", "answer_key", "file_id", "file_type", "deadline_at"}
        assert set(fields) <= allowed
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = [to_db(v) if isinstance(v, datetime) else v for v in fields.values()]
        await self._exec(f"UPDATE tests SET {sets} WHERE id = ?", (*values, test_id))

    async def delete_test(self, test_id: int) -> None:
        await self._exec("DELETE FROM tests WHERE id = ? AND status IN ('draft','queued')", (test_id,))

    async def user_open_tests(self, user_id: int) -> list[Test]:
        """Foydalanuvchi guruhlaridagi faol testlar (topshirilgan-topshirilmaganidan qat'i nazar)."""
        rows = await self._all(
            f"""SELECT {', '.join('t.' + c.strip() for c in _TEST_COLS.split(','))}
                FROM tests t JOIN group_members m ON m.group_id = t.group_id
                WHERE m.user_id = ? AND t.status = 'published' ORDER BY t.deadline_at""", (user_id,))
        return [_test(r) for r in rows]

    # ================= submissions =================
    async def submit(self, test_id: int, user_id: int, answers: str, correct: int, now: datetime) -> bool:
        """Faqat test faol va muddati o'tmagan bo'lsa, bir marta qabul qilinadi."""
        cur = await self._exec(
            """INSERT OR IGNORE INTO submissions (test_id, user_id, answers, correct, submitted_at)
               SELECT ?, ?, ?, ?, ? WHERE EXISTS (
                   SELECT 1 FROM tests WHERE id = ? AND status = 'published' AND deadline_at > ?)""",
            (test_id, user_id, answers, correct, to_db(now), test_id, to_db(now)))
        return cur.rowcount > 0

    async def get_submission(self, test_id: int, user_id: int) -> Submission | None:
        row = await self._one("SELECT * FROM submissions WHERE test_id = ? AND user_id = ?", (test_id, user_id))
        if not row:
            return None
        d = dict(row)
        d["submitted_at"] = from_db(d["submitted_at"])
        return Submission(**d)

    async def list_submissions(self, test_id: int) -> list[Submission]:
        rows = await self._all("SELECT * FROM submissions WHERE test_id = ?", (test_id,))
        out = []
        for r in rows:
            d = dict(r)
            d["submitted_at"] = from_db(d["submitted_at"])
            out.append(Submission(**d))
        return out

    async def set_submission_correct(self, test_id: int, user_id: int, correct: int) -> None:
        await self._exec("UPDATE submissions SET correct = ? WHERE test_id = ? AND user_id = ?",
                         (correct, test_id, user_id))

    async def non_submitters(self, test: Test, only_before_publish: bool) -> list[User]:
        """Topshirmagan a'zolar. only_before_publish — faqat test nashr qilinishidan oldin qo'shilganlar
        (keyin qo'shilganlarga jarima berilmaydi)."""
        sql = (f"SELECT {_USER_COLS} FROM group_members m JOIN users u ON u.id = m.user_id "
               "WHERE m.group_id = ? AND NOT EXISTS "
               "(SELECT 1 FROM submissions s WHERE s.test_id = ? AND s.user_id = m.user_id)")
        params: list = [test.group_id, test.id]
        if only_before_publish and test.published_at:
            sql += " AND m.joined_at <= ?"
            params.append(to_db(test.published_at))
        rows = await self._all(sql + " ORDER BY u.full_name", params)
        return [_user(r) for r in rows]

    async def member_joined_at(self, group_id: int, user_id: int) -> datetime | None:
        row = await self._one("SELECT joined_at FROM group_members WHERE group_id = ? AND user_id = ?",
                              (group_id, user_id))
        return from_db(row["joined_at"]) if row else None

    # ================= coins =================
    async def add_coins(self, user_id: int, group_id: int, amount: int, reason: str, now: datetime,
                        test_id: int | None = None, created_by: int | None = None,
                        lesson_id: int | None = None) -> None:
        await self._exec(
            "INSERT INTO coins (user_id, group_id, test_id, lesson_id, amount, reason, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, group_id, test_id, lesson_id, amount, reason, created_by, to_db(now)))

    async def lesson_coins(self, lesson_id: int, user_id: int) -> int:
        row = await self._one("SELECT COALESCE(SUM(amount), 0) AS s FROM coins WHERE lesson_id = ? AND user_id = ?",
                              (lesson_id, user_id))
        return row["s"]

    async def rating(self, group_id: int, since: datetime | None = None,
                     until: datetime | None = None) -> list[tuple[User, int]]:
        """Guruh a'zolari reytingi (tangalar yig'indisi bo'yicha, kamayish tartibida)."""
        s = to_db(since) if since else None
        u = to_db(until) if until else None
        rows = await self._all(
            f"""SELECT {_USER_COLS}, COALESCE(SUM(c.amount), 0) AS coins
                FROM group_members m JOIN users u ON u.id = m.user_id
                LEFT JOIN coins c ON c.user_id = m.user_id AND c.group_id = m.group_id
                     AND (? IS NULL OR c.created_at >= ?) AND (? IS NULL OR c.created_at < ?)
                WHERE m.group_id = ?
                GROUP BY u.id ORDER BY coins DESC, u.full_name""",
            (s, s, u, u, group_id))
        return [(_user(r), r["coins"]) for r in rows]

    async def coin_history(self, group_id: int, user_id: int | None = None, limit: int = 1000) -> list[dict]:
        sql = ("SELECT c.created_at, c.amount, c.reason, u.full_name, u.phone, c.user_id "
               "FROM coins c JOIN users u ON u.id = c.user_id WHERE c.group_id = ?")
        params: list = [group_id]
        if user_id is not None:
            sql += " AND c.user_id = ?"
            params.append(user_id)
        rows = await self._all(sql + " ORDER BY c.id DESC LIMIT ?", (*params, limit))
        return [dict(r) | {"created_at": from_db(r["created_at"])} for r in rows]

    async def has_activity(self, group_id: int, since: datetime, until: datetime) -> bool:
        return bool(await self._one(
            "SELECT 1 FROM coins WHERE group_id = ? AND created_at >= ? AND created_at < ? LIMIT 1",
            (group_id, to_db(since), to_db(until))))

    # ================= appeals =================
    async def create_appeal(self, test_id: int, user_id: int, question: int | None, text: str,
                            now: datetime) -> int:
        cur = await self._exec(
            "INSERT INTO appeals (test_id, user_id, question, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (test_id, user_id, question, text, to_db(now)))
        return cur.lastrowid

    async def get_appeal(self, appeal_id: int) -> Appeal | None:
        row = await self._one("SELECT id, test_id, user_id, question, text, status, created_at FROM appeals "
                              "WHERE id = ?", (appeal_id,))
        if not row:
            return None
        d = dict(row)
        d["created_at"] = from_db(d["created_at"])
        return Appeal(**d)

    async def open_appeals(self, admin_id: int | None) -> list[Appeal]:
        sql = ("SELECT a.id, a.test_id, a.user_id, a.question, a.text, a.status, a.created_at FROM appeals a "
               "JOIN tests t ON t.id = a.test_id WHERE a.status = 'open'")
        params: tuple = ()
        if admin_id is not None:
            sql += " AND t.group_id IN (SELECT group_id FROM group_admins WHERE admin_id = ?)"
            params = (admin_id,)
        rows = await self._all(sql + " ORDER BY a.id", params)
        out = []
        for r in rows:
            d = dict(r)
            d["created_at"] = from_db(d["created_at"])
            out.append(Appeal(**d))
        return out

    async def resolve_appeal(self, appeal_id: int, status: str, admin_id: int, now: datetime) -> bool:
        cur = await self._exec(
            "UPDATE appeals SET status = ?, resolved_by = ?, resolved_at = ? WHERE id = ? AND status = 'open'",
            (status, admin_id, to_db(now), appeal_id))
        return cur.rowcount > 0

    # ================= statistika =================
    async def user_test_stats(self, user_id: int, group_id: int) -> tuple[int, float | None]:
        """(topshirgan testlar soni, o'rtacha foiz)"""
        row = await self._one(
            """SELECT COUNT(*) AS cnt, AVG(100.0 * s.correct / LENGTH(t.answer_key)) AS avg
               FROM submissions s JOIN tests t ON t.id = s.test_id
               WHERE s.user_id = ? AND t.group_id = ?""", (user_id, group_id))
        return row["cnt"], row["avg"]

    async def admin_activity(self) -> list[dict]:
        rows = await self._all(
            """SELECT u.id, u.full_name,
                 (SELECT COUNT(*) FROM group_admins ga WHERE ga.admin_id = u.id) AS groups,
                 (SELECT COUNT(*) FROM tests t WHERE t.created_by = u.id) AS tests_created,
                 (SELECT COUNT(*) FROM tests t WHERE t.created_by = u.id
                        AND t.status IN ('published','closed')) AS tests_published,
                 (SELECT MAX(t.created_at) FROM tests t WHERE t.created_by = u.id) AS last_test,
                 (SELECT COUNT(*) FROM appeals a WHERE a.resolved_by = u.id) AS appeals_resolved,
                 (SELECT AVG((julianday(a.resolved_at) - julianday(a.created_at)) * 24)
                        FROM appeals a WHERE a.resolved_by = u.id) AS avg_resolve_hours,
                 (SELECT COUNT(*) FROM appeals a JOIN tests t ON t.id = a.test_id
                        WHERE a.status = 'open' AND t.group_id IN
                          (SELECT group_id FROM group_admins WHERE admin_id = u.id)) AS appeals_open,
                 (SELECT COUNT(*) FROM coins c WHERE c.created_by = u.id) AS manual_coins
               FROM users u WHERE u.role = 'admin' ORDER BY u.full_name""")
        return [dict(r) | {"last_test": from_db(r["last_test"])} for r in rows]

    # ================= jonli darslar =================
    async def create_lesson(self, group_id: int, title: str, code: str, created_by: int, now: datetime,
                            closes_at: datetime) -> Lesson:
        cur = await self._exec(
            "INSERT INTO lessons (group_id, title, code, created_by, created_at, closes_at) VALUES (?, ?, ?, ?, ?, ?)",
            (group_id, title, code, created_by, to_db(now), to_db(closes_at)))
        lesson = await self.get_lesson(cur.lastrowid)
        assert lesson
        return lesson

    async def get_lesson(self, lesson_id: int) -> Lesson | None:
        row = await self._one(f"SELECT {_LESSON_COLS} FROM lessons l WHERE l.id = ?", (lesson_id,))
        return _lesson(row) if row else None

    async def list_lessons(self, group_id: int, limit: int = 500) -> list[Lesson]:
        rows = await self._all(f"SELECT {_LESSON_COLS} FROM lessons l WHERE l.group_id = ? "
                               "ORDER BY l.created_at DESC, l.id DESC LIMIT ?", (group_id, limit))
        return [_lesson(r) for r in rows]

    async def open_code_in_group(self, group_id: int, code: str, now: datetime) -> bool:
        return bool(await self._one(
            "SELECT 1 FROM lessons WHERE group_id = ? AND code = ? AND closed_at IS NULL AND closes_at > ?",
            (group_id, code, to_db(now))))

    async def open_lessons_by_code(self, user_id: int, code: str, now: datetime) -> list[Lesson]:
        """Foydalanuvchi guruhlaridagi, kodi mos va hali ochiq darslar."""
        rows = await self._all(
            f"""SELECT {_LESSON_COLS} FROM lessons l JOIN group_members m ON m.group_id = l.group_id
                WHERE m.user_id = ? AND l.code = ? AND l.closed_at IS NULL AND l.closes_at > ?""",
            (user_id, code, to_db(now)))
        return [_lesson(r) for r in rows]

    async def due_lessons(self, now: datetime) -> list[Lesson]:
        rows = await self._all(f"SELECT {_LESSON_COLS} FROM lessons l WHERE l.closed_at IS NULL AND l.closes_at <= ?",
                               (to_db(now),))
        return [_lesson(r) for r in rows]

    async def close_lesson(self, lesson_id: int, now: datetime) -> bool:
        """Kodni yopadi; muddatidan oldin yopilsa closes_at ham qisqaradi."""
        cur = await self._exec(
            "UPDATE lessons SET closed_at = ?, closes_at = MIN(closes_at, ?) WHERE id = ? AND closed_at IS NULL",
            (to_db(now), to_db(now), lesson_id))
        return cur.rowcount > 0

    async def delete_lesson(self, lesson_id: int) -> None:
        """Dars, uning davomati va shu dars uchun berilgan tangalar o'chadi."""
        await self._exec("DELETE FROM coins WHERE lesson_id = ?", (lesson_id,))
        await self._exec("DELETE FROM lessons WHERE id = ?", (lesson_id,))

    async def mark_attendance(self, lesson_id: int, user_id: int, now: datetime,
                              marked_by: int | None = None) -> bool:
        cur = await self._exec(
            "INSERT OR IGNORE INTO attendance (lesson_id, user_id, marked_at, marked_by) VALUES (?, ?, ?, ?)",
            (lesson_id, user_id, to_db(now), marked_by))
        return cur.rowcount > 0

    async def unmark_attendance(self, lesson_id: int, user_id: int) -> None:
        await self._exec("DELETE FROM attendance WHERE lesson_id = ? AND user_id = ?", (lesson_id, user_id))

    async def lesson_present_ids(self, lesson_id: int) -> set[int]:
        rows = await self._all("SELECT user_id FROM attendance WHERE lesson_id = ?", (lesson_id,))
        return {r["user_id"] for r in rows}

    async def lesson_roster(self, lesson: Lesson) -> list[tuple[User, bool]]:
        """Dars vaqtida guruhda bo'lgan a'zolar va ular qatnashganmi (dars yopilgandan keyin qo'shilganlar kirmaydi)."""
        rows = await self._all(
            f"""SELECT {_USER_COLS}, EXISTS(SELECT 1 FROM attendance a WHERE a.lesson_id = ? AND a.user_id = u.id) AS present
                FROM group_members m JOIN users u ON u.id = m.user_id
                WHERE m.group_id = ? AND m.joined_at <= ?
                ORDER BY u.full_name""",
            (lesson.id, lesson.group_id, to_db(lesson.closes_at)))
        return [(_user(r), bool(r["present"])) for r in rows]

    async def attendance_matrix(self, group_id: int) -> tuple[list[Lesson], list[tuple[User, datetime | None]], set[tuple[int, int]]]:
        """(darslar eskidan yangiga, a'zolar + qo'shilgan vaqti, {(lesson_id, user_id)} qatnashganlar)."""
        lessons = list(reversed(await self.list_lessons(group_id)))
        rows = await self._all(
            f"SELECT {_USER_COLS}, m.joined_at FROM group_members m JOIN users u ON u.id = m.user_id "
            "WHERE m.group_id = ? ORDER BY u.full_name", (group_id,))
        members = [(_user(r), from_db(r["joined_at"])) for r in rows]
        att = await self._all("SELECT a.lesson_id, a.user_id FROM attendance a JOIN lessons l ON l.id = a.lesson_id "
                              "WHERE l.group_id = ?", (group_id,))
        return lessons, members, {(r["lesson_id"], r["user_id"]) for r in att}

    # ================= settings =================
    async def get_setting(self, key: str) -> str | None:
        row = await self._one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._exec("INSERT INTO settings (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
