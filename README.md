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
   Ustoz bir vaqtda **faqat bitta guruhda** bo'ladi: boshqasiga o'tish uchun avval 📚 Guruhlarim → 🚪 Chiqish
   (chiqqanda nazoratchiga xabar boradi). Qoida bazaning o'zida tekshiriladi.
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

## Tez formatlar (bitta xabar bilan)

- **Ustoz:** `kod*javoblar`, masalan `12*abcdabcd` yoki `12*1a 2b 3c`. Test kodi e'lon xabarida yoziladi.
  Faqat bitta faol testi bo'lsa, kodsiz `abcdabcd` ham yetadi. Bot javoblarni ko'rsatib, bir marta tasdiqlatadi.
- **Nazoratchi:** `+Nomi*kalit`, masalan `+3-hafta: Hosila*abcdabcdab`. PDF yoki rasmni shu matnni izoh
  qilib yuborsa, fayl ham qo'shiladi. Bir nechta guruhi bo'lsa, bot guruhni so'raydi; keyin nashr qilinadi.

## Jonli dars davomati

- Nazoratchi guruh uchun jonli dars ochadi: 4 xonali kodni o'zi yozadi yoki avtomatik oladi, kod qancha ishlashini
  tanlaydi (30 daqiqa, 1 soat, 2 soat, kun oxirigacha). Bot: 🗂 Guruhlar → guruh → 🎥 Jonli dars. Mini App: guruh → 🎥 Jonli darslar.
- Dars oxirida kod aytiladi. Ustoz uni botga shunchaki `4821` deb yozadi (yoki «🎥 Davomat» tugmasi, yoki Mini App bosh sahifasi).
  10 daqiqada 5 tadan ortiq xato kod bloklanadi.
- Kod yopilganda (muddat tugashi yoki «Kodni yopish») nazoratchiga qatnashganlar soni va qatnashmaganlar ro'yxati keladi.
- Mini App'da har bir ustozning qatnashmagan kunlari; kodni kirita olmaganlarni nazoratchi qo'lda belgilashi mumkin.
- Excel: «📥 Davomat Excel» — nazoratchining barcha guruhlari bitta faylda (Umumiy, Darslar, har guruh uchun ustoz × sana).
  Guruh hisobotida ham «Davomat» varag'i bor.
- Darsdan keyin guruhga qo'shilganlar o'sha dars uchun qatnashmagan hisoblanmaydi.
- Tanga: qatnashgan **+5** (kod kiritilishi bilan), qoldirgan **−5** (kod yopilganda, ustozga xabar boradi).
  Nazoratchi qo'lda belgilasa yoki belgini olsa, farq avtomatik to'g'rilanadi; dars o'chirilsa, uning tangalari ham o'chadi.
  `COINS_PER_LESSON`, `PENALTY_MISSED_LESSON` bilan o'zgartiriladi.

## Tanga va reyting

- Har bir to'g'ri javob: **+1**, topshirmaslik: **−5**; jonli dars: qatnashish **+5**, qoldirish **−5** (`.env` da o'zgartiriladi).
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
- **Nazoratchi:** guruhlar paneli; test yaratish (kalit varaqasi yoki matndan, PDF/rasm yuklash), nashr / navbat,
  eslatma, hozir yakunlash, kalitni tuzatish; har savol bo'yicha xato foizi; ustozlar, tanga berish, guruhdan chiqarish,
  yangi kod, Excel (botga yuboriladi); e'tirozlar.
- **Bosh admin:** guruh yaratish, nomini o'zgartirish, o'chirish; nazoratchi qo'shish va guruhlarga tayinlash.
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
