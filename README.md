# Nazoratchi bot

Matematikadan attestatsiya va milliy sertifikatga tayyorlanayotgan ustozlar uchun Telegram bot.
Nazoratchilar test (javoblar kaliti bilan) nashr qiladi, ustozlar javob yuboradi,
bot avtomatik tekshiradi, tanga beradi va reyting tuzadi.

## Rollar

| Rol | Kim belgilaydi | Imkoniyatlar |
|---|---|---|
| **Bosh admin** | `.env` → `SUPER_ADMIN_IDS` | Guruh yaratadi, nazoratchi qo'shadi va guruhlarga tayinlaydi, hamma narsani ko'radi, nazoratchilar faoliyati |
| **Nazoratchi** | Bosh admin | Faqat o'ziga tayinlangan guruhlar: testlar, ustozlar, reyting, tanga, e'tirozlar, Excel |
| **Ustoz** | Ro'yxatdan o'tgan har kim | Kod orqali guruhga qo'shiladi, test javoblarini yuboradi, reyting va profil |

## Asosiy jarayon

1. Bosh admin: **🆕 Guruh yaratish** → nazoratchilarni belgilaydi. Guruh kodi ustozlarga beriladi.
2. Ustoz: **➕ Guruhga qo'shilish** → kodni kiritadi.
3. Nazoratchi: **🗂 Guruhlar → guruh → 📝 Testlar → ➕ Yangi test** → nom → fayl (PDF/rasm, ixtiyoriy) → kalit (`abcd...` yoki `1a 2b ...`).
4. **🚀 Nashr qilish** → muddat (12 soat … 1 hafta yoki aniq sana). Guruhda bir vaqtda **bitta** faol test bo'ladi;
   agar faol test bo'lsa, yangisi **navbatga** qo'yiladi va oldingisi yakunlanishi bilan avtomatik nashr qilinadi.
5. Ustozlar **✍️ Javob yuborish** → javoblar → tasdiqlash. Bot darhol natijani aytadi (`27/30`), javob faqat bir marta qabul qilinadi.
6. Topshirmaganlarga har **3 soatda** eslatma (tunda emas) va muddatdan **1 soat** oldin oxirgi eslatma.
7. Muddat tugaganda:
   - topshirmaganlardan **−5 tanga** (test nashridan keyin qo'shilganlarga jarima yo'q);
   - har bir ustozga xatolari va to'g'ri javoblar yuboriladi (kalit faqat shu paytda ochiladi);
   - nazoratchiga hisobot: topshirganlar, o'rtacha natija, eng ko'p xato qilingan savollar,
     topshirmaganlar, **ketma-ket 2 ta testni topshirmaganlar**.

## Tanga va reyting

- Har bir to'g'ri javob: **+1**, topshirmaslik: **−5** (`.env` da o'zgartiriladi).
- Har bir tanga sababi bilan yoziladi (Excel'dagi «Tangalar tarixi»).
- Reyting **har bir guruh uchun alohida**: umumiy / shu hafta / o'tgan hafta. Teng tangalilar bir o'rinda.
- Ustoz o'z o'rnini va TOP-10 ga qancha tanga qolganini ko'radi.
- Har dushanba soat 9:00 da o'tgan hafta reytingi hamma ustoz va nazoratchilarga yuboriladi.
- Nazoratchi qo'lda tanga berishi/ayirishi mumkin (faqat sabab bilan).

## E'tiroz va kalitni tuzatish

- Test yakunlangach, xatosi bor ustozda **⚖️ E'tiroz bildirish** tugmasi chiqadi.
- Nazoratchi: **✅ Qabul (+1)**, **❌ Rad etish** yoki **🔑 Kalitni tuzatish**.
- Kalit tuzatilsa, barcha natijalar qayta hisoblanadi, tangalar avtomatik to'g'rilanadi va ustozlarga xabar boradi.

## Hisobotlar

- **📥 Excel** (guruh kartochkasida): Reyting, Natijalar (ustoz × test), Savollar tahlili, Testlar, Tangalar tarixi.
- **📈 Faoliyat** (bosh admin): har bir nazoratchining testlari, e'tirozlarga javob tezligi, ochiq e'tirozlar.

## Mini App (bot ichidagi ilova)

Bot bilan bir serverda ishlaydi (`bot/web/`). `WEBAPP_URL` berilsa, botning menyu tugmasi va test xabarlarida
«📱 Varaqada belgilash» tugmasi paydo bo'ladi.

- **Ustoz:** tangalar va o'rin, faol testlar (qolgan vaqt), A/B/C/D javob varaqasi, natijalar
  (yakunlangach to'g'ri/xato javoblar), reyting (umumiy / shu hafta / o'tgan hafta).
- **Nazoratchi:** guruhlar paneli, faol test qanchalik topshirilgani, har savol bo'yicha xato foizi,
  natijalar va topshirmaganlar ro'yxati.
- Kirish Telegram imzosi (initData) bilan tekshiriladi; tungi rejimni qo'llab-quvvatlaydi.

## Ishga tushirish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN va SUPER_ADMIN_IDS ni to'ldiring
python -m bot
```

Bosh admin ham avval botda `/start` orqali ro'yxatdan o'tadi.

> Agar botning birinchi versiyasini ishga tushirgan bo'lsangiz, eski `data/bot.db` faylini o'chiring —
> ma'lumotlar tuzilmasi o'zgardi.

Testlar: `pip install pytest && python -m pytest -q`

## Tuzilma

```
bot/
  __main__.py      ishga tushirish (bot + fon jarayoni)
  config.py        .env sozlamalari
  db.py            SQLite: users, groups, group_admins, group_members, tests, submissions, coins, appeals
  answers.py       javoblarni o'qish (abcd / 1a 2b / kirill) va tekshirish
  services.py      nashr, javob, yakunlash, eslatma, reyting, kalitni tuzatish
  scheduler.py     har 30 soniyada: muddatlar, eslatmalar, haftalik reyting
  excel.py         Excel hisobot (brend ranglarida)
  timeutil.py      Toshkent vaqti
  theme.py         brend ranglari va shriftlari
  texts.py         matnlar,  keyboards.py  tugmalar
  handlers/        common (ro'yxat), superadmin, groups, tests_admin, appeals, user (ustoz)
tests/             avtomatik testlar (to'liq stsenariy ham bor)
```
