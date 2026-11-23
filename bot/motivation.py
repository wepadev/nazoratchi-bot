"""Eslatmalar uchun motivatsion matnlar: har safar har xil.

Har bir ustozga jumlalar aralashtirilgan "dasta"dan beriladi: barcha jumlalar ishlatilmaguncha takror yo'q
(bot qayta ishga tushsa, dasta yangidan aralashtiriladi — bu muammo emas).
"""
from __future__ import annotations

import random

HEADLINES = [
    "💸 Tangalardan quruq qolib ketyapsiz!",
    "📈 Ustama uchun harakatdan to'xtamang!",
    "🏅 Toifangizni ko'taring — har bir test bir qadam!",
    "🎯 Attestatsiya o'z-o'zidan topshirilmaydi — bugun 20 daqiqa ajrating.",
    "🔥 Reytingda yuqoriga chiqish uchun ajoyib imkoniyat!",
    "🧠 Bilim — eng yaxshi sarmoya. Testni hozir ishlang!",
    "🪙 Tangalaringiz sizni kutyapti — ularni olib qo'ying!",
    "🏆 TOP-10 ga kirish imkoniyati qo'ldan ketmasin!",
    "💪 Kichik qadam — katta natija: bitta test, 15–20 daqiqa.",
    "📚 Milliy sertifikat sari yana bir qadam!",
    "⭐️ Oliy toifa tayyorgarlikdan boshlanadi.",
    "☕️ Bir piyola choy vaqtida testni topshirib qo'ying.",
    "🚀 Bugun ishlagan test — ertangi yuqori ball.",
    "😉 Testlar sizni sog'inib qoldi!",
    "🥇 Hamkasblaringiz oldinga ketyapti — siz ham ortda qolmang!",
    "💼 Yuqori toifa — yuqori ustama. Bugundan boshlang!",
    "⏳ Vaqt o'tyapti, tangalar esa hali sizniki emas.",
    "🌟 Har bir to'g'ri javob — reytingda bir pog'ona.",
    "📊 Natijangiz o'zingizga bog'liq — testni ishlang!",
    "🎓 Kuchli ustoz — doim o'qiydigan ustoz.",
    "🙌 Siz buni uddalaysiz! Faqat boshlash kerak xolos.",
    "⚡️ Hozir boshlang — keyin o'zingizga rahmat aytasiz.",
    "🧩 Har bir yechilgan masala — attestatsiyada bitta xavotir kamroq.",
    "📣 Guruhingiz sizni kutyapti — natijangizni ko'rsating!",
]

CTAS = [
    "Hoziroq boshlang 👇",
    "Pastdagi tugmani bosing — 1 daqiqada boshlaysiz 👇",
    "Bir bosish — va test ochiladi 👇",
    "Kechiktirmang, hozir ishlang 👇",
    "Boshlash uchun tugmani bosing 👇",
    "Bugun tugatib qo'ying — ertaga bo'sh bo'lasiz 👇",
    "Tangalarni olishga shoshiling 👇",
    "Keling, birga boshlaymiz 👇",
    "15 daqiqa topiladi-ku? 👇",
    "O'zingizga va'da bering — bugun topshiraman 👇",
]

FINAL_HEADLINES = [
    "🔥 Oxirgi imkoniyat! Muddat tugashiga oz qoldi.",
    "⏰ Soat millari yuguryapti — 1 soatdan kam vaqt qoldi!",
    "🚨 Shoshiling! Tez orada test yopiladi.",
    "⌛️ So'nggi daqiqalar — tangalarni boy bermang!",
]

_decks: dict[tuple[int, str], list[str]] = {}
_last: dict[tuple[int, str], str] = {}


def pick(user_id: int, pool: list[str], name: str) -> str:
    """Kartalar dastasi: pooldagi barcha jumlalar aralashtirib, birma-bir beriladi — hammasi ishlatilmaguncha
    hech biri takrorlanmaydi; yangi aylanish oldingisining oxirgi jumlasi bilan boshlanmaydi."""
    key = (user_id, name)
    deck = _decks.get(key)
    if not deck:
        deck = pool[:]
        random.shuffle(deck)
        if len(deck) > 1 and deck[-1] == _last.get(key):  # pop() oxiridan oladi
            deck[0], deck[-1] = deck[-1], deck[0]
        _decks[key] = deck
    phrase = deck.pop()
    _last[key] = phrase
    return phrase


def headline(user_id: int, final: bool = False) -> str:
    return pick(user_id, FINAL_HEADLINES, "final") if final else pick(user_id, HEADLINES, "head")


def cta(user_id: int) -> str:
    return pick(user_id, CTAS, "cta")


TASK_PROMPTS = [
    "📋 Eslatma: bugungi vazifa",
    "⏰ Unutmang — bugun qilinishi kerak:",
    "🔔 Bugungi rejangizda:",
    "📌 Esingizda bo'lsin:",
    "💪 Bugungi kichik qadam:",
    "🎯 Bugungi maqsad:",
    "☕️ Bir piyola choy va bugungi vazifa:",
    "🧠 Bilim har kuni mustahkamlanadi — bugun:",
    "🚀 Ertangi natija bugungi ishdan boshlanadi:",
    "🙂 Yana bir bor eslatib qo'yaman:",
]


def task_prompt(user_id: int) -> str:
    return pick(user_id, TASK_PROMPTS, "task")


# soatlik test eslatmasining matn uslublari (har safar boshqasi)
REMINDER_STYLES = ["list", "sentence", "total", "challenge", "time", "question", "coins", "peers"]
