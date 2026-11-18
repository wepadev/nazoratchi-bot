"""Test javoblarini o'qish va tekshirish (faqat A/B/C/D).

Qabul qilinadigan formatlar:
  abcdabcd            — ketma-ket harflar (bo'sh joy, vergul bo'lishi mumkin)
  1a 2b 3c / 1-a,2-b  — raqam + harf juftliklari (tartib ixtiyoriy)
Kirill harflari ham tushuniladi (а, б/в, с, д). Javobsiz savol: x yoki (juftlik formatida) yozilmaydi.
Natijada har savol uchun bitta belgi: A, B, C, D yoki '-' (javobsiz).
"""
from __future__ import annotations

import re

MAX_QUESTIONS = 200
VALID = "abcdx"
_CYR = str.maketrans({"а": "a", "б": "b", "в": "b", "с": "c", "ц": "c", "д": "d", "х": "x"})
_PAIR = re.compile(r"(\d+)\s*[-.):=]?\s*([^\W\d_])")


class AnswerError(ValueError):
    pass


def parse_answers(text: str, n: int | None = None, allow_blank: bool = True) -> str:
    """n — kutilayotgan savollar soni (kalit kiritishda None)."""
    s = (text or "").lower().translate(_CYR)
    if any(ch.isdigit() for ch in s):
        pairs = _PAIR.findall(s)
        leftover = _PAIR.sub(" ", s)
        if re.search(r"[^\W_]", leftover):
            raise AnswerError("Format tushunarsiz. Masalan: <code>1a 2b 3c</code> yoki <code>abc</code>")
        found: dict[int, str] = {}
        for num, letter in pairs:
            i = int(num)
            if letter not in VALID:
                raise AnswerError(f"{i}-savol: «{letter.upper()}» — faqat A, B, C, D bo'lishi mumkin.")
            if i in found:
                raise AnswerError(f"{i}-savol ikki marta yozilgan.")
            found[i] = letter
        if not found:
            raise AnswerError("Javob topilmadi.")
        size = n or max(found)
        extra = sorted(i for i in found if i < 1 or i > size)
        if extra:
            raise AnswerError(f"Testda {size} ta savol bor. Ortiqcha raqam: {', '.join(map(str, extra))}.")
        result = "".join(found.get(i, "x") for i in range(1, size + 1))
    else:
        result = re.sub(r"[\s,;.\-_/|]+", "", s)
        bad = sorted(set(result) - set(VALID))
        if bad:
            raise AnswerError(
                f"Noto'g'ri belgi: {', '.join(b.upper() for b in bad)}. Faqat A, B, C, D ishlating."
            )
        if n is not None and len(result) != n:
            raise AnswerError(f"Siz {len(result)} ta javob yozdingiz, testda esa {n} ta savol bor.")
    if not result:
        raise AnswerError("Javob topilmadi.")
    if len(result) > MAX_QUESTIONS:
        raise AnswerError(f"Savollar soni {MAX_QUESTIONS} tadan oshmasligi kerak.")
    if not allow_blank and "x" in result:
        missing = [str(i + 1) for i, ch in enumerate(result) if ch == "x"]
        raise AnswerError(f"Kalitda barcha savollarga javob bo'lishi kerak. Yo'q: {', '.join(missing)}.")
    return result.upper().replace("X", "-")


def grade(answers: str, key: str) -> int:
    return sum(1 for a, k in zip(answers, key) if a == k and k != "-")


def mistakes(answers: str, key: str) -> list[tuple[int, str, str]]:
    """[(savol raqami, berilgan javob, to'g'ri javob), ...]"""
    return [(i + 1, a, k) for i, (a, k) in enumerate(zip(answers, key)) if a != k]


def preview(answers: str, per_row: int = 5) -> str:
    cells = [f"{i + 1:>3}-{ch}" for i, ch in enumerate(answers)]
    rows = [" ".join(cells[i:i + per_row]) for i in range(0, len(cells), per_row)]
    return "<pre>" + "\n".join(rows) + "</pre>"


_QUICK = re.compile(r"^\s*(\d{1,7})\s*\*\s*(.+)$", re.S)


def split_quick(text: str) -> tuple[int | None, str]:
    """'1024*abcd' -> (1024, 'abcd'); kodsiz bo'lsa (None, matn)."""
    m = _QUICK.match(text or "")
    return (int(m.group(1)), m.group(2)) if m else (None, text or "")


def looks_like_answers(text: str) -> bool:
    """Matn javoblar qatoriga o'xshaydimi (oddiy gap emasmi)."""
    s = re.sub(r"[\s\d.,;:)\-=_/|*]+", "", (text or "").lower().translate(_CYR))
    return len(s) >= 2 and set(s) <= set(VALID)
