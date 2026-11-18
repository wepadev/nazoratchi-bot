from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import texts as T

# ---------------- callback data ----------------


class GroupCb(CallbackData, prefix="g"):
    # list|open|members|code|rating|excel|coins|tests|newtest|admins|rename|delete|delete_ok
    action: str
    group_id: int = 0


class AssignCb(CallbackData, prefix="as"):
    group_id: int
    admin_id: int


class MemberCb(CallbackData, prefix="m"):
    action: str  # kick | kick_ok | coin
    group_id: int
    user_id: int


class TestCb(CallbackData, prefix="t"):
    # admin: open|publish|pub|date|unqueue|close|close_ok|stats|fixkey|delete|delete_ok|resend
    # ustoz: answer|confirm|retry|appeal
    action: str
    test_id: int
    arg: int = 0


class RatingCb(CallbackData, prefix="r"):
    group_id: int
    period: str  # all | week | lastweek
    admin: bool = False


class AppealCb(CallbackData, prefix="ap"):
    action: str  # accept | reject | fixkey
    appeal_id: int


class MyGroupCb(CallbackData, prefix="mg"):
    action: str  # leave | leave_ok | rating
    group_id: int


class AdminCb(CallbackData, prefix="a"):
    action: str  # add | remove
    user_id: int = 0


# ---------------- reply klaviaturalar ----------------

def _kb(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t) for t in r] for r in rows],
                               resize_keyboard=True)


def share_phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T.BTN_SHARE_PHONE, request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return _kb([[T.BTN_CANCEL]])


def skip_cancel_kb() -> ReplyKeyboardMarkup:
    return _kb([[T.BTN_SKIP], [T.BTN_CANCEL]])


def main_menu(is_admin: bool, is_super: bool) -> ReplyKeyboardMarkup:
    if is_super:
        return _kb([[T.BTN_GROUPS, T.BTN_CREATE_GROUP],
                    [T.BTN_ADMINS, T.BTN_ACTIVITY],
                    [T.BTN_APPEALS, T.BTN_PROFILE]])
    if is_admin:
        return _kb([[T.BTN_GROUPS, T.BTN_APPEALS], [T.BTN_PROFILE]])
    return _kb([[T.BTN_TESTS, T.BTN_RATING], [T.BTN_JOIN, T.BTN_MY_GROUPS], [T.BTN_PROFILE]])


# ---------------- inline klaviaturalar ----------------

def _build(buttons: list[tuple[str, CallbackData]], adjust: list[int] | int = 1) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for text, cb in buttons:
        b.button(text=text, callback_data=cb)
    b.adjust(*(adjust if isinstance(adjust, list) else [adjust]))
    return b.as_markup()


BACK = "⬅️ Orqaga"


def groups_kb(groups) -> InlineKeyboardMarkup:
    return _build([(f"📁 {g.name} · {g.member_count}", GroupCb(action="open", group_id=g.id)) for g in groups])


def group_kb(group_id: int, is_super: bool) -> InlineKeyboardMarkup:
    g = lambda a: GroupCb(action=a, group_id=group_id)  # noqa: E731
    items = [
        ("📝 Testlar", g("tests")), ("🏆 Reyting", g("rating")),
        ("👥 Ustozlar", g("members")), ("🪙 Tanga berish", g("coins")),
        ("📥 Excel", g("excel")), ("🔄 Yangi kod", g("code")),
    ]
    if is_super:
        items += [("👮 Nazoratchilar", g("admins")), ("✏️ Nomi", g("rename")), ("🗑 O'chirish", g("delete"))]
    items.append((BACK, GroupCb(action="list")))
    return _build(items, 2)


def back_to_group_kb(group_id: int) -> InlineKeyboardMarkup:
    return _build([(BACK, GroupCb(action="open", group_id=group_id))])


def confirm_group_delete_kb(group_id: int) -> InlineKeyboardMarkup:
    return _build([("Ha, o'chirish", GroupCb(action="delete_ok", group_id=group_id)),
                   ("Yo'q", GroupCb(action="open", group_id=group_id))], 2)


def assign_kb(group_id: int, admins, assigned_ids: set[int]) -> InlineKeyboardMarkup:
    items = [(("✅ " if a.id in assigned_ids else "▫️ ") + a.full_name, AssignCb(group_id=group_id, admin_id=a.id))
             for a in admins]
    items.append((BACK, GroupCb(action="open", group_id=group_id)))
    return _build(items)


def members_kb(group_id: int, members, action: str) -> InlineKeyboardMarkup:
    icon = "❌" if action == "kick" else "🪙"
    items = [(f"{icon} {u.full_name}", MemberCb(action=action, group_id=group_id, user_id=u.id))
             for u in members[:90]]
    items.append((BACK, GroupCb(action="open", group_id=group_id)))
    return _build(items)


def confirm_kick_kb(group_id: int, user_id: int) -> InlineKeyboardMarkup:
    return _build([("Ha, chiqarish", MemberCb(action="kick_ok", group_id=group_id, user_id=user_id)),
                   ("Yo'q", GroupCb(action="members", group_id=group_id))], 2)


STATUS_ICON = {"draft": "📄", "queued": "⏳", "published": "🟢", "closed": "✅"}


def tests_kb(group_id: int, tests) -> InlineKeyboardMarkup:
    items = [("➕ Yangi test", GroupCb(action="newtest", group_id=group_id))]
    items += [(f"{STATUS_ICON[t.status]} {t.title}", TestCb(action="open", test_id=t.id)) for t in tests]
    items.append((BACK, GroupCb(action="open", group_id=group_id)))
    return _build(items)


def test_kb(test) -> InlineKeyboardMarkup:
    t = lambda a, arg=0: TestCb(action=a, test_id=test.id, arg=arg)  # noqa: E731
    items: list = []
    if test.status == "draft":
        items += [("🚀 Nashr qilish", t("publish")), ("🗑 O'chirish", t("delete"))]
    elif test.status == "queued":
        items += [("↩️ Navbatdan olish", t("unqueue")), ("🗑 O'chirish", t("delete"))]
    elif test.status == "published":
        items += [("📊 Statistika", t("stats")), ("📣 Qayta yuborish", t("resend")),
                  ("🔑 Kalitni tuzatish", t("fixkey")), ("⏹ Hozir yakunlash", t("close"))]
    else:
        items += [("📊 Statistika", t("stats")), ("🔑 Kalitni tuzatish", t("fixkey"))]
    items.append((BACK, GroupCb(action="tests", group_id=test.group_id)))
    return _build(items, 2)


DURATIONS = [(12, "12 soat"), (24, "1 kun"), (48, "2 kun"), (72, "3 kun"), (168, "1 hafta")]


def publish_kb(test_id: int, queue: bool) -> InlineKeyboardMarkup:
    items = [(label, TestCb(action="pub", test_id=test_id, arg=h)) for h, label in DURATIONS]
    if not queue:
        items.append(("📅 Aniq sana", TestCb(action="date", test_id=test_id)))
    items.append((BACK, TestCb(action="open", test_id=test_id)))
    return _build(items, [3, 2, 1, 1] if not queue else [3, 2, 1])


def confirm_kb(yes: tuple[str, CallbackData], no: tuple[str, CallbackData]) -> InlineKeyboardMarkup:
    return _build([yes, no], 2)


def answer_kb(test_id: int) -> InlineKeyboardMarkup:
    return _build([("✍️ Javob yuborish", TestCb(action="answer", test_id=test_id))])


def confirm_answers_kb(test_id: int) -> InlineKeyboardMarkup:
    return _build([("✅ Tasdiqlash", TestCb(action="confirm", test_id=test_id)),
                   ("✏️ Qayta yozish", TestCb(action="retry", test_id=test_id))], 2)


def appeal_kb(test_id: int) -> InlineKeyboardMarkup:
    return _build([("⚖️ E'tiroz bildirish", TestCb(action="appeal", test_id=test_id))])


def appeal_admin_kb(appeal_id: int) -> InlineKeyboardMarkup:
    return _build([("✅ Qabul (+1 🪙)", AppealCb(action="accept", appeal_id=appeal_id)),
                   ("❌ Rad etish", AppealCb(action="reject", appeal_id=appeal_id)),
                   ("🔑 Kalitni tuzatish", AppealCb(action="fixkey", appeal_id=appeal_id))], [2, 1])


def rating_kb(group_id: int, period: str, admin: bool) -> InlineKeyboardMarkup:
    labels = [("all", "Umumiy"), ("week", "Shu hafta"), ("lastweek", "O'tgan hafta")]
    items = [(("• " if p == period else "") + label, RatingCb(group_id=group_id, period=p, admin=admin))
             for p, label in labels]
    if admin:
        items.append((BACK, GroupCb(action="open", group_id=group_id)))
    return _build(items, [3, 1])


def pick_group_kb(groups, action: str) -> InlineKeyboardMarkup:
    return _build([(f"📁 {g.name}", MyGroupCb(action=action, group_id=g.id)) for g in groups])


def my_groups_kb(groups) -> InlineKeyboardMarkup:
    return _build([(f"🚪 Chiqish: {g.name}", MyGroupCb(action="leave", group_id=g.id)) for g in groups])


def admins_kb(admins) -> InlineKeyboardMarkup:
    items = [(f"❌ {u.full_name}", AdminCb(action="remove", user_id=u.id)) for u in admins]
    items.append(("➕ Nazoratchi qo'shish", AdminCb(action="add")))
    return _build(items)
