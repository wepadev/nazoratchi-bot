"""Guruh hisobotini Excel (.xlsx) faylga chiqarish — brend ranglarida."""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .db import Database, Group
from .services import question_stats, ranked
from .theme import LIGHT
from .timeutil import fmt, local

HEAD_FILL = PatternFill("solid", fgColor=LIGHT["brand"].lstrip("#"))
HEAD_FONT = Font(name="Geologica", bold=True, color="FFFFFF")
TINT_FILL = PatternFill("solid", fgColor=LIGHT["tint"].lstrip("#"))
GOOD_FILL = PatternFill("solid", fgColor=LIGHT["success_soft"].lstrip("#"))
BAD_FILL = PatternFill("solid", fgColor=LIGHT["danger_soft"].lstrip("#"))
BODY_FONT = Font(name="Geologica")


def _sheet(wb: Workbook, title: str, headers: list[str], rows: list[list], widths: list[int] | None = None):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for cell in ws[1]:
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = BODY_FONT
    for i, w in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "B2"
    return ws


async def group_report(db: Database, group: Group, now: datetime) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    members = await db.list_members(group.id)
    tests = await db.closed_tests(group.id)
    subs = {t.id: {s.user_id: s for s in await db.list_submissions(t.id)} for t in tests}

    # 1) Reyting
    rating_rows = []
    for place, u, coins in ranked(await db.rating(group.id)):
        cnt, avg = await db.user_test_stats(u.id, group.id)
        rating_rows.append([place, u.full_name, u.phone, coins, f"{cnt}/{len(tests)}",
                            round(avg, 1) if avg is not None else None])
    ws = _sheet(wb, "Reyting", ["O'rin", "F.I.Sh", "Telefon", "Tanga", "Topshirgan", "O'rtacha %"],
                rating_rows, [7, 30, 16, 9, 12, 12])
    for row in ws.iter_rows(min_row=2, max_row=4):
        for cell in row:
            cell.fill = TINT_FILL

    # 2) Natijalar matritsasi
    headers = ["F.I.Sh"] + [f"{t.title} ({t.n})" for t in tests]
    rows = []
    for m in members:
        row = [m.full_name]
        for t in tests:
            s = subs[t.id].get(m.id)
            row.append(s.correct if s else "—")
        rows.append(row)
    ws = _sheet(wb, "Natijalar", headers, rows, [30] + [14] * len(tests))
    for r_idx, row in enumerate(ws.iter_rows(min_row=2), start=0):
        for c_idx, cell in enumerate(row[1:]):
            t = tests[c_idx]
            if cell.value == "—":
                cell.fill = BAD_FILL
            elif isinstance(cell.value, int) and cell.value == t.n:
                cell.fill = GOOD_FILL
            cell.alignment = Alignment(horizontal="center")

    # 3) Savollar tahlili
    q_rows = []
    for t in tests:
        answers = [s.answers for s in subs[t.id].values()]
        if not answers:
            continue
        for num, wrong, common in question_stats(t, answers):
            q_rows.append([t.title, num, t.answer_key[num - 1], len(answers), wrong,
                           round(100 * wrong / len(answers), 1), common or ""])
    _sheet(wb, "Savollar tahlili",
           ["Test", "Savol №", "To'g'ri javob", "Topshirgan", "Xato", "Xato %", "Ko'p tanlangan xato"],
           q_rows, [28, 9, 13, 12, 8, 9, 20])

    # 4) Testlar
    t_rows = [[t.title, t.n, fmt(t.published_at), fmt(t.deadline_at),
               "faol" if t.status == "published" else "yakunlangan", len(subs[t.id]), len(members)]
              for t in tests]
    _sheet(wb, "Testlar", ["Test", "Savollar", "Nashr", "Muddat", "Holat", "Topshirdi", "A'zolar"],
           t_rows, [28, 10, 17, 17, 13, 11, 9])

    # 5) Jonli dars davomati
    lessons, att_members, att = await db.attendance_matrix(group.id)
    if lessons:
        _attendance_sheet(wb, "Davomat", lessons, att_members, att, now)

    # 6) Tangalar tarixi
    c_rows = [[fmt(c["created_at"]), c["full_name"], c["amount"], c["reason"]]
              for c in await db.coin_history(group.id, limit=5000)]
    _sheet(wb, "Tangalar tarixi", ["Sana", "F.I.Sh", "Tanga", "Sabab"], c_rows, [17, 30, 8, 50])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------- jonli dars davomati ----------------

def _mark(lesson, user_id: int, joined, att: set, now: datetime) -> str:
    if joined and joined > lesson.closes_at:
        return "—"   # o'sha paytda guruhda emas edi
    if (lesson.id, user_id) in att:
        return "✓"
    return "…" if lesson.is_open(now) else "✗"


def _attendance_sheet(wb: Workbook, title: str, lessons, members, att: set, now: datetime):
    headers = ["F.I.Sh", "Telefon", "Qatnashdi", "Qatnashmadi"] + [
        f"{local(l.created_at):%d.%m}\n{l.title}" for l in lessons]
    rows = []
    for u, joined in members:
        marks = [_mark(l, u.id, joined, att, now) for l in lessons]
        rows.append([u.full_name, u.phone, marks.count("✓"), marks.count("✗")] + marks)
    ws = _sheet(wb, title, headers, rows, [28, 16, 11, 12] + [11] * len(lessons))
    ws.freeze_panes = "E2"
    ws.row_dimensions[1].height = 34
    for row in ws.iter_rows(min_row=2, min_col=5):
        for cell in row:
            cell.alignment = Alignment(horizontal="center")
            if cell.value == "✓":
                cell.fill = GOOD_FILL
            elif cell.value == "✗":
                cell.fill = BAD_FILL
    return ws


def _sheet_title(name: str, used: set) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:28] or "Guruh"
    title, i = base, 2
    while title in used:
        title, i = f"{base[:25]} ({i})", i + 1
    used.add(title)
    return title


async def attendance_report(db: Database, groups: list[Group], now: datetime) -> bytes:
    """Barcha jonli darslar davomati bitta faylda: umumiy varaq + har guruh uchun ustoz × sana jadvali."""
    wb = Workbook()
    wb.remove(wb.active)
    summary, details, used = [], [], {"Umumiy", "Darslar"}
    lesson_rows = []
    for g in groups:
        lessons, members, att = await db.attendance_matrix(g.id)
        details.append((g, lessons, members, att))
        for u, joined in members:
            marks = [(l, _mark(l, u.id, joined, att, now)) for l in lessons]
            held = [m for _, m in marks if m in ("✓", "✗")]
            missed = [f"{local(l.created_at):%d.%m}" for l, m in marks if m == "✗"]
            pct = round(100 * held.count("✓") / len(held), 1) if held else None
            summary.append([g.name, u.full_name, u.phone, len(held), held.count("✓"), held.count("✗"), pct,
                            ", ".join(missed)])
        for l in reversed(lessons):
            present = sum(1 for u, j in members if (l.id, u.id) in att)
            eligible = sum(1 for u, j in members if not (j and j > l.closes_at))
            lesson_rows.append([g.name, f"{local(l.created_at):%d.%m.%Y}", l.title, l.code, present, eligible,
                                "ochiq" if l.is_open(now) else "yopilgan"])
    ws = _sheet(wb, "Umumiy", ["Guruh", "F.I.Sh", "Telefon", "Darslar", "Qatnashdi", "Qatnashmadi", "Davomat %",
                               "Qatnashmagan kunlari"], summary, [26, 28, 16, 9, 11, 12, 11, 40])
    for row in ws.iter_rows(min_row=2):
        if isinstance(row[5].value, int) and row[5].value > 0:
            row[5].fill = BAD_FILL
    _sheet(wb, "Darslar", ["Guruh", "Sana", "Mavzu", "Kod", "Qatnashdi", "Guruhda", "Holat"], lesson_rows,
           [26, 12, 30, 8, 11, 10, 11])
    for g, lessons, members, att in details:
        _attendance_sheet(wb, _sheet_title(g.name, used), lessons, members, att, now)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
